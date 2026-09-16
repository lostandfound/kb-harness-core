"""KB project discovery and path resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    # kb-domain.yml の任意セクション index:。未指定なら無効（従来と同じ挙動）。
    index_by_tag: bool = False
    tag_labels: dict[str, str] = field(default_factory=dict)
    # kb-domain.yml の任意セクション validate.extra_checks:。kb validate が repo_root で順に実行する。
    extra_checks: tuple[str, ...] = ()

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
        index = data.get("index") if isinstance(data.get("index"), dict) else {}
        raw_labels = index.get("tag_labels") if isinstance(index.get("tag_labels"), dict) else {}
        tag_labels = {str(key): str(value) for key, value in raw_labels.items()}
        validate_section = data.get("validate") if isinstance(data.get("validate"), dict) else {}
        raw_checks = validate_section.get("extra_checks") or []
        if not isinstance(raw_checks, list) or not all(
            isinstance(command, str) and command.strip() for command in raw_checks
        ):
            raise ProjectError(
                f"{path}: validate.extra_checks must be a list of non-empty strings"
            )
        return cls(
            repo_root=path.parent,
            content_root=path.parent / content_root,
            index_by_tag=bool(index.get("by_tag", False)),
            tag_labels=tag_labels,
            extra_checks=tuple(raw_checks),
        )
