#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from kb_config import default_content_root
# 同じチェックアウトの src を pip で入った kb_harness より優先する。導入先で古い版が
# 入っていると、try/except の import は成功してしまい submodule の修正が効かない
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
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
