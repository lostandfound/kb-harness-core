"""ドメイン非依存のハーネス各スクリプトが共有する設定ヘルパー。

`--root` のデフォルト値をハードコードせず、リポジトリルートの kb-domain.yml
（ドメイン定義）から content_root を読み取ることで、別ドメインの KB でも
このパッケージをそのまま使い回せるようにする。
"""
from pathlib import Path

import yaml


def default_content_root(start: Path | None = None) -> str:
    """start（省略時はこのファイルの親のリポジトリルート想定位置）から上に
    辿って kb-domain.yml を探し、domain.content_root を返す。"""
    if start is None:
        start = Path(__file__).resolve().parent.parent
    start = start.resolve()

    for candidate in (start, *start.parents):
        kb_domain_path = candidate / "kb-domain.yml"
        if kb_domain_path.exists():
            data = yaml.safe_load(kb_domain_path.read_text(encoding="utf-8")) or {}
            content_root = (data.get("domain") or {}).get("content_root")
            if not content_root:
                raise FileNotFoundError(
                    f"kb-domain.yml に domain.content_root が定義されていない: {kb_domain_path}"
                )
            return content_root

    raise FileNotFoundError(
        f"kb-domain.yml が見つからない（{start} から上に探索した）"
    )
