"""Combined deterministic synchronization for derived KB artifacts."""

from __future__ import annotations

import os
import tempfile
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .graph import plan_graph
from .index import plan_index
from .project import Project


@dataclass(frozen=True)
class WritePlan:
    """A side-effect-free description of one write action.

    All CLI write commands use this small adapter, even when their domain
    planners return a richer plan type.  Keeping the plan as a mapping makes
    it possible to combine a primary document with derived artifacts while
    retaining one diff and one atomic apply operation.
    """

    changes: dict[Path, str]
    diff: str


def unified_diff(
    changes: Mapping[Path, str], *, display_root: Path | None = None
) -> str:
    """Return a deterministic unified diff for prospective writes.

    ``display_root`` is deliberately separate from the paths used for the
    actual write.  CLI previews must not leak checkout-specific absolute
    paths (or temporary staging directories) into otherwise deterministic
    output.
    """
    chunks: list[str] = []
    root = display_root.resolve() if display_root is not None else None
    for path, new_text in sorted(changes.items(), key=lambda item: str(item[0])):
        # Read bytes to avoid changing the preview merely because Python
        # normalizes CRLF while decoding text.
        old_text = path.read_bytes().decode("utf-8") if path.is_file() else ""
        label = path
        if root is not None:
            try:
                label = path.resolve().relative_to(root)
            except ValueError:
                # A caller supplied an out-of-root path.  Keep it visible for
                # library users rather than silently producing a misleading
                # relative label; project-bound CLI plans never take this
                # branch because their paths are containment-checked first.
                label = path
        chunks.extend(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{label}",
                tofile=f"b/{label}",
            )
        )
    return "".join(chunks)


def plan_write(
    changes: Mapping[Path, str],
    *,
    diff: str | None = None,
    display_root: Path | None = None,
) -> WritePlan:
    """Normalize a planner result into the common write-plan representation."""
    normalized = dict(sorted(changes.items(), key=lambda item: str(item[0])))
    rendered_diff = (
        unified_diff(normalized, display_root=display_root)
        if display_root is not None or diff is None
        else diff
    )
    return WritePlan(normalized, rendered_diff)


def execute_write_plan(
    plan: WritePlan,
    *,
    dry_run: bool = False,
    apply: Callable[[Mapping[Path, str]], list[Path]] | None = None,
) -> list[Path]:
    """Apply a plan atomically, or return without touching disk for dry-run."""
    if dry_run or not plan.changes:
        return []
    return (apply or apply_changes_atomically)(plan.changes)


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
    except Exception:
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
