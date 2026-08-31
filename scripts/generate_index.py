#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

from kb_config import default_content_root
from validate import _load_types, _parse_frontmatter

SECTION_HEADING = "## エンティティ一覧"
SECTION_RE = re.compile(
    r"(^## エンティティ一覧\n)(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
)
COUNT_LINE_RE = re.compile(r"(\[[^\]]+\]\(/(\w+)/index\.md\))（\d+件）")


def _entity_lines(dir_path: Path) -> str:
    entries = []
    for path in sorted(dir_path.glob("*.md")):
        if path.name == "index.md":
            continue
        fm, _body, err = _parse_frontmatter(path)
        if err:
            continue
        title = fm.get("title", path.stem)
        description = fm.get("description", "")
        entries.append(f"- [{title}](/{dir_path.name}/{path.name}) — {description}\n")
    return "".join(entries)


def _update_dir_index(dir_path: Path) -> bool:
    idx_path = dir_path / "index.md"
    if not idx_path.exists():
        return False
    text = idx_path.read_text(encoding="utf-8")
    listing = _entity_lines(dir_path)

    if SECTION_RE.search(text):
        replacement = ("\n" + listing) if listing else ""
        new_text = SECTION_RE.sub(lambda m: m.group(1) + replacement, text, count=1)
    else:
        sep = "" if text.endswith("\n") else "\n"
        new_text = f"{text}{sep}{SECTION_HEADING}\n\n{listing}"

    if new_text == text:
        return False
    idx_path.write_text(new_text, encoding="utf-8")
    return True


def _update_root_index(root: Path) -> bool:
    idx_path = root / "index.md"
    if not idx_path.exists():
        return False
    text = idx_path.read_text(encoding="utf-8")

    def repl(m: re.Match) -> str:
        link, dirname = m.group(1), m.group(2)
        dir_path = root / dirname
        if not dir_path.is_dir():
            return m.group(0)
        count = sum(1 for p in dir_path.glob("*.md") if p.name != "index.md")
        return f"{link}（{count}件）"

    new_text = COUNT_LINE_RE.sub(repl, text)
    if new_text == text:
        return False
    idx_path.write_text(new_text, encoding="utf-8")
    return True


def generate_index(root: Path) -> list[Path]:
    updated: list[Path] = []
    types = _load_types(root)
    dirnames = [t["directory"] for t in types.values()]
    for dirname in dirnames:
        dir_path = root / dirname
        if dir_path.is_dir() and _update_dir_index(dir_path):
            updated.append(dir_path / "index.md")
    if _update_root_index(root):
        updated.append(root / "index.md")
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=default_content_root())
    args = parser.parse_args()

    updated = generate_index(Path(args.root))
    for path in updated:
        print(f"updated {path}")


if __name__ == "__main__":
    main()
