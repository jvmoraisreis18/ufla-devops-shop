"""Valida a estrutura essencial do CycloneDX e as dependencias da aplicacao."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(sbom, requirements):
    require(isinstance(sbom, dict), "SBOM deve ser um objeto JSON")
    require(sbom.get("bomFormat") == "CycloneDX", "Formato deve ser CycloneDX")
    require(sbom.get("specVersion") == "1.6", "Versao esperada: CycloneDX 1.6")
    require(type(sbom.get("version")) is int and sbom["version"] > 0, "Versao do BOM invalida")
    components = sbom.get("components")
    require(isinstance(components, list) and components, "SBOM sem componentes")
    refs = set()
    packages = set()
    versioned = 0
    for component in components:
        require(isinstance(component, dict), "Componente invalido")
        require(isinstance(component.get("name"), str) and component["name"], "Nome ausente")
        require(isinstance(component.get("type"), str) and component["type"], "Tipo ausente")
        ref = component.get("bom-ref")
        require(isinstance(ref, str) and ref and ref not in refs, "Referencia ausente ou duplicada")
        refs.add(ref)
        if component["type"] != "file":
            version = component.get("version")
            require(isinstance(version, str) and version, "Componente de software sem versao")
            versioned += 1
            if component.get("purl", "").startswith("pkg:pypi/"):
                packages.add((re.sub(r"[-_.]+", "-", component["name"].lower()), version))

    root = sbom.get("metadata", {}).get("component", {})
    require(root.get("type") == "container" and root.get("version"), "Imagem nao identificada")
    if root.get("bom-ref"):
        refs.add(root["bom-ref"])
    dependencies = sbom.get("dependencies")
    require(isinstance(dependencies, list) and dependencies, "Relacoes de dependencia ausentes")
    for dependency in dependencies:
        require(isinstance(dependency, dict), "Dependencia invalida")
        require(dependency.get("ref") in refs, "Referencia de dependencia desconhecida")
        targets = dependency.get("dependsOn", [])
        require(isinstance(targets, list), "Lista de dependencias invalida")
        require(
            all(target in refs for target in targets),
            "Dependencia aponta para componente ausente",
        )
    require(any(d.get("dependsOn") for d in dependencies), "Grafo de dependencias vazio")

    expected = set()
    for line in requirements.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s]+)", line)
        require(match is not None, "Requisito sem versao exata ou formato nao suportado")
        expected.add((re.sub(r"[-_.]+", "-", match[1].lower()), match[2]))
    require(expected, "Nenhuma dependencia de producao definida")
    require(
        expected <= packages,
        f"Dependencias da aplicacao ausentes: {sorted(expected - packages)}",
    )
    return len(components), versioned, len(dependencies)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sbom", type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sbom = json.loads(args.sbom.read_text())
    count, versioned, dependencies = validate(sbom, args.requirements.read_text())
    with args.image.open("rb") as image:
        image_hash = hashlib.file_digest(image, "sha256").hexdigest()
    provenance = {
        "commit": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "syft_version": "1.55.0",
        "image_archive_sha256": image_hash,
        "sbom_sha256": hashlib.sha256(args.sbom.read_bytes()).hexdigest(),
        "image": sbom["metadata"]["component"],
        "components": count,
        "versioned_components": versioned,
        "dependency_entries": dependencies,
    }
    args.output.write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"SBOM valido: {count} componentes, {versioned} com versao; {dependencies} dependencias.")


if __name__ == "__main__":
    main()
