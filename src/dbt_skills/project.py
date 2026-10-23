"""Safe discovery and minimal configuration for a local dbt project."""

from __future__ import annotations

import math
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import yaml


class ProjectError(RuntimeError):
    """Raised when a dbt project or its local runtime config is invalid."""


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    root: Path
    config_path: Path
    name: str
    version: str | None
    profile: str | None
    manifest_path: Path
    manifest_available: bool

    def to_json(self) -> dict[str, object]:
        return {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(self).items()
        }


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    provider: str
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: float


def discover_project(
    start: str | Path = ".", *, target_path: str | Path | None = None
) -> ProjectInfo:
    candidate = Path(start).expanduser().resolve()
    if not candidate.is_dir():
        raise ProjectError(f"Project path is not a directory: {candidate}")

    config_path = next(
        (
            parent / "dbt_project.yml"
            for parent in (candidate, *candidate.parents)
            if (parent / "dbt_project.yml").is_file()
        ),
        None,
    )
    if config_path is None:
        raise ProjectError(f"No dbt_project.yml found at or above {candidate}")

    try:
        with config_path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except OSError as error:
        raise ProjectError(f"Cannot read dbt project config {config_path}: {error}") from error
    except yaml.YAMLError as error:
        raise ProjectError(
            f"Invalid YAML in dbt project config {config_path} ({type(error).__name__})"
        ) from None
    if not isinstance(config, Mapping):
        raise ProjectError(f"dbt project config must contain a YAML mapping: {config_path}")
    name = config.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ProjectError(f"dbt project config has no non-empty string 'name': {config_path}")
    version_value = config.get("version")
    version = str(version_value) if isinstance(version_value, (str, int, float)) else None
    profile_value = config.get("profile")
    profile = profile_value if isinstance(profile_value, str) and profile_value.strip() else None
    root = config_path.parent
    target = target_path if target_path is not None else config.get("target-path", "target")
    if isinstance(target, Path):
        target = str(target)
    if not isinstance(target, str) or not target.strip():
        raise ProjectError("target-path must be a non-empty literal path")
    if any(marker in target for marker in ("{{", "{%", "{#")) or "\x00" in target:
        raise ProjectError("Cannot resolve target-path; supply an explicit literal target path")
    manifest_path = (root / target).resolve() / "manifest.json"
    return ProjectInfo(
        root=root,
        config_path=config_path,
        name=name,
        version=version,
        profile=profile,
        manifest_path=manifest_path,
        manifest_available=manifest_path.is_file(),
    )


def initialize_project(start: str | Path = ".", *, target_path: str | Path | None = None) -> Path:
    project = discover_project(start, target_path=target_path)
    config_dir = project.root / ".dbt-skills"
    if config_dir.is_symlink():
        raise ProjectError(f"Refusing to write through a symlink: {config_dir}")
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "config.toml"
    content = """# Local runtime settings. Credentials are read only from environment variables.
[model]
provider = "openai-compatible"
base_url = "http://127.0.0.1:11434/v1"
model = ""
api_key_env = "OPENAI_API_KEY"
timeout_seconds = 60
"""
    try:
        with config_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except FileExistsError as error:
        raise ProjectError(f"Runtime config already exists: {config_path}") from error
    except OSError as error:
        raise ProjectError(f"Cannot create runtime config {config_path}: {error}") from error
    return config_path


def load_runtime_config(project: ProjectInfo) -> RuntimeConfig:
    path = project.root / ".dbt-skills" / "config.toml"
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except FileNotFoundError as error:
        raise ProjectError(f"Runtime config is missing; run 'init' for {project.root}") from error
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ProjectError(f"Cannot read runtime config {path}: {error}") from error
    model = document.get("model")
    if not isinstance(model, Mapping):
        raise ProjectError(f"Runtime config must contain a [model] table: {path}")

    provider = model.get("provider", "openai-compatible")
    base_url = model.get("base_url", "http://127.0.0.1:11434/v1")
    model_name = model.get("model", "")
    api_key_env = model.get("api_key_env", "OPENAI_API_KEY")
    timeout = model.get("timeout_seconds", 60)
    if provider != "openai-compatible":
        raise ProjectError(f"Unsupported model provider: {provider}")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ProjectError("model.base_url must be a non-empty string")
    if not isinstance(model_name, str):
        raise ProjectError("model.model must be a string")
    if not isinstance(api_key_env, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", api_key_env
    ):
        raise ProjectError("model.api_key_env must be an environment variable name")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ProjectError("model.timeout_seconds must be a finite positive number")
    return RuntimeConfig(
        provider=provider,
        base_url=base_url.strip(),
        model=model_name.strip(),
        api_key_env=api_key_env,
        timeout_seconds=float(timeout),
    )
