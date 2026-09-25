"""Build a generic, read-only flashcard payload from any configured KB."""

from __future__ import annotations

import yaml

from .graph import export_graph
from .markdown import parse_document
from .project import Project


def export_flashcards(project: Project) -> dict[str, object]:
    graph = export_graph(project.content_root)
    entities: dict[str, dict[str, object]] = {}
    for node in graph["nodes"]:
        path = str(node["path"])
        source = project.content_root / path.lstrip("/")
        document = parse_document(str(source), source.read_text(encoding="utf-8"))
        entities[path] = {
            "id": path,
            "title": node.get("title") or source.stem,
            "type": node.get("type") or "",
            "description": node.get("description") or "",
            "details": document.body,
            "tags": node.get("tags") or [],
            "related": [],
        }

    for edge in graph["edges"]:
        source = entities.get(str(edge["source"]))
        target = entities.get(str(edge["target"]))
        if source and target:
            relation = str(edge["predicate"])
            source["related"].append({"id": target["id"], "title": target["title"], "relation": relation})
            target["related"].append({"id": source["id"], "title": source["title"], "relation": relation})

    for entity in entities.values():
        entity["related"].sort(key=lambda item: item["title"])

    config = yaml.safe_load((project.repo_root / "kb-domain.yml").read_text(encoding="utf-8")) or {}
    domain = config.get("domain") or {}
    return {
        "title": domain.get("kb_title") or domain.get("name") or project.repo_root.name,
        "tagLabels": project.tag_labels,
        "entities": list(entities.values()),
    }
