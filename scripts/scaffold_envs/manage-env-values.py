#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ACTIVE_ENV_LINE_RE = re.compile(r"^\s*-\s*\./environments/([a-zA-Z0-9._-]+)\.yaml\s*$")
ENV_ENTRY_RE = re.compile(r"^\s*#?\s*-\s*\./environments/([a-zA-Z0-9._-]+)\.yaml\s*$")
ENV_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
CLUSTER_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
ENV_TOKEN = "__ENV__"
CLUSTER_ENV_SECTION_MARKER = "  ## Environments for different stages"
COMMAND_CHOICES = {"sync", "scaffold", "scaffold-config"}


@dataclass(frozen=True)
class ServiceDefinition:
    workload_resource: str
    health_check_name: str | None = None
    env_values_configmap_name: str | None = None
    env_values_file: str | None = None
    image_repository: str | None = None


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    tag: str | None = None
    image_repository_prefix: str | None = None


@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    services: list[ServiceConfig]
    image_updater: bool


@dataclass(frozen=True)
class ClusterScaffoldConfig:
    cluster: str
    environments: list[EnvironmentConfig]


@dataclass(frozen=True)
class ParsedLine:
    number: int
    indent: int
    content: str


SERVICE_DEFINITIONS: dict[str, ServiceDefinition] = {
    "sandbox-nginx": ServiceDefinition(
        workload_resource="../../../../apps/sandbox-nginx/overlays/{env}",
        health_check_name="sandbox-nginx",
        env_values_configmap_name="sandbox-nginx-values-env",
        env_values_file="sandbox-nginx.yaml",
    ),
    "sandbox-redis": ServiceDefinition(
        workload_resource="../../../../apps/sandbox-redis/overlays/{env}",
        health_check_name="sandbox-redis",
        env_values_configmap_name="sandbox-redis-values-env",
        env_values_file="sandbox-redis-values.yaml",
    ),
    "sandbox-ai-consumer": ServiceDefinition(
        workload_resource="../../../../apps/sandbox-ai-consumer/overlays/{env}",
        health_check_name="sandbox-ai-consumer",
        env_values_configmap_name="sandbox-ai-consumer-values-env",
        env_values_file="sandbox-ai-consumer-values.yaml",
        image_repository="ghcr.io/robertkustra/{env}/sandbox-ai-consumer",
    ),
    "postgres": ServiceDefinition(
        workload_resource="../../../../postgres/overlays/{env}",
    ),
}


