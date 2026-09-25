# ビューアの静的資産

`graph.html` は Sigma.js と Graphology を使う知識グラフビューアである。ノードの配置は graphology-library の ForceAtlas2 と noverlap で、表示前にブラウザ上で計算する。依存ライブラリは `vendor/` に、見た目の定義は `ds/` に同梱し、外部ランタイム、CDN、Claude Design の再エクスポートには依存しない。

`graph.json` のデータは `__KB_GRAPH__` / `__KB_DESC__`、型・述語・題名は `__KB_VIEWER__` / `__KB_TITLE__` の差し込み口からサーバが埋め込む。

ビューアは検索、型フィルタ、ノード選択、関係表示、ズーム、パンを提供する。ライセンスは `vendor/*-LICENSE.txt` と `ds/assets/fonts/OFL.txt` に置く。

## ds/

[lostandfound/neon-graph-design-system](https://github.com/lostandfound/neon-graph-design-system) のトークンと書体を写したもの。**取得元コミット: `45d89f6f7079720feadfdb764dace3c4aa99c20c`。**

写したのは `styles.css`、`tokens/*.css`、JetBrains Mono の woff2 だけである。React コンポーネント（`components/`）と UI kit は持ち込まない。ブラウザ上で JSX を変換する前提で、ノードを DOM 要素として描くため、Sigma.js の WebGL 描画と両立しない。コンポーネントの見た目は `graph.html` の CSS で再現している。

上流から次の点を変えている。

- `tokens/fonts.css` から Noto Sans JP の Google Fonts 読み込みを外した。日本語は `graph.html` の `--font-sans` で各 OS の日本語書体へ落とす
- JetBrains Mono は可変フォントで、上流の 400 / 500 / 700 は同一ファイルだった。字形範囲ごとに 1 ファイル（`JetBrainsMono-latin.woff2` / `JetBrainsMono-latin-ext.woff2`）へ畳み、`font-weight: 400 700` で宣言した
- 型の色トークン（`--type-course` など）は上流の題材に固有なので使わない。型の色は `viewer.py` の `PALETTE` から型の定義順に割り当てる。先頭 4 色は上流の neon 4 色と同じ並びである。パレットを超えた型には、色相を黄金角ずつ回した色を生成する

更新するときは上流の同じファイルを写し直し、上の変更を適用し直す。取得元コミットもこの節に書き直す。サーバは `ds/` 配下を固定の対応表（`server.py` の `DS`）でだけ配るので、ファイルを足したら対応表と `pyproject.toml` の package-data も更新する。
