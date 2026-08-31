#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from kb_config import default_content_root
from validate import _load_types

SECTIONS_BY_TYPE = {
    "Person": ["概要", "生涯", "系譜（師と弟子）", "功績"],
    "Style": ["概要", "特徴", "主要人物", "代表的な型"],
    "Kata": ["概要", "由来", "特徴", "伝承する流派"],
    "Term": ["概要", "詳細", "関連項目"],
    "HistoricalEvent": ["概要", "詳細", "関連項目"],
    "Note": ["概要", "本文", "関連項目"],
}

DEFAULT_SECTIONS = ["概要", "詳細", "関連項目"]


def new_entity(root: Path, type_key: str, slug: str) -> Path:
    types = _load_types(root)
    type_map = {name.lower(): (t["directory"], name) for name, t in types.items()}
    if type_key not in type_map:
        raise ValueError(f"unknown type '{type_key}' (expected one of {sorted(type_map)})")
    dirname, entity_type = type_map[type_key]
    path = root / dirname / f"{slug}.md"
    if path.exists():
        raise ValueError(f"entity already exists: {path}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    section_names = (
        types[entity_type]["sections"]
        or SECTIONS_BY_TYPE.get(entity_type)
        or DEFAULT_SECTIONS
    )
    sections = "\n".join(f"## {name}\n\nTODO\n" for name in section_names)
    extra_fields = types[entity_type]["extra_fields"]
    person_fields = "".join(f"{field}: TODO\n" for field in extra_fields)
    text = (
        "---\n"
        f"type: {entity_type}\n"
        "title: TODO\n"
        "description: TODO\n"
        "tags: []\n"
        "aliases: []\n"
        f"timestamp: {now}\n"
        "sources:\n"
        "  - TODO\n"
        f"{person_fields}"
        "---\n"
        "\n"
        f"{sections}"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("type")
    parser.add_argument("slug")
    parser.add_argument("--root", default=default_content_root())
    args = parser.parse_args()

    try:
        path = new_entity(Path(args.root), args.type, args.slug)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"created {path}")
    print("次: 本文を書き、python3 scripts/generate_index.py と python3 scripts/validate.py を実行")


if __name__ == "__main__":
    main()
