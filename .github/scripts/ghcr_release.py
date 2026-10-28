"""Transfere e publica somente a candidata aprovada, conferindo sua integridade."""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORY = "jvmoraisreis18/ufla-devops-shop"
PACKAGE = "jvmoraisreis18/ufla-shop"
CONTROLS = {"gitleaks", "ci", "sonarqube", "trivy-dependencies", "trivy-image"}
FILES = ("candidate-image.tar", "trivy-image.json", "sbom.cdx.json", "provenance.json")
ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def context():
    result = {
        key: os.environ[f"GITHUB_{key.upper()}"]
        for key in ("repository", "sha", "run_id", "run_attempt")
    }
    require(result["repository"] == REPOSITORY, "Repositorio inesperado")
    require(re.fullmatch(r"[0-9a-f]{40}", result["sha"]), "SHA do commit invalido")
    require(result["run_id"].isdigit() and result["run_attempt"].isdigit(), "Execucao invalida")
    return result


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True)


def inspect_image(reference):
    return json.loads(docker("image", "inspect", reference))[0]


def archive_config(directory):
    with tarfile.open(directory / "candidate-image.tar") as archive:
        entries = json.load(archive.extractfile("manifest.json"))
        require(len(entries) == 1, "Esperada uma unica imagem candidata")
        raw = archive.extractfile(entries[0]["Config"]).read()
    return "sha256:" + hashlib.sha256(raw).hexdigest(), json.loads(raw)


def check_loaded_image(directory, reference, manifest):
    digest, config = archive_config(directory)
    loaded = inspect_image(reference)
    require(digest == manifest["config_digest"], "Digest de configuracao divergente")
    require(loaded["Config"] == config["config"], "Configuracao da imagem carregada divergente")
    require(
        loaded["RootFS"]["Layers"] == config["rootfs"]["diff_ids"],
        "Camadas da imagem carregada divergentes",
    )
    require(
        loaded["Os"] == config["os"] and loaded["Architecture"] == config["architecture"],
        "Plataforma da imagem carregada divergente",
    )
    return loaded["Id"]


def check_evidence(directory, manifest):
    provenance = read_json(directory / "provenance.json")
    source = manifest["context"]
    require(provenance["commit"] == source["sha"], "Commit do SBOM divergente")
    require(str(provenance["run_id"]) == source["run_id"], "Execucao do SBOM divergente")
    require(str(provenance["run_attempt"]) == source["run_attempt"], "Tentativa do SBOM divergente")
    require(
        provenance["image_archive_sha256"] == manifest["files"]["candidate-image.tar"],
        "Imagem divergente da utilizada pelo Syft",
    )
    require(provenance["sbom_sha256"] == manifest["files"]["sbom.cdx.json"], "SBOM divergente")
    report = read_json(directory / "trivy-image.json")
    require(
        report["Metadata"]["ImageID"] == manifest["config_digest"],
        "Imagem divergente da analisada pelo Trivy",
    )


def bundle(directory):
    source = context()
    config_digest, _ = archive_config(directory)
    manifest = {
        "context": source,
        "image_id": inspect_image(f"ufla-shop:candidate-{source['sha']}")["Id"],
        "config_digest": config_digest,
        "files": {name: checksum(directory / name) for name in FILES},
    }
    check_evidence(directory, manifest)
    path = directory / "candidate-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"manifest-sha256={checksum(path)}\n")
    print("Candidata vinculada ao Trivy e ao Syft; hashes registrados.")


def verified_candidate(directory):
    current = context()
    require(
        os.environ.get("GITHUB_EVENT_NAME") == "push"
        and os.environ.get("GITHUB_REF") == "refs/heads/main",
        "Publicacao somente em push na main",
    )
    results = json.loads(os.environ["CONTROL_RESULTS"])
    require(
        set(results) == CONTROLS and all(results[name]["result"] == "success" for name in CONTROLS),
        "Todos os cinco controles precisam estar aprovados",
    )
    path = directory / "candidate-manifest.json"
    require(checksum(path) == os.environ["EXPECTED_MANIFEST_SHA256"], "Manifesto adulterado")
    manifest = read_json(path)
    for key in ("repository", "sha", "run_id"):
        require(manifest["context"][key] == current[key], f"Candidata de outro contexto: {key}")
    require(set(manifest["files"]) == set(FILES), "Inventario de arquivos inesperado")
    for name in FILES:
        require(checksum(directory / name) == manifest["files"][name], f"Hash divergente: {name}")
    check_evidence(directory, manifest)
    return manifest


