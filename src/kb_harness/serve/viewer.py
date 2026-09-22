"""ビューアが必要とする表示情報を、既存の定義から導く。

色は表示の都合であってドメインの知識ではないため、kb-domain.yml にも
vocabulary.yml にも書かせない。型の定義順に機械的に割り当てる。順序に
基づくので、型を末尾に足しても既存の型の色は動かない。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..project import Project

# 深い紺黒の地で発光して見える 8 色。型の定義順に割り当てる。
PALETTE = (
    "#f5a524",
    "#22d3ee",
    "#a78bfa",
    "#34d399",
    "#f472b6",
    "#facc15",
    "#38bdf8",
    "#fb923c",
)


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_viewer_config(project: Project) -> dict:
    """型の色・述語の表示名・題名をまとめた辞書を返す。"""
    vocabulary = _load_yaml(project.content_root / "vocabulary.yml")
    domain = _load_yaml(project.repo_root / "kb-domain.yml").get("domain") or {}

    types = [
        {"name": str(name), "color": PALETTE[i % len(PALETTE)]}
        for i, name in enumerate((vocabulary.get("types") or {}).keys())
    ]

    predicates = []
    for name, value in (vocabulary.get("predicates") or {}).items():
        label = value.get("description") if isinstance(value, dict) else value
        predicates.append(
            {"name": str(name), "label": str(label) if label else str(name)}
        )

    title = domain.get("kb_title") or domain.get("name") or "knowledge base"
    return {"title": str(title), "types": types, "predicates": predicates}
