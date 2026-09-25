# ビューアの静的資産

`graph.html` は Sigma.js と Graphology を使う知識グラフビューアである。依存ライブラリは `vendor/` に同梱し、外部ランタイム、CDN、Claude Design の再エクスポートには依存しない。

`graph.json` のデータは `__KB_GRAPH__` / `__KB_DESC__`、型・述語・題名は `__KB_VIEWER__` / `__KB_TITLE__` の差し込み口からサーバが埋め込む。

ビューアは検索、型フィルタ、ノード選択、関係表示、ズーム、パンを提供する。ライセンスは `vendor/*-LICENSE.txt` に置く。