def err(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def normalize_argv(argv: list[str]) -> list[str]:
    # Allow shorthand: `python manage-env-values.py scaffold-config.yaml`
    if len(argv) >= 2 and argv[1] not in COMMAND_CHOICES and not argv[1].startswith("-"):
        suffix = Path(argv[1]).suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return [argv[0], "scaffold-config", argv[1], *argv[2:]]
    return argv


def discover_cluster_repo_root(start_dir: Path) -> Path:
    for candidate in [start_dir, *start_dir.parents]:
        if (candidate / "clusters").is_dir() and (candidate / "cluster-components").is_dir():
            return candidate
    err(f"could not detect sandbox-cluster-config root from {start_dir}")


def discover_template_root(script_dir: Path, cluster_repo_root: Path) -> Path:
    local_template_root = script_dir / "templates" / "scaffold"
    repo_template_root = cluster_repo_root / "templates" / "scaffold"

    if local_template_root.is_dir():
        return local_template_root
    if repo_template_root.is_dir():
        return repo_template_root

    err(
        "templates not found. Expected one of: "
        f"{local_template_root} or {repo_template_root}"
    )


def validate_environment_name(name: str) -> None:
    if not ENV_NAME_RE.match(name):
        err(f"invalid environment name '{name}'. Use lowercase letters, digits, and '-' only.")


def validate_cluster_name(name: str) -> None:
    if not CLUSTER_NAME_RE.match(name):
        err(f"invalid cluster name '{name}'. Use lowercase letters, digits, and '-' only.")


def list_enabled_environments(cluster_kustomization: Path) -> list[str]:
    if not cluster_kustomization.is_file():
        err(f"required file not found: {cluster_kustomization}")

    environments: list[str] = []
    for line in cluster_kustomization.read_text(encoding="utf-8").splitlines():
        match = ACTIVE_ENV_LINE_RE.match(line)
        if match:
            environments.append(match.group(1))
    return environments


def render_flux_env_values_kustomization_for_env(env: str) -> str:
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


def generate_env_values_kustomizations_from_names(environment_names: list[str], output_file: Path) -> list[str]:
    if not environment_names:
        err(f"no environments provided for {output_file}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n---\n".join(render_flux_env_values_kustomization_for_env(env) for env in environment_names) + "\n"
    output_file.write_text(payload, encoding="utf-8")
    return environment_names


def generate_env_values_kustomizations(cluster_kustomization: Path, output_file: Path) -> list[str]:
    environments = list_enabled_environments(cluster_kustomization)
    if not environments:
        err(f"no enabled environments found in {cluster_kustomization}")
    return generate_env_values_kustomizations_from_names(environments, output_file)


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


def add_environment_reference_if_missing(cluster_kustomization: Path, env: str) -> bool:
    content = cluster_kustomization.read_text(encoding="utf-8")

    for line in content.splitlines():
        if re.match(rf"^\s*#?\s*-\s*\./environments/{re.escape(env)}\.yaml\s*$", line):
            return False

    lines = content.splitlines()
    entry = f"#  - ./environments/{env}.yaml"

    for index, line in enumerate(lines):
        if line == CLUSTER_ENV_SECTION_MARKER:
            lines.insert(index + 1, entry)
            cluster_kustomization.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True

    lines.extend(["", CLUSTER_ENV_SECTION_MARKER, entry])
    cluster_kustomization.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def strip_inline_comment(raw_line: str) -> str:
    result: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for index, char in enumerate(raw_line):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "#" and not in_single_quote and not in_double_quote:
            if index == 0 or raw_line[index - 1].isspace():
                break
        result.append(char)

    return "".join(result).rstrip()


def parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def tokenize_yaml(text: str) -> list[ParsedLine]:
    parsed_lines: list[ParsedLine] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if "\t" in raw_line:
            err(f"tabs are not supported in scaffold YAML (line {line_number})")

        stripped = strip_inline_comment(raw_line)
        if not stripped.strip():
            continue

        indent = len(stripped) - len(stripped.lstrip(" "))
        parsed_lines.append(ParsedLine(number=line_number, indent=indent, content=stripped.strip()))
    return parsed_lines


def parse_yaml_block(lines: list[ParsedLine], index: int) -> tuple[Any, int]:
    if index >= len(lines):
        err("unexpected end of scaffold YAML")
    if lines[index].content.startswith("- "):
        return parse_yaml_sequence(lines, index, lines[index].indent)
    return parse_yaml_mapping(lines, index, lines[index].indent)


def parse_yaml_mapping(lines: list[ParsedLine], index: int, indent: int) -> tuple[dict[str, Any], int]:
    data: dict[str, Any] = {}

    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            err(f"unexpected indentation on line {line.number}")
        if line.content.startswith("- "):
            break
        if ":" not in line.content:
            err(f"expected key/value pair on line {line.number}")

        key, raw_value = line.content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        index += 1

        if not key:
            err(f"empty key on line {line.number}")

        if raw_value:
            data[key] = parse_scalar(raw_value)
            continue

        if index >= len(lines) or lines[index].indent <= indent:
            data[key] = {}
            continue

        nested_value, index = parse_yaml_block(lines, index)
        data[key] = nested_value

    return data, index


def parse_yaml_sequence(lines: list[ParsedLine], index: int, indent: int) -> tuple[list[Any], int]:
    values: list[Any] = []

    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            err(f"unexpected indentation on line {line.number}")
        if not line.content.startswith("- "):
            break

        item_content = line.content[2:].strip()
        index += 1

        if not item_content:
            if index >= len(lines) or lines[index].indent <= indent:
                values.append(None)
                continue

            nested_value, index = parse_yaml_block(lines, index)
            values.append(nested_value)
            continue

        if ":" in item_content:
            key, raw_value = item_content.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            item: dict[str, Any] = {}

            if not key:
                err(f"empty key in list item on line {line.number}")

            if raw_value:
                item[key] = parse_scalar(raw_value)
            elif index < len(lines) and lines[index].indent > indent:
                nested_value, index = parse_yaml_block(lines, index)
                item[key] = nested_value
            else:
                item[key] = {}

            if index < len(lines) and lines[index].indent > indent:
                extra_mapping, index = parse_yaml_mapping(lines, index, lines[index].indent)
                for extra_key, extra_value in extra_mapping.items():
                    if extra_key in item:
                        err(f"duplicate key '{extra_key}' near line {line.number}")
                    item[extra_key] = extra_value

            values.append(item)
            continue

        if index < len(lines) and lines[index].indent > indent:
            err(f"scalar list item cannot have nested content (line {line.number})")

        values.append(parse_scalar(item_content))

    return values, index


def load_scaffold_yaml(config_file: Path) -> dict[str, Any]:
    if not config_file.is_file():
        err(f"scaffold config file not found: {config_file}")

    text = config_file.read_text(encoding="utf-8")
    lines = tokenize_yaml(text)
    if not lines:
        err(f"scaffold config file is empty: {config_file}")

    document, next_index = parse_yaml_block(lines, 0)
    if next_index != len(lines):
        err(f"unable to parse scaffold YAML after line {lines[next_index].number}")
    if not isinstance(document, dict):
        err("scaffold YAML root must be a mapping")

    return document


def ensure_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        err(f"field '{field_name}' must be a non-empty string")
    return value.strip()


def ensure_boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        err(f"field '{field_name}' must be true or false")
    return value


def ensure_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        err(f"field '{field_name}' must be a non-empty list")

    items: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, str) or not raw_item.strip():
            err(f"field '{field_name}' must contain non-empty strings only")
        item = raw_item.strip()
        if item in seen:
            err(f"field '{field_name}' contains duplicate value '{item}'")
        seen.add(item)
        items.append(item)
    return items


def load_service_config(raw_service: Any, field_name: str) -> ServiceConfig:
    if isinstance(raw_service, str):
        service_name = raw_service.strip()
        if not service_name:
            err(f"field '{field_name}' must not contain empty service names")
        return ServiceConfig(name=service_name)

    if not isinstance(raw_service, dict):
        err(f"field '{field_name}' entries must be either strings or mappings")

    service_name = ensure_string(raw_service.get("name"), f"{field_name}.name")
    tag_value = raw_service.get("tag")
    tag = ensure_string(tag_value, f"{field_name}.tag") if tag_value is not None else None
    image_repository_prefix_value = raw_service.get("image_repository_prefix")
    image_repository_prefix = (
        ensure_string(image_repository_prefix_value, f"{field_name}.image_repository_prefix")
        if image_repository_prefix_value is not None
        else None
    )
    if image_repository_prefix is not None:
        validate_environment_name(image_repository_prefix)

    return ServiceConfig(name=service_name, tag=tag, image_repository_prefix=image_repository_prefix)


def load_service_configs(value: Any, field_name: str) -> list[ServiceConfig]:
    if not isinstance(value, list) or not value:
        err(f"field '{field_name}' must be a non-empty list")

    services: list[ServiceConfig] = []
    seen: set[str] = set()
    for index, raw_service in enumerate(value, start=1):
        service = load_service_config(raw_service, f"{field_name}[{index}]")
        if service.name in seen:
            err(f"field '{field_name}' contains duplicate service '{service.name}'")
        seen.add(service.name)

        if service.name not in SERVICE_DEFINITIONS:
            supported = ", ".join(sorted(SERVICE_DEFINITIONS))
            err(f"unsupported service '{service.name}'. Supported services: {supported}")

        definition = SERVICE_DEFINITIONS[service.name]
        if service.tag is not None and definition.env_values_file is None:
            err(f"service '{service.name}' does not support tag overrides")
        if service.image_repository_prefix is not None and definition.image_repository is None:
            err(f"service '{service.name}' does not support image_repository_prefix")

        services.append(service)

    return services


def load_cluster_scaffold_config(config_file: Path) -> ClusterScaffoldConfig:
    document = load_scaffold_yaml(config_file)

    cluster_value = document.get("cluster", document.get("cluster_name"))
    cluster = ensure_string(cluster_value, "cluster")
    validate_cluster_name(cluster)

    raw_environments = document.get("environments")
    if not isinstance(raw_environments, list) or not raw_environments:
        err("field 'environments' must be a non-empty list")

    environments: list[EnvironmentConfig] = []
    seen_envs: set[str] = set()

    for index, raw_env in enumerate(raw_environments, start=1):
        if not isinstance(raw_env, dict):
            err(f"environment entry #{index} must be a mapping")

        env_name = ensure_string(raw_env.get("name"), f"environments[{index}].name")
        validate_environment_name(env_name)
        if env_name in seen_envs:
            err(f"duplicate environment '{env_name}' in scaffold config")
        seen_envs.add(env_name)

        services = load_service_configs(raw_env.get("services"), f"environments[{index}].services")

        image_updater = ensure_boolean(raw_env.get("image_updater", False), f"environments[{index}].image_updater")
        environments.append(EnvironmentConfig(name=env_name, services=services, image_updater=image_updater))

    return ClusterScaffoldConfig(cluster=cluster, environments=environments)


def write_text_file(target_file: Path, content: str) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")


def write_template_if_missing(template_file: Path, target_file: Path, env: str) -> bool:
    if target_file.exists():
        return False
    render_template_file(template_file, target_file, env)
    return True


def render_environment_workload_kustomization(environment: EnvironmentConfig, include_image_reflector: bool) -> str:
    lines = [
        "apiVersion: kustomize.config.k8s.io/v1beta1",
        "kind: Kustomization",
        "resources:",
    ]

    if include_image_reflector:
        lines.append("  - ./image-reflector.yaml")

    for service in environment.services:
        definition = SERVICE_DEFINITIONS[service.name]
        lines.append(f"  - {definition.workload_resource.format(env=environment.name)}")

    return "\n".join(lines) + "\n"


def render_environment_flux_kustomization(cluster: str, environment: EnvironmentConfig) -> str:
    lines = [
        "apiVersion: kustomize.toolkit.fluxcd.io/v1",
        "kind: Kustomization",
        "metadata:",
        f"  name: {cluster}-{environment.name}",
        "  namespace: flux-system",
        "spec:",
        "  interval: 10m",
        "  dependsOn:",
        f"    - name: {cluster}-postgres-operator",
        f"    - name: {cluster}-monitoring",
        f"    - name: sandbox-env-values-{environment.name}",
        f"  path: ./clusters/{cluster}/environments/{environment.name}",
        "  prune: true",
        "  wait: true",
    ]

    health_check_services = [
        SERVICE_DEFINITIONS[service.name]
        for service in environment.services
        if SERVICE_DEFINITIONS[service.name].health_check_name
    ]
    if health_check_services:
        lines.append("  healthChecks:")
        for service in health_check_services:
            lines.extend(
                [
                    "    - apiVersion: helm.toolkit.fluxcd.io/v2",
                    "      kind: HelmRelease",
                    f"      name: {service.health_check_name}",
                    f"      namespace: {environment.name}",
                ]
            )

    lines.extend(
        [
            "  timeout: 5m0s",
            "  sourceRef:",
            "    kind: GitRepository",
            "    name: flux-system",
            "  postBuild:",
            "    substitute:",
            f"      cluster: {cluster}",
            f"      environment: {environment.name}",
        ]
    )

    return "\n".join(lines) + "\n"


def render_env_values_overlay_kustomization(environment: EnvironmentConfig) -> str:
    lines = [
        "apiVersion: kustomize.config.k8s.io/v1beta1",
        "kind: Kustomization",
        f"namespace: {environment.name}",
        "resources:",
        "  - ./namespace.yaml",
        "  - ../../base",
    ]

    configmap_services = [
        SERVICE_DEFINITIONS[service.name]
        for service in environment.services
        if SERVICE_DEFINITIONS[service.name].env_values_configmap_name and SERVICE_DEFINITIONS[service.name].env_values_file
    ]

    if configmap_services:
        lines.append("configMapGenerator:")
        for service in configmap_services:
            lines.extend(
                [
                    f"  - name: {service.env_values_configmap_name}",
                    "    files:",
                    f"      - values.yaml={service.env_values_file}",
                ]
            )

    lines.extend(
        [
            "generatorOptions:",
            "  disableNameSuffixHash: true",
        ]
    )

    return "\n".join(lines) + "\n"


def render_namespace_manifest(environment: str) -> str:
    return "\n".join(
        [
            "apiVersion: v1",
            "kind: Namespace",
            "metadata:",
            f"  name: {environment}",
            "  labels:",
            f"    environment: {environment}",
        ]
    ) + "\n"


def resolve_image_repository(service: ServiceConfig, environment_name: str) -> str | None:
    definition = SERVICE_DEFINITIONS[service.name]
    if definition.image_repository is None:
        return None

    prefix = service.image_repository_prefix or environment_name
    return definition.image_repository.format(env=prefix)


def render_service_image_block(service: ServiceConfig, environment: EnvironmentConfig) -> list[str]:
    definition = SERVICE_DEFINITIONS[service.name]
    if definition.env_values_file is None:
        return []

    repository = resolve_image_repository(service, environment.name)
    if service.tag is None and repository is None:
        return []

    lines = ["image:"]
    if repository is not None:
        lines.append(f"  repository: {repository}")
    if service.tag is not None:
        tag_line = f'  tag: "{service.tag}"'
        if environment.image_updater and repository is not None:
            tag_line += f' # {{"$imagepolicy": "{environment.name}:{service.name}-{environment.name}:tag"}}'
        lines.append(tag_line)
    return lines


def replace_top_level_yaml_block(content: str, key: str, block_lines: list[str]) -> str:
    lines = content.splitlines()
    pattern = re.compile(rf"^{re.escape(key)}:\s*(?:#.*)?$")
    start_index: int | None = None
    end_index = 0

    for index, line in enumerate(lines):
        if pattern.match(line):
            start_index = index
            end_index = index + 1
            while end_index < len(lines):
                next_line = lines[end_index]
                if next_line and not next_line.startswith((" ", "#")):
                    break
                end_index += 1
            break

    if start_index is None:
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            lines.append("")
        lines.extend(block_lines)
        return "\n".join(lines) + "\n"

    updated_lines = lines[:start_index] + block_lines + lines[end_index:]
    return "\n".join(updated_lines) + "\n"


def sync_service_values_file(overlay_dir: Path, service: ServiceConfig, environment: EnvironmentConfig) -> None:
    definition = SERVICE_DEFINITIONS[service.name]
    if definition.env_values_file is None:
        return

    block_lines = render_service_image_block(service, environment)
    if not block_lines:
        return

    target_file = overlay_dir / definition.env_values_file
    if not target_file.is_file():
        err(f"service values file not found after scaffold: {target_file}")

    updated = replace_top_level_yaml_block(target_file.read_text(encoding="utf-8"), "image", block_lines)
    target_file.write_text(updated, encoding="utf-8")


def render_image_reflector_resources(environment: EnvironmentConfig) -> list[str]:
    resources: list[str] = []
    image_services = [
        (service, SERVICE_DEFINITIONS[service.name])
        for service in environment.services
        if SERVICE_DEFINITIONS[service.name].image_repository
    ]

    if not environment.image_updater or not image_services:
        return resources

    for service_config, service in image_services:
        resources.append(
            "\n".join(
                [
                    "apiVersion: image.toolkit.fluxcd.io/v1",
                    "kind: ImageRepository",
                    "metadata:",
                    f"  name: {service_config.name}-{environment.name}",
                    f"  namespace: {environment.name}",
                    "spec:",
                    "  interval: 1m",
                    f"  image: {resolve_image_repository(service_config, environment.name)}",
                    "  secretRef:",
                    "    name: ghcr-pull-secret",
                ]
            )
        )
        resources.append(
            "\n".join(
                [
                    "apiVersion: image.toolkit.fluxcd.io/v1",
                    "kind: ImagePolicy",
                    "metadata:",
                    f"  name: {service_config.name}-{environment.name}",
                    f"  namespace: {environment.name}",
                    "spec:",
                    "  imageRepositoryRef:",
                    f"    name: {service_config.name}-{environment.name}",
                    "  policy:",
                    "    semver:",
                    '      range: ">=0.0.0"',
                ]
            )
        )

    return resources


def render_image_update_automation(environment: EnvironmentConfig) -> str | None:
    image_services = [
        service
        for service in environment.services
        if SERVICE_DEFINITIONS[service.name].image_repository
    ]

    if not environment.image_updater or not image_services:
        return None

    return "\n".join(
        [
            "apiVersion: image.toolkit.fluxcd.io/v1beta2",
            "kind: ImageUpdateAutomation",
            "metadata:",
            f"  name: sandbox-env-values-{environment.name}",
            "  namespace: flux-system",
            "spec:",
            "  interval: 1m",
            "  sourceRef:",
            "    kind: GitRepository",
            "    name: sandbox-env-values",
            "  git:",
            "    checkout:",
            "      ref:",
            "        branch: development",
            "    commit:",
            "      author:",
            "        email: fluxcdbot@users.noreply.github.com",
            "        name: fluxcdbot",
            "      messageTemplate: |",
            "        chore: update sandbox image tags",
            "",
            "        Automation: {{ .AutomationObject }}",
            "        Changed files:",
            "        {{- range $file, $_ := .Changed.FileChanges }}",
            "        - {{ $file }}",
            "        {{- end }}",
            "    push:",
            "      branch: development",
            "  update:",
            f"    path: ./overlays/{environment.name}",
            "    strategy: Setters",
        ]
    )


def render_image_automation_file(environments: list[EnvironmentConfig]) -> str:
    resources: list[str] = []
    for environment in environments:
        automation = render_image_update_automation(environment)
        if automation:
            resources.append(automation)
    return "\n---\n".join(resources) + ("\n" if resources else "")


def sync_cluster_environment_entries(cluster_kustomization: Path, environment_names: list[str]) -> None:
    if not cluster_kustomization.is_file():
        err(f"required file not found: {cluster_kustomization}")

    lines = cluster_kustomization.read_text(encoding="utf-8").splitlines()
    try:
        marker_index = lines.index(CLUSTER_ENV_SECTION_MARKER)
    except ValueError:
        marker_index = -1

    new_entries = [f"  - ./environments/{env}.yaml" for env in environment_names]

    if marker_index == -1:
        lines.extend(["", CLUSTER_ENV_SECTION_MARKER, *new_entries])
        cluster_kustomization.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    section_start = marker_index + 1
    section_end = section_start
    while section_end < len(lines) and (not lines[section_end].strip() or ENV_ENTRY_RE.match(lines[section_end])):
        section_end += 1

    updated_lines = lines[:section_start] + new_entries + lines[section_end:]
    cluster_kustomization.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def ensure_cluster_environment_entries_present(cluster_kustomization: Path, environment_names: list[str]) -> None:
    if not cluster_kustomization.is_file():
        err(f"required file not found: {cluster_kustomization}")

    lines = cluster_kustomization.read_text(encoding="utf-8").splitlines()
    changed = False

    for env in environment_names:
        active_line = f"  - ./environments/{env}.yaml"
        commented_line = f"#  - ./environments/{env}.yaml"

        active_indexes = [index for index, line in enumerate(lines) if line.strip() == active_line.strip()]
        if active_indexes:
            continue

        commented_indexes = [index for index, line in enumerate(lines) if line.strip() == commented_line.strip()]
        if commented_indexes:
            lines[commented_indexes[0]] = active_line
            changed = True
            continue

        inserted = False
        for index, line in enumerate(lines):
            if line == CLUSTER_ENV_SECTION_MARKER:
                lines.insert(index + 1, active_line)
                inserted = True
                changed = True
                break
        if not inserted:
            lines.extend(["", CLUSTER_ENV_SECTION_MARKER, active_line])
            changed = True

    if changed:
        cluster_kustomization.write_text("\n".join(lines) + "\n", encoding="utf-8")


def split_yaml_documents(payload: str) -> list[str]:
    docs = [part.strip() for part in payload.split("---")]
    return [doc for doc in docs if doc]


def extract_image_update_automation_name(doc: str) -> str | None:
    if not re.search(r"^kind:\s*ImageUpdateAutomation\s*$", doc, flags=re.MULTILINE):
        return None

    metadata_match = re.search(r"^metadata:\s*$([\s\S]*?)(?:^spec:\s*$|\Z)", doc, flags=re.MULTILINE)
    if not metadata_match:
        return None

    name_match = re.search(r"^\s*name:\s*([^\s#]+)\s*$", metadata_match.group(1), flags=re.MULTILINE)
    if not name_match:
        return None
    return name_match.group(1)


def merge_image_update_automation_docs(existing_payload: str, generated_payload: str) -> str:
    existing_docs = split_yaml_documents(existing_payload)
    generated_docs = split_yaml_documents(generated_payload)

    generated_by_name: dict[str, str] = {}
    for doc in generated_docs:
        name = extract_image_update_automation_name(doc)
        if name is not None:
            generated_by_name[name] = doc

    used_names: set[str] = set()
    merged_docs: list[str] = []

    for doc in existing_docs:
        name = extract_image_update_automation_name(doc)
        if name is None:
            merged_docs.append(doc)
            continue

        replacement = generated_by_name.get(name)
        if replacement is not None:
            merged_docs.append(replacement)
            used_names.add(name)
        else:
            # Keep unmanaged environments untouched.
            merged_docs.append(doc)

    for name, doc in generated_by_name.items():
        if name not in used_names:
            merged_docs.append(doc)

    if not merged_docs:
        return ""
    return "\n---\n".join(merged_docs) + "\n"


def set_flux_system_resource_reference(flux_kustomization: Path, resource_path: str, enabled: bool) -> None:
    if not flux_kustomization.is_file():
        err(f"required file not found: {flux_kustomization}")

    resource_pattern = re.compile(rf"^\s*-\s*{re.escape(resource_path)}\s*$")
    lines = flux_kustomization.read_text(encoding="utf-8").splitlines()
    filtered_lines = [line for line in lines if not resource_pattern.match(line)]

    if enabled:
        insert_index = len(filtered_lines)
        for index, line in enumerate(filtered_lines):
            if line.strip() == "- ./env-values-kustomizations.yaml":
                insert_index = index + 1
                break
        filtered_lines.insert(insert_index, f"- {resource_path}")

    flux_kustomization.write_text("\n".join(filtered_lines) + "\n", encoding="utf-8")


def apply_scaffold_config(
    config_file: Path,
    cluster_repo_root: Path,
    env_values_repo_root: Path,
    template_root: Path,
) -> ClusterScaffoldConfig:
    config = load_cluster_scaffold_config(config_file)

    cluster_dir = cluster_repo_root / "clusters" / config.cluster
    if not cluster_dir.is_dir():
        err(f"cluster directory not found: {cluster_dir}")

    env_values_overlay_template_dir = template_root / "env-values-overlay"
    cluster_kustomization = cluster_dir / "kustomization.yaml"
    flux_system_kustomization = cluster_dir / "flux-system" / "kustomization.yaml"
    env_values_kustomizations = cluster_dir / "flux-system" / "env-values-kustomizations.yaml"
    image_automation_file = cluster_dir / "flux-system" / "image-automation.yaml"

    if not env_values_overlay_template_dir.is_dir():
        err(f"required template directory not found: {env_values_overlay_template_dir}")

    for environment in config.environments:
        env_dir = cluster_dir / "environments" / environment.name
        env_manifest_file = cluster_dir / "environments" / f"{environment.name}.yaml"
        overlay_dir = env_values_repo_root / "overlays" / environment.name
        image_reflector_file = env_dir / "image-reflector.yaml"

        image_reflector_resources = render_image_reflector_resources(environment)
        has_image_reflector = bool(image_reflector_resources)

        if has_image_reflector:
            write_text_file(image_reflector_file, "\n---\n".join(image_reflector_resources) + "\n")
        elif image_reflector_file.exists():
            image_reflector_file.unlink()

        write_text_file(
            env_dir / "kustomization.yaml",
            render_environment_workload_kustomization(environment, has_image_reflector),
        )
        write_text_file(env_manifest_file, render_environment_flux_kustomization(config.cluster, environment))

        overlay_dir.mkdir(parents=True, exist_ok=True)
        write_text_file(overlay_dir / "kustomization.yaml", render_env_values_overlay_kustomization(environment))
        write_text_file(overlay_dir / "namespace.yaml", render_namespace_manifest(environment.name))

        for service in environment.services:
            definition = SERVICE_DEFINITIONS[service.name]
            if not definition.env_values_file:
                continue

            template_file = env_values_overlay_template_dir / definition.env_values_file
            if not template_file.is_file():
                err(f"required template file not found: {template_file}")
            write_template_if_missing(template_file, overlay_dir / definition.env_values_file, environment.name)
            sync_service_values_file(overlay_dir, service, environment)

    environment_names = [environment.name for environment in config.environments]
    ensure_cluster_environment_entries_present(cluster_kustomization, environment_names)
    generate_env_values_kustomizations(cluster_kustomization, env_values_kustomizations)

    image_automation_payload = render_image_automation_file(config.environments)
    existing_payload = image_automation_file.read_text(encoding="utf-8") if image_automation_file.exists() else ""
    merged_payload = merge_image_update_automation_docs(existing_payload, image_automation_payload)
    if merged_payload:
        write_text_file(image_automation_file, merged_payload)
    elif image_automation_file.exists():
        image_automation_file.unlink()
    set_flux_system_resource_reference(flux_system_kustomization, "./image-automation.yaml", bool(merged_payload))

    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Flux env-values kustomizations from enabled environments, scaffold new environments, "
            "and apply YAML-driven environment scaffolds."
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="sync",
        choices=sorted(COMMAND_CHOICES),
        help="sync updates env-values manifests; scaffold creates a legacy single environment; scaffold-config applies a YAML config",
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="environment name for scaffold or path to YAML config for scaffold-config",
    )
    parser.add_argument(
        "--env-values-repo",
        dest="env_values_repo",
        help="override path to sandbox-env-values repository",
    )
    parser.add_argument(
        "--cluster-repo-root",
        dest="cluster_repo_root",
        help="override path to sandbox-cluster-config repository",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args(normalize_argv(sys.argv)[1:])

    script_dir = Path(__file__).resolve().parent
    default_cluster_repo_root = discover_cluster_repo_root(script_dir)
    cluster_repo_root = Path(args.cluster_repo_root).resolve() if args.cluster_repo_root else default_cluster_repo_root
    repos_root = cluster_repo_root.parent
    template_root = discover_template_root(script_dir, cluster_repo_root)
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

    if args.command == "scaffold":
        if args.target is None:
            err("scaffold requires environment name")

        env = args.target
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

    if args.target is None:
        err("scaffold-config requires a YAML config file path")

    config = apply_scaffold_config(Path(args.target).resolve(), cluster_repo_root, env_values_repo_root, template_root)
    print(f"Applied scaffold config for cluster: {config.cluster}")
    print("Environments:", " ".join(environment.name for environment in config.environments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
