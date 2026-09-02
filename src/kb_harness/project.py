"""KB project discovery and path resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class ProjectError(ValueError):
    """Raised when a KB project cannot be discovered or is misconfigured."""

    def __init__(self, message: str, *, code: str = "project.invalid_config"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Project:
    repo_root: Path
    content_root: Path

    @classmethod
    def discover(cls, start: str | Path | None = None) -> "Project":
        current = Path(start or Path.cwd()).resolve()
        if current.is_file():
            current = current.parent

        for candidate in (current, *current.parents):
            config_path = candidate / "kb-domain.yml"
            if config_path.is_file():
                return cls.from_config(config_path)

        raise ProjectError(
            f"kb-domain.yml not found from {current}",
            code="project.not_found",
        )

    @classmethod
    def from_config(cls, config_path: str | Path) -> "Project":
        path = Path(config_path).resolve()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise ProjectError(f"{path}: invalid YAML: {error}") from error
        domain = data.get("domain") if isinstance(data, dict) else None
        content_root = domain.get("content_root") if isinstance(domain, dict) else None
        if not isinstance(content_root, str) or not content_root.strip():
            raise ProjectError(
                f"{path}: domain.content_root must be a non-empty string"
            )
        return cls(repo_root=path.parent, content_root=path.parent / content_root)
