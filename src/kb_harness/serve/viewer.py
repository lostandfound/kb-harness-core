"""ビューアが必要とする表示情報を、既存の定義から導く。

色は表示の都合であってドメインの知識ではないため、kb-domain.yml にも
vocabulary.yml にも書かせない。型の定義順に機械的に割り当てる。順序に
基づくので、型を末尾に足しても既存の型の色は動かない。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..project import Project, ProjectError

# 深い紺黒の地で発光して見える 8 色。型の定義順に割り当てる。
# 先頭 4 色は neon-graph-design-system の neon 4 色と同じ並び。型が 8 を超えて
# 色が重なるようになったら、循環させず末尾に色を足す。
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
    """YAML を辞書として読む。壊れていれば ProjectError に包んで投げる。

    マッピング以外（リストやスカラー）が書かれていても呼び出し側を
    AttributeError で落とさず、空の定義として扱う。
    """
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ProjectError(f"{path}: invalid YAML: {error}") from error
    return data if isinstance(data, dict) else {}


def _section(data: dict, key: str) -> dict:
    """マッピングとして書かれた節だけを返す。それ以外は空とみなす。"""
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def build_viewer_config(project: Project) -> dict:
    """型の色・述語の表示名・題名をまとめた辞書を返す。"""
    vocabulary = _load_yaml(project.content_root / "vocabulary.yml")
    domain = _section(_load_yaml(project.repo_root / "kb-domain.yml"), "domain")

    types = [
        {"name": str(name), "color": PALETTE[i % len(PALETTE)]}
        for i, name in enumerate(_section(vocabulary, "types"))
    ]

    predicates = []
    for name, value in _section(vocabulary, "predicates").items():
        label = value.get("description") if isinstance(value, dict) else value
        predicates.append(
            {"name": str(name), "label": str(label) if label else str(name)}
        )

    title = domain.get("kb_title") or domain.get("name") or "knowledge base"
    return {"title": str(title), "types": types, "predicates": predicates}
