#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from kb_config import default_content_root
try:
    from kb_harness.entity import create_entity
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from kb_harness.entity import create_entity


new_entity = create_entity


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
