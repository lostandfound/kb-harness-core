"""Combined deterministic synchronization for derived KB artifacts."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Mapping

from .graph import plan_graph
from .index import plan_index
from .project import Project


def plan_sync(project: Project) -> dict[Path, str]:
    changes = {
        **plan_index(project.content_root),
        **plan_graph(project.content_root, project.repo_root / "graph.json"),
    }
    return dict(sorted(changes.items(), key=lambda item: str(item[0])))


def apply_changes_atomically(changes: Mapping[Path, str]) -> list[Path]:
    """Replace generated files as one rollback-capable operation."""
    originals: dict[Path, bytes | None] = {
        path: path.read_bytes() if path.exists() else None for path in changes
    }
    temporary: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for path, text in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
            )
            temporary[path] = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        for path in changes:
            temporary[path].replace(path)
            replaced.append(path)
        return replaced
    except OSError:
        for path in reversed(replaced):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)
