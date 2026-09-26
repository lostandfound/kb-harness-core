# BACKLOG

ハーネス自身の作業台帳。導入先 KB の `docs/BACKLOG.md`（[integration.md](docs/integration.md#8-運用ファイルを置く任意)）とは別物で、`docs/` の外に置く。`docs/` は導入先への対外契約であり、`apm_modules/` 経由で導入先のエージェントが読むためである。APM の配布対象（`.apm/` 配下）にも含まれない。

## 書き方

- 1 項目につきチェックボックス 1 行。実装と検証が終わったら `[x]` にしてコミットを付記する。
- 出所を書く（ディスカッション、導入先からの要望、監査、考察メモの未決事項）。
- 設計判断の保留は考察メモ（`docs/notes/`）の「未決事項」節が正本で、ここには写さない。着手を決めた時点で 1 行に起こしてここへ移す。

## 未着手

- [ ] `Unreleased` をタグ付きリリースにし、omnibus-kb の `apm.yml` の固定コミットを上げて `apm install` で `.claude/agents/evidence-reviewer.md` を再生成する。`kb reference show` を前提とする evidence-reviewer は、これが済むまで導入先で効かない。（出所: 2026-09-27 ディスカッション）
- [ ] `scripts/refs_health.py`（`lineage` 未判定・`pending` 滞留・到達確認の記録）を `kb reference` に統合するか決める。`kb reference health` は構造検査だけで、`lineage` の運用を促す入口が `docs/scripts.md` の 1 行しかない。この周知不足が `lineage` を 2 週間以上孤児にした。（出所: 2026-09-27 ディスカッション）
- [ ] evidence-reviewer が「`lineage` の付与を提案」した後、それを `references.yml` に反映する担い手と手順を決める。既存エントリへの `lineage` 追記は `kb reference create` の範囲外で、今は手編集しかない。（出所: 2026-09-27 ディスカッション）
- [ ] 導入先の `references.yml` が数千件に達したときの分割方針を決める。現状は単一ファイル前提（`kb reference create` の追記、`validation.reference.unreferenced`）で、`kb reference show / search` により文脈消費の問題は解消済みなので急がない。（出所: 2026-09-27 ディスカッション）

## 完了

- [x] `kb reference show ID... / --for ENTITY` と `kb reference search` を追加し、エージェントが `references.yml` を丸ごと読まずに書誌を引けるようにした。evidence-reviewer と find-book / find-paper / add-entity の手順を対応させた。（出所: 2026-09-27 ディスカッション。コミット: e6a33d9, 67ba53c）
- [x] `references.yml` の `lineage` を「同じ由来の資料群のラベル」として汎用化し、設定リファレンスに必須キーと合わせて明記、find-book / find-paper / add-entity に付与手順を戻した。（出所: 同上。コミット: 7b952a5, 67ba53c）

## 保留した判断（考察メモの未決事項）

正本は各メモの「未決事項」節。ここは所在の一覧だけを持つ。

- [フィールドのプリセット化](docs/notes/field-preset-memo.md#未決事項) — 年表現の定義がハーネスとオントロジーコアで食い違う。`same_as` による突合。`query` ビューへのフィールド条件
- [型の標準化](docs/notes/hyojun-kata-memo.md#未決事項) — 型の `maps_to` を足す時点。`Organization` / `Place` を持つ KB が現れたときの層 2 の扱い
- [述語の階層](docs/notes/jutsugo-kaisou-memo.md#未決事項) — 標準述語の改版規則。層 2 の追加条件。既存述語の移行支援。CURIE 展開表の置き場。対称な関係
- [関係をあとから見出す](docs/notes/kankei-hakken-memo.md#未決事項) — ハブ Concept を立てる閾値。出典由来 / 解釈由来の明示を規約に載せるか
