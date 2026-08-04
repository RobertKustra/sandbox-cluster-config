#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ENV_LINE_RE = re.compile(r"^\s*-\s*\./environments/([a-zA-Z0-9._-]+)\.yaml\s*$")
ENV_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
ENV_TOKEN = "__ENV__"


def err(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_environment_name(name: str) -> None:
    if not ENV_NAME_RE.match(name):
        err(f"invalid environment name '{name}'. Use lowercase letters, digits, and '-' only.")


def list_enabled_environments(minikube_kustomization: Path) -> list[str]:
    if not minikube_kustomization.is_file():
        err(f"required file not found: {minikube_kustomization}")

    environments: list[str] = []
    for line in minikube_kustomization.read_text(encoding="utf-8").splitlines():
        match = ENV_LINE_RE.match(line)
        if match:
            environments.append(match.group(1))
    return environments


def render_flux_kustomization_for_env(env: str) -> str:
    return "\n".join(
        [
            "apiVersion: kustomize.toolkit.fluxcd.io/v1",
            "kind: Kustomization",
            "metadata:",
            f"  name: sandbox-env-values-{env}",
            "  namespace: flux-system",
            "spec:",
            "  interval: 5m",
            "  sourceRef:",
            "    kind: GitRepository",
            "    name: sandbox-env-values",
            "    namespace: flux-system",
            f"  path: ./overlays/{env}",
            "  prune: true",
            "  wait: true",
            "  timeout: 5m0s",
        ]
    )


def generate_env_values_kustomizations(minikube_kustomization: Path, output_file: Path) -> list[str]:
    environments = list_enabled_environments(minikube_kustomization)
    if not environments:
        err(f"no enabled environments found in {minikube_kustomization}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n---\n".join(render_flux_kustomization_for_env(env) for env in environments) + "\n"
    output_file.write_text(payload, encoding="utf-8")
    return environments


def render_template_file(template_file: Path, target_file: Path, env: str) -> None:
    content = template_file.read_text(encoding="utf-8")
    content = content.replace(ENV_TOKEN, env)
    target_file.write_text(content, encoding="utf-8")


def scaffold_env_values_overlay(template_dir: Path, env_values_repo_root: Path, env: str) -> Path:
    target_dir = env_values_repo_root / "overlays" / env

    if not template_dir.is_dir():
        err(f"required template directory not found: {template_dir}")
    if target_dir.exists():
        err(f"target overlay already exists: {target_dir}")

    target_dir.mkdir(parents=True, exist_ok=False)

    for template_file in sorted(template_dir.iterdir()):
        if not template_file.is_file():
            continue
        render_template_file(template_file, target_dir / template_file.name, env)

    return target_dir


def scaffold_cluster_environment_manifest(template_file: Path, cluster_repo_root: Path, env: str) -> Path:
    target_file = cluster_repo_root / "clusters" / "minikube" / "environments" / f"{env}.yaml"

    if not template_file.is_file():
        err(f"required template file not found: {template_file}")
    if target_file.exists():
        err(f"cluster environment manifest already exists: {target_file}")

    render_template_file(template_file, target_file, env)
    return target_file


def add_environment_reference_if_missing(minikube_kustomization: Path, env: str) -> bool:
    content = minikube_kustomization.read_text(encoding="utf-8")

    for line in content.splitlines():
        if re.match(rf"^\s*#?\s*-\s*\./environments/{re.escape(env)}\.yaml\s*$", line):
            return False

    lines = content.splitlines()
    marker = "## Environments for different stages"
    entry = f"#  - ./environments/{env}.yaml"

    for index, line in enumerate(lines):
        if line.strip() == marker:
            lines.insert(index + 1, entry)
            minikube_kustomization.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True

    lines.extend(["", marker, entry])
    minikube_kustomization.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Flux env-values kustomizations from enabled environments "
            "and scaffold new environments from dedicated templates."
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="sync",
        choices=["sync", "scaffold"],
        help="sync generates env-values-kustomizations.yaml; scaffold creates a new environment from dedicated templates",
    )
    parser.add_argument("environment", nargs="?", help="environment name for scaffold command")
    parser.add_argument(
        "--env-values-repo",
        dest="env_values_repo",
        help="override path to sandbox-env-values repository",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    script_dir = Path(__file__).resolve().parent
    cluster_repo_root = script_dir.parent
    repos_root = cluster_repo_root.parent
    template_root = cluster_repo_root / "templates" / "scaffold"
    env_values_overlay_template_dir = template_root / "env-values-overlay"
    minikube_environment_template_file = template_root / "minikube-environment.yaml"

    minikube_kustomization = cluster_repo_root / "clusters" / "minikube" / "kustomization.yaml"
    output_file = cluster_repo_root / "clusters" / "minikube" / "flux-system" / "env-values-kustomizations.yaml"

    env_values_repo_root = Path(args.env_values_repo).resolve() if args.env_values_repo else repos_root / "sandbox-env-values"

    if args.command == "sync":
        environments = generate_env_values_kustomizations(minikube_kustomization, output_file)
        print(f"Generated: {output_file}")
        print("Environments:", " ".join(environments))
        return 0

    if args.environment is None:
        err("scaffold requires environment name")

    env = args.environment
    validate_environment_name(env)

    overlay_path = scaffold_env_values_overlay(env_values_overlay_template_dir, env_values_repo_root, env)
    manifest_path = scaffold_cluster_environment_manifest(minikube_environment_template_file, cluster_repo_root, env)
    inserted = add_environment_reference_if_missing(minikube_kustomization, env)
    environments = generate_env_values_kustomizations(minikube_kustomization, output_file)

    print(f"Scaffolded env-values overlay: {overlay_path}")
    print(f"Scaffolded cluster environment manifest: {manifest_path}")
    if inserted:
        print(f"Added commented environment entry to {minikube_kustomization}: {env}")
    else:
        print(f"Environment entry already existed in {minikube_kustomization}: {env}")
    print(f"Generated: {output_file}")
    print("Environments:", " ".join(environments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
