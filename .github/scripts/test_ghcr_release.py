"""Testes da transferencia e publicacao; Docker e registry sempre simulados."""

import contextlib
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import ghcr_release as release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        temp = tempfile.TemporaryDirectory(prefix="ufla-release-tests-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.directory = self.root / "candidate"
        self.directory.mkdir()
        self.output = self.root / "publication"
        self.output.mkdir()
        self.image_id = "sha256:" + "b" * 64
        self.config = {
            "config": {"Cmd": ["fixture"]},
            "rootfs": {"diff_ids": []},
            "os": "linux",
            "architecture": "amd64",
        }
        raw_config = json.dumps(self.config).encode()
        self.config_digest = "sha256:" + hashlib.sha256(raw_config).hexdigest()
        with tarfile.open(self.directory / "candidate-image.tar", "w") as archive:
            for name, raw in (
                ("config.json", raw_config),
                ("manifest.json", b'[{"Config":"config.json"}]'),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
        self.env = {
            "GITHUB_REPOSITORY": release.REPOSITORY,
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_OUTPUT": str(self.root / "outputs"),
            "GITHUB_STEP_SUMMARY": str(self.root / "summary"),
            "PUBLICATION_DIR": str(self.output),
            "CANDIDATE_ARTIFACT_ID": "42",
            "CONTROL_RESULTS": json.dumps(
                {name: {"result": "success"} for name in release.CONTROLS}
            ),
        }
        # Restaura o ambiente sem depender dos valores anteriores dos testes.
        self.env_patch = mock.patch.dict(os.environ, self.env)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.inspect_mock = mock.patch.object(
            release,
            "inspect_image",
            return_value={
                "Id": self.image_id,
                "Config": self.config["config"],
                "RootFS": {"Layers": []},
                "Os": "linux",
                "Architecture": "amd64",
            },
        ).start()
        self.addCleanup(mock.patch.stopall)
        self.docker_mock = mock.patch.object(release, "docker", return_value="").start()
        self.push_mock = mock.patch.object(
            release.subprocess,
            "run",
            return_value=mock.Mock(returncode=0, stdout="push simulado\n", stderr=""),
        ).start()
        mock.patch.object(
            release.urllib.request,
            "urlopen",
            side_effect=AssertionError("Rede real proibida no teste"),
        ).start()
        (self.directory / "sbom.cdx.json").write_text('{"bomFormat":"CycloneDX"}')
        (self.directory / "trivy-image.json").write_text(
            json.dumps(
                {
                    "Metadata": {"ImageID": self.config_digest},
                }
            )
        )
        provenance = {
            "commit": self.env["GITHUB_SHA"],
            "run_id": "123",
            "run_attempt": "1",
            "image_archive_sha256": release.checksum(self.directory / "candidate-image.tar"),
            "sbom_sha256": release.checksum(self.directory / "sbom.cdx.json"),
        }
        (self.directory / "provenance.json").write_text(json.dumps(provenance))
        release.bundle(self.directory)
        os.environ["EXPECTED_MANIFEST_SHA256"] = release.checksum(
            self.directory / "candidate-manifest.json"
        )

    def test_bundle_and_prepare_preserve_image_id(self):
        release.prepare(self.directory)
        self.docker_mock.assert_any_call(
            "load", "--input", str(self.directory / "candidate-image.tar")
        )
        self.docker_mock.assert_any_call(
            "tag", "ufla-shop:candidate-" + self.env["GITHUB_SHA"], release.destination()
        )
        self.assertTrue((self.output / "verified-candidate.json").is_file())
        self.push_mock.assert_not_called()

    def test_each_payload_and_manifest_tampering_is_rejected(self):
        for name in (*release.FILES, "candidate-manifest.json"):
            with self.subTest(name=name):
                path = self.directory / name
                original = path.read_bytes()
                path.write_bytes(original + b"tampered")
                with self.assertRaises(ValueError):
                    release.prepare(self.directory)
                path.write_bytes(original)
        self.docker_mock.assert_not_called()

    def test_other_commit_or_run_is_rejected(self):
        for key, value in (("GITHUB_SHA", "c" * 40), ("GITHUB_RUN_ID", "456")):
            with self.subTest(key=key), mock.patch.dict(os.environ, {key: value}):
                with self.assertRaises(ValueError):
                    release.verified_candidate(self.directory)

    def test_pull_requests_and_other_branches_are_rejected(self):
        for change in ({"GITHUB_EVENT_NAME": "pull_request"}, {"GITHUB_REF": "refs/heads/dev"}):
            with self.subTest(change=change), mock.patch.dict(os.environ, change):
                with self.assertRaises(ValueError):
                    release.publish(self.directory)
        self.push_mock.assert_not_called()

    def test_each_control_must_succeed(self):
        for name in release.CONTROLS:
            for status in ("failure", "cancelled", "skipped", None):
                results = {key: {"result": "success"} for key in release.CONTROLS}
                results[name]["result"] = status
                with (
                    self.subTest(name=name, status=status),
                    mock.patch.dict(os.environ, {"CONTROL_RESULTS": json.dumps(results)}),
                    self.assertRaises(ValueError),
                ):
                    release.publish(self.directory)
        self.push_mock.assert_not_called()

    def test_loaded_image_mismatch_is_rejected(self):
        self.inspect_mock.return_value["Config"] = {"Cmd": ["wrong image"]}
        with self.assertRaises(ValueError):
            release.prepare(self.directory)
        self.push_mock.assert_not_called()

    def test_different_docker_store_ids_preserve_same_runtime(self):
        self.inspect_mock.return_value["Id"] = self.config_digest
        release.prepare(self.directory)
        self.assertTrue((self.output / "verified-candidate.json").exists())
        self.push_mock.assert_not_called()

    def test_changed_layers_are_rejected(self):
        self.inspect_mock.return_value["RootFS"]["Layers"] = ["sha256:" + "c" * 64]
        with self.assertRaises(ValueError):
            release.prepare(self.directory)
        self.push_mock.assert_not_called()

    def test_failed_job_rerun_can_use_verified_original_attempt(self):
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "2"}):
            candidate = release.verified_candidate(self.directory)
        self.assertEqual(candidate["context"]["run_attempt"], "1")

    @mock.patch.object(release, "registry_token", return_value="ficticio")
    @mock.patch.object(release, "remote_manifest")
    def test_existing_tag_or_registry_error_never_pushes(self, remote, _token):
        remote.return_value = ("sha256:" + "d" * 64, {})
        with self.assertRaises(ValueError):
            release.publish(self.directory)
        remote.side_effect = OSError("registry indisponivel")
        with self.assertRaises(OSError):
            release.publish(self.directory)
        self.push_mock.assert_not_called()

    @mock.patch.object(release, "registry_token", return_value="ficticio")
    @mock.patch.object(release, "remote_manifest")
    def test_success_records_digest_evidence_and_trace(self, remote, _token):
        digest = "sha256:" + "d" * 64
        remote.side_effect = [None, (digest, {"config": {"digest": self.config_digest}})]
        release.publish(self.directory)
        self.push_mock.assert_called_once_with(
            ["docker", "push", release.destination()], capture_output=True, text=True
        )
        publication = release.read_json(self.output / "publication.json")
        self.assertEqual(publication["digest"], digest)
        self.assertEqual(publication["candidate"]["image_id"], self.image_id)
        self.assertEqual(publication["candidate_artifact_id"], "42")
        self.assertEqual(publication["context"]["sha"], self.env["GITHUB_SHA"])

    @mock.patch.object(release, "registry_token", return_value="ficticio")
    @mock.patch.object(release, "remote_manifest", return_value=None)
    def test_push_error_is_not_success(self, _remote, _token):
        self.push_mock.return_value.returncode = 1
        with self.assertRaises(ValueError):
            release.publish(self.directory)
        self.assertFalse((self.output / "publication.json").exists())
        self.assertTrue((self.output / "push.log").exists())

    @mock.patch.object(release, "registry_token", return_value="ficticio")
    @mock.patch.object(release, "remote_manifest")
    def test_remote_image_mismatch_is_not_approved(self, remote, _token):
        remote.side_effect = [
            None,
            ("sha256:" + "d" * 64, {"config": {"digest": "sha256:" + "c" * 64}}),
        ]
        with self.assertRaises(ValueError):
            release.publish(self.directory)
        self.assertFalse((self.output / "publication.json").exists())

    def test_remote_manifest_requires_matching_content_digest(self):
        raw = b'{"config":{"digest":"candidate"}}'
        response = io.BytesIO(raw)
        response.headers = {"Docker-Content-Digest": "sha256:" + hashlib.sha256(raw).hexdigest()}
        with mock.patch.object(release.urllib.request, "urlopen", return_value=response):
            digest, _ = release.remote_manifest("ficticio", "sha-test")
        self.assertEqual(digest, "sha256:" + hashlib.sha256(raw).hexdigest())
        bad = io.BytesIO(raw)
        bad.headers = {"Docker-Content-Digest": "sha256:" + "0" * 64}
        with (
            mock.patch.object(release.urllib.request, "urlopen", return_value=bad),
            self.assertRaises(ValueError),
        ):
            release.remote_manifest("ficticio", "sha-test")

    def test_only_explicit_not_found_allows_first_push(self):
        error = urllib.error.HTTPError(
            "https://ghcr.io/fixture",
            404,
            "missing",
            {},
            io.BytesIO(b'{"errors":[{"code":"MANIFEST_UNKNOWN"}]}'),
        )
        self.addCleanup(error.close)
        with mock.patch.object(release.urllib.request, "urlopen", side_effect=error):
            self.assertIsNone(release.remote_manifest("ficticio", "sha-test", allow_missing=True))
        for code in (401, 403, 429, 500):
            error = urllib.error.HTTPError(
                "https://ghcr.io/fixture", code, "error", {}, io.BytesIO()
            )
            self.addCleanup(error.close)
            with (
                self.subTest(code=code),
                mock.patch.object(release.urllib.request, "urlopen", side_effect=error),
                self.assertRaises(urllib.error.HTTPError),
            ):
                release.remote_manifest("ficticio", "sha-test", allow_missing=True)


if __name__ == "__main__":
    unittest.main()
