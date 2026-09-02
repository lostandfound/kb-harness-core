"""Deterministic graph export and synchronization."""

from __future__ import annotations

import json
from pathlib import Path

from .ontology import export_claim
from .validation import _load_types, _parse_frontmatter


def export_graph(root: Path, warnings: list[str] | None = None) -> dict[str, object]:
    root = root.resolve()
    types = _load_types(root)
    non_graph_types = {
        name for name, definition in types.items() if not definition.get("graph", True)
    }
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    referenced: set[str] = set()

    for path in sorted(root.rglob("*.md")):
        frontmatter, _body, error = _parse_frontmatter(path)
        if error or frontmatter is None:
            continue
        entity_type = frontmatter.get("type")
        relative_path = "/" + str(path.relative_to(root))
        if entity_type == "Claim":
            claims.append(export_claim(relative_path, frontmatter))
            subject = frontmatter.get("subject")
            object_path = frontmatter.get("object")
            if isinstance(subject, str):
                referenced.add(subject)
            if isinstance(object_path, str):
                referenced.add(object_path)
            continue
        if entity_type == "Index" or entity_type in non_graph_types:
            continue
        nodes.append(
            {
                "path": relative_path,
                "type": entity_type,
                "title": frontmatter.get("title"),
                "description": frontmatter.get("description"),
                "tags": frontmatter.get("tags") or [],
            }
        )
        for relation in frontmatter.get("relations") or []:
            if not isinstance(relation, dict):
                continue
            predicate = relation.get("predicate")
            target = relation.get("target")
            if not isinstance(predicate, str) or not isinstance(target, str):
                continue
            edge: dict[str, object] = {
                "source": relative_path,
                "predicate": predicate,
                "target": target,
            }
            if relation.get("confidence") == "C":
                edge["confidence"] = "C"
            edges.append(edge)
            referenced.add(relative_path)
            referenced.add(target)

    nodes.sort(key=lambda node: str(node["path"]))
    edges.sort(
        key=lambda edge: (
            str(edge["source"]),
            str(edge["predicate"]),
            str(edge["target"]),
            str(edge.get("confidence", "")),
        )
    )
    claims.sort(key=lambda claim: str(claim["path"]))

    if warnings is not None:
        for node in nodes:
            if node["path"] not in referenced:
                warnings.append(f"isolated: {node['path']}")

    return {"nodes": nodes, "edges": edges, "claims": claims}


def render_graph(root: Path) -> str:
    return json.dumps(export_graph(root), ensure_ascii=False, indent=2) + "\n"


def plan_graph(root: Path, output_path: Path) -> dict[Path, str]:
    output = output_path.resolve()
    rendered = render_graph(root)
    current = output.read_text(encoding="utf-8") if output.is_file() else None
    if current == rendered:
        return {}
    return {output: rendered}
