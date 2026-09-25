"""ビューアが必要とする表示情報を、既存の定義から導く。

色は表示の都合であってドメインの知識ではないため、kb-domain.yml にも
vocabulary.yml にも書かせない。型の定義順に機械的に割り当てる。順序に
基づくので、型を末尾に足しても既存の型の色は動かない。
"""

from __future__ import annotations

import colorsys
from pathlib import Path

import yaml

from ..project import Project, ProjectError

# 深い紺黒の地で発光して見える 12 色。型の定義順に割り当てる。
# 先頭 4 色は neon-graph-design-system の neon 4 色と同じ並び。以降は色相の
# 空いたところを埋める順に足してある。
PALETTE = (
    "#f5a524",
    "#22d3ee",
    "#a78bfa",
    "#34d399",
    "#f472b6",
    "#facc15",
    "#38bdf8",
    "#fb923c",
    "#f87171",
    "#a3e635",
    "#e879f9",
    "#60a5fa",
)
# パレットを使い切った後の色相の歩幅（黄金角）。循環させると別の型と同色になるので、
# 色相を少しずつずらして生成し続ける。
GOLDEN_ANGLE = 137.508


def _color(index: int) -> str:
    """型の順番から色を決める。パレットの外は彩度と明度を揃えて色相だけを回す。"""
    if index < len(PALETTE):
        return PALETTE[index]
    hue = ((index - len(PALETTE)) * GOLDEN_ANGLE + 15) % 360 / 360
    r, g, b = colorsys.hls_to_rgb(hue, 0.64, 0.86)
    return "#" + "".join(f"{round(c * 255):02x}" for c in (r, g, b))


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
        {"name": str(name), "color": _color(i)}
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
