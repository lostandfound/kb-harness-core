# ビューアの静的資産

このディレクトリのファイルは、いずれもこのリポジトリで書いたものではない。出所と更新の手順を記す。

## graph.html

Claude Design（claude.ai/design）で作った知識グラフビューアのエクスポート。**エクスポート日: 2026-09-22。** 生成物に版番号が無く、これが版の同定手段になる。

取り込み時に次の改変を加えてある。`<helmet>` の Google Fonts の 3 行はエクスポートのまま残してある。

- データの埋め込み（`const RAW` / `const DESC`）を差し込み口 `__KB_GRAPH__` / `__KB_DESC__` に置き換え
- 型と述語の直書きを `__KB_VIEWER__` からの組み立てに変更
- 見出しを差し込み口 `__KB_TITLE__` に置き換え（サーバが HTML エスケープした題名を入れる）
- 語彙に無い型・述語で落ちないよう `typeOf()` / `predLabel()` を通す
- `support.js` の参照を絶対パス `/support.js` に変更

更新するときは Claude Design で再エクスポートし、上の 6 点を適用し直す。エクスポート日もこの節に書き直す。

**書体について:** `JetBrains Mono` と `Noto Sans JP` は Google Fonts から読む。ここだけが唯一の外部依存で、届かなければ `monospace` / `sans-serif` に落ちるだけなので描画は壊れない。同梱しないのは、配布物が重くなるのとライセンス表記が要るのを避けるため。描画に必要な JavaScript は同梱してあり、ネットのない場所でもグラフは出る。

## support.js

Claude Design の dc ランタイム。冒頭に `GENERATED from dc-runtime/src/*.ts — do not edit` とあるとおり、正本は Anthropic 側にあり、このリポジトリでは編集しない。再エクスポートで丸ごと差し替える。

**エクスポート日: 2026-09-22**（`graph.html` と同時に取得）。

**制約:** 壊れたときにこちらで直す手段がない。将来この依存を外すなら、graphology + sigma.js による実装へ移す。

## vendor/

`support.js` が実行時に unpkg から読む React を、ネットのない場所でも動くよう同梱したもの。取得元は次のとおり。

- `react.production.min.js` — https://unpkg.com/react@18.3.1/umd/react.production.min.js
- `react-dom.production.min.js` — https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js

`support.js` の取得先の差し替えは `graph.html` 冒頭の `window.__resources` で行う。版を上げるときは、`support.js` の `REACT_SRI` / `REACT_DOM_SRI` と同梱物の SHA-384 が一致することを確認する（`tests/test_serve_assets.py` が検査する）。
