#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from kb_config import default_content_root
from validate import _load_types, _parse_frontmatter, validate


def export_graph(root: Path) -> dict:
    nodes = []
    edges = []
    claims = []
    referenced = set()
    types = _load_types(root)
    non_graph_types = {name for name, t in types.items() if not t["graph"]}

    for path in sorted(root.rglob("*.md")):
        fm, _body, err = _parse_frontmatter(path)
        if err or fm is None:
            continue
        entity_type = fm.get("type")
        rel = "/" + str(path.relative_to(root))
        if entity_type == "Claim":
            claims.append({
                "path": rel,
                "subject": fm.get("subject"),
                "predicate": fm.get("predicate"),
                "object": fm.get("object"),
                "status": fm.get("status"),
                "confidence": fm.get("confidence"),
                "sources": fm.get("sources") or [],
            })
            referenced.add(fm.get("subject"))
            referenced.add(fm.get("object"))
            continue
        if entity_type == "Index" or entity_type in non_graph_types:
            continue
        nodes.append({
            "path": rel,
            "type": fm.get("type"),
            "title": fm.get("title"),
            "description": fm.get("description"),
            "tags": fm.get("tags") or [],
        })
        for rel_entry in fm.get("relations") or []:
            if not isinstance(rel_entry, dict):
                continue
            predicate = rel_entry.get("predicate")
            target = rel_entry.get("target")
            if predicate is None or target is None:
                continue
            edge = {"source": rel, "predicate": predicate, "target": target}
            if rel_entry.get("confidence") == "C":
                edge["confidence"] = "C"
            edges.append(edge)
            referenced.add(rel)
            referenced.add(target)

    for node in nodes:
        if node["path"] not in referenced:
            print(f"WARN isolated: {node['path']}", file=sys.stderr)

    return {"nodes": nodes, "edges": edges, "claims": claims}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=default_content_root())
    parser.add_argument("--out")
    parser.add_argument("--force", action="store_true", help="validate() をスキップする（デバッグ用）")
    args = parser.parse_args()

    root = Path(args.root)

    if not args.force:
        errors = validate(root)
        if errors:
            for e in errors:
                print(e, file=sys.stderr)
            sys.exit(1)

    graph = export_graph(root)
    output = json.dumps(graph, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
