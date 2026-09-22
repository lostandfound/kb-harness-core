# ビューアの静的資産

このディレクトリのファイルは、いずれもこのリポジトリで書いたものではない。出所と更新の手順を記す。

## graph.html

Claude Design（claude.ai/design）で作った知識グラフビューアのエクスポート。取り込み時に次の改変を加えてある。

- データの埋め込み（`const RAW` / `const DESC`）を差し込み口 `__KB_GRAPH__` / `__KB_DESC__` に置き換え
- 型と述語の直書きを `__KB_VIEWER__` からの組み立てに変更
- 見出しを知識ベースの題名で差し替え
- `support.js` の参照を絶対パス `/support.js` に変更

更新するときは Claude Design で再エクスポートし、上の 4 点を適用し直す。

## support.js

Claude Design の dc ランタイム。冒頭に `GENERATED from dc-runtime/src/*.ts — do not edit` とあるとおり、正本は Anthropic 側にあり、このリポジトリでは編集しない。再エクスポートで丸ごと差し替える。

**制約:** 壊れたときにこちらで直す手段がない。将来この依存を外すなら、graphology + sigma.js による実装へ移す。

## vendor/

`support.js` が実行時に unpkg から読む React を、ネットのない場所でも動くよう同梱したもの。取得元は次のとおり。

- `react.production.min.js` — https://unpkg.com/react@18.3.1/umd/react.production.min.js
- `react-dom.production.min.js` — https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js

`support.js` の取得先の差し替えは `graph.html` 冒頭の `window.__resources` で行う。版を上げるときは、`support.js` の `REACT_SRI` / `REACT_DOM_SRI` と同梱物の SHA-384 が一致することを確認する（`tests/test_serve_assets.py` が検査する）。