def destination():
    return f"ghcr.io/{PACKAGE}:sha-{context()['sha']}"


def prepare(directory):
    output = Path(os.environ["PUBLICATION_DIR"])
    output.mkdir(parents=True, exist_ok=True)
    manifest = verified_candidate(directory)
    docker("load", "--input", str(directory / "candidate-image.tar"))
    source = f"ufla-shop:candidate-{context()['sha']}"
    loaded_id = check_loaded_image(directory, source, manifest)
    docker("tag", source, destination())
    require(
        check_loaded_image(directory, destination(), manifest) == loaded_id,
        "Imagem de destino divergente",
    )
    (output / "verified-candidate.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Hashes, contexto, evidencias e ID da imagem carregada conferidos.")


def registry_token():
    credential = base64.b64encode(
        f"{os.environ['GITHUB_ACTOR']}:{os.environ['GHCR_TOKEN']}".encode()
    ).decode()
    query = urllib.parse.urlencode(
        {"service": "ghcr.io", "scope": f"repository:{PACKAGE}:pull"}
    )
    request = urllib.request.Request(
        f"https://ghcr.io/token?{query}", headers={"Authorization": f"Basic {credential}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response).get("token")
    require(isinstance(token, str) and token, "GHCR nao retornou token de acesso")
    return token


def remote_manifest(token, reference, allow_missing=False):
    request = urllib.request.Request(
        f"https://ghcr.io/v2/{PACKAGE}/manifests/{reference}",
        headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            digest = response.headers.get("Docker-Content-Digest")
    except urllib.error.HTTPError as error:
        if allow_missing and error.code == 404:
            codes = {e.get("code") for e in json.loads(error.read()).get("errors", [])}
            require(
                codes and codes <= {"MANIFEST_UNKNOWN", "NAME_UNKNOWN"},
                "Resposta inesperada do GHCR ao consultar tag",
            )
            return None
        raise
    require(digest == "sha256:" + hashlib.sha256(raw).hexdigest(), "Digest remoto divergente")
    if reference.startswith("sha256:"):
        require(reference == digest, "Manifesto remoto difere do digest solicitado")
    return digest, json.loads(raw)


def has_image(token, manifest, expected_id):
    if "config" in manifest:
        return manifest["config"]["digest"] == expected_id
    # Docker com image store containerd pode publicar indice OCI com attestations.
    for descriptor in manifest.get("manifests", []):
        if descriptor.get("platform", {}).get("os") == "unknown":
            continue
        child = remote_manifest(token, descriptor["digest"])
        if "config" in child[1] and child[1]["config"]["digest"] == expected_id:
            return True
    return False


def publish(directory):
    manifest = verified_candidate(directory)
    check_loaded_image(directory, destination(), manifest)
    token = registry_token()
    tag = "sha-" + context()["sha"]
    require(
        remote_manifest(token, tag, allow_missing=True) is None,
        "Tag SHA ja existe; sobrescrita recusada",
    )
    output = Path(os.environ["PUBLICATION_DIR"])
    push = subprocess.run(["docker", "push", destination()], capture_output=True, text=True)
    (output / "push.log").write_text(push.stdout + push.stderr)
    require(push.returncode == 0, "Docker push falhou; consulte push.log")
    digest, remote = remote_manifest(token, tag)
    require(
        has_image(token, remote, manifest["config_digest"]), "Imagem publicada difere da candidata"
    )
    current = context()
    run_url = f"https://github.com/{REPOSITORY}/actions/runs/{current['run_id']}"
    release = {
        "image": destination(),
        "digest": digest,
        "pull_reference": f"ghcr.io/{PACKAGE}@{digest}",
        "context": current,
        "candidate": manifest,
        "candidate_manifest_sha256": os.environ["EXPECTED_MANIFEST_SHA256"],
        "candidate_artifact_id": os.environ["CANDIDATE_ARTIFACT_ID"],
        "controls": {name: "success" for name in sorted(CONTROLS)},
        "run_url": run_url,
    }
    (output / "publication.json").write_text(json.dumps(release, indent=2) + "\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
        summary.write(f"Imagem: `{destination()}`\n\nDigest: `{digest}`\n\n")
        summary.write(f"Commit: `{current['sha']}`\n\n[Controles e artifacts]({run_url})\n")
    print(f"Imagem aprovada publicada: ghcr.io/{PACKAGE}@{digest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("bundle", "prepare", "publish"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    {"bundle": bundle, "prepare": prepare, "publish": publish}[args.operation](args.directory)


if __name__ == "__main__":
    main()
