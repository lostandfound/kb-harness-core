# BACKLOG

ハーネス自身の作業台帳。導入先 KB の `docs/BACKLOG.md`（[integration.md](docs/integration.md#8-運用ファイルを置く任意)）とは別物で、`docs/` の外に置く。`docs/` は導入先への対外契約であり、`apm_modules/` 経由で導入先のエージェントが読むためである。APM の配布対象（`.apm/` 配下）にも含まれない。

## 書き方

- 1 項目につきチェックボックス 1 行。実装と検証が終わったら `[x]` にしてコミットを付記する。
- 出所を書く（ディスカッション、導入先からの要望、監査、考察メモの未決事項）。
- 設計判断の保留は考察メモ（`docs/notes/`）の「未決事項」節が正本で、ここには写さない。着手を決めた時点で 1 行に起こしてここへ移す。

## 未着手

- [ ] `scripts/refs_health.py`（`lineage` 未判定・`pending` 滞留・到達確認の記録）を `kb reference` に統合するか決める。`kb reference health` は構造検査だけで、`lineage` の運用を促す入口が `docs/scripts.md` の 1 行しかない。この周知不足が `lineage` を 2 週間以上孤児にした。（出所: 2026-09-27 ディスカッション）
- [ ] evidence-reviewer が「`lineage` の付与を提案」した後、それを `references.yml` に反映する担い手と手順を決める。既存エントリへの `lineage` 追記は `kb reference create` の範囲外で、今は手編集しかない。（出所: 2026-09-27 ディスカッション）
- [ ] 導入先の `references.yml` が数千件に達したときの分割方針を決める。現状は単一ファイル前提（`kb reference create` の追記、`validation.reference.unreferenced`）で、`kb reference show / search` により文脈消費の問題は解消済みなので急がない。（出所: 2026-09-27 ディスカッション）

- [x] KB への問い合わせに答える手順をスキル `ask-kb` にし、rag-tester の答え方をこのスキルに委ねる。（出所: 2026-09-30 ディスカッション。[考察メモ](docs/notes/kaitou-tejun-memo.md#実装の記録)。コミット: f10a114）
- [ ] `Unreleased` をタグ付きリリースにし、omnibus-kb の `apm.yml` の固定コミットを上げて `apm install` で `ask-kb` と rag-tester を再生成する。（出所: `ask-kb` の実装）
- [ ] relations（`created-by` / `part-of` など）から、正解の根拠が決まる構造の問いを機械的に作るコマンドを足し、導入先が `evals/rag-eval.yml` の固定セットを作る足がかりにする。（出所: [RAG の自己改善のメモ](docs/notes/rag-jiko-kaizen-memo.md)）
- [ ] 検索用キーの台帳（検査と交換形式への出力）と、生成を担うスキル（仮称 `tune-index`）からなる RAG の自己改善のハーネス側を設計・実装する。検索・評価・紛らわしい相手の診断は kb-retrieval-core の責務（同 Issue #19）で、ハーネスには置かない。（出所: [RAG の自己改善のメモ](docs/notes/rag-jiko-kaizen-memo.md#再考同日-kb-retrieval-core-との分担)）
- [x] `references.yml` の `year` の型を制約するか決める。ハーネスは引用符つきの年を通すが、kb-retrieval-core は整数以外を拒否する（同 Issue #18。omnibus-kb の 494 件中 46 件が該当）。（出所: [RAG の自己改善のメモ](docs/notes/rag-jiko-kaizen-memo.md#再考同日-kb-retrieval-core-との分担)） → ハーネスは制約しない。kb-retrieval-core が数字だけの文字列を整数として受けるよう直した（kb-retrieval-core 523a2d2）。
- [x] 導入先の懸念台帳を `concerns.root` 配下の 1 件 1 YAML にし、実在するエンティティか出典 ID を必須の対象として `kb validate` で検査する。一覧は `kb sync` が生成する。CONCERNS と BACKLOG の役割を定義し直し、目的外の記録を促すスキルの記述を直す。（出所: 2026-09-29 ディスカッション。[考察メモ](docs/notes/kenen-daichou-memo.md#実装の記録)。コミット: 8b44f31）
- [x] `--check-urls` で、HEAD が HTTP のエラー応答を返したら状態コードを問わず GET で確かめ直す。HEAD に 500 を返し GET には 200 を返すサイト（e-種や）を到達不能と誤判定していた。（出所: 2026-09-29 tommy-farm。[考察メモ](docs/notes/url-kakunin-memo.md#再考2026-09-29-head-の-5xx)。コミット: d6351a6）

## 全体レビュー（2026-09-27、main @ ce52d66）の残作業

High 7 件は #30（コミット 996f433）で、R1〜R7 は claude/sharp-pasteur-byb4rc で修正済み。以下は Medium で、1 項目が PR 1 本の粒度。各項目は別セッションが単独で着手できるよう、対象・再現・完了条件を書く。行番号は ce52d66 時点。Low は末尾にまとめる。

- [x] **R1 `references.yml` のローダと検査規則を 1 つにする**。対象: `src/kb_harness/validation.py:124-144`（`_load_references`）、`src/kb_harness/references.py:66-81`（`plan_reference_create`）、`references.py:140-171`（`_Loader` / `reference_health`）。問題: (a) validate は list / str の `references.yml` で `AttributeError` → exit 3、health は `reference.root.mapping`。(b) create は type / title / URL 形式しか見ず、`{type: web, title: x}` は create が通り直後の validate で `type 'web' requires 'url'` になる（docs/cli.md「一時 KB で全体検証してから書く」に反する）。validate は「web は url 必須」、health は「全型で url か書誌」で規則も違う。(c) `_duplicate_ids` がモジュール大域で、入れ子 mapping の重複キー（1 エントリ内に `author:` 2 回）を `reference.duplicate.id` と誤報告する。完了条件: エントリ単位の検査関数を `references.py` に 1 つ置き validate / health / create から呼ぶ。重複検出はルートの mapping だけを見る。3 ケースの回帰テスト。（出所: 全体レビュー）（コミット: e0c52bd）
- [x] **R2 CLI の出力契約を揃える**。対象: `src/kb_harness/cli.py` の `_emit`（205-224）と各呼び出し。問題: `--format json` の失敗時出力が `validate` / `sync` は stdout、`entity create` / `project show` / `view` / `reference show|search|health` / `eval` / `okf validate` は stderr（`error=True`）。stdout を読む消費側は空を受け取る。`--dry-run` の text が `updated: <path>` と書き込み済みを装う（`_run_write_plan` が dry-run でも `changed` にパスを入れる）。`kb okf validate` だけ `--start` を受けない。`reference create` は内容の問題（重複 ID）でも exit 2、`entity create` は 1。完了条件: json なら常に stdout（`error` は text の stream 選択だけに使う）、dry-run は `would update:`、docs/cli.md の共通仕様表を実態に合わせる。（出所: 全体レビュー）（コミット: 8d1a96c）
- [x] **R3 validate の取りこぼし 3 件**。対象: `src/kb_harness/validation.py`。(a) `:286-291,404` `content_root` 直下の `.md`（`content/stray.md`、type: Person）が検査を素通りし graph.json に載る。`index.md` 以外のルート直下 `.md` を ERROR にする。(b) `:264,281` `directory` を欠く型があるとルート index に `'/None/index.md'` を要求する。`types.Note.directory` の欠落として報告し `type_dir_map` から除外する。(c) `:149` evals の探索が `content_root.parent` 固定で、`staging.py:47` / `cli.py` は `repo_root/evals`。`content_root: kb/entities` のような配置で evals 検査が黙ってスキップされる。`validate(root, ..., repo_root=)` を受けるようにする。完了条件: 3 ケースの回帰テスト。（出所: 全体レビュー）（コミット: 73e801f）
- [x] **R4 例外境界と view の整合**。(a) `src/kb_harness/serve/server.py:95-146` `do_GET` に例外境界が無く、壊れた `graph.json` / `vocabulary.yml` でトレースバックを出して接続を切る（HTTP 応答なし）。`try/except` で 500 を返す。(b) `src/kb_harness/doctor.py:239` `plan_sync` を保護せず呼ぶため、ビュー YAML の不備で `kb doctor` 自体が exit 3。診断に変換する。(c) `src/kb_harness/views.py:292-296` list ビューの member に `graph: false` の型（Note 等）や Index を書けるので、graph.json の `views[].members` が `nodes` に無いパスを指す。query 側の `query_excluded_types` を list member にも適用する。（出所: 全体レビュー）（コミット: 6e754f6）
- [x] **R5 Claim 規則の再実装を撤去する**。対象: `src/kb_harness/claim.py:35,106-107`、`src/kb_harness/okf.py:26`。許容 status `{proposed, accepted, disputed, rejected}`・confidence `{A,B,C,D}`・「predicate/object か property/value のどちらか」がハーネス側に再実装され、`validate_claim_file` は自前検査で弾いた後にしかコアを呼ばない。AGENTS.md は「変更先はオントロジーコア」と明記。完了条件: 事前検査を外してコアの `claim.status.unknown` / `claim.form.invalid` に委ね、okf の写像はコアが公開する集合を参照する（無ければコア側に足す）。兄弟ディレクトリに `../kb-ontology-core` v0.2.0 を置いて Claim テストを skip させずに確認する。（出所: 全体レビュー）（コミット: 55a876e）
- [x] **R6 テストと CI の穴**。(a) `tests/test_distribution_alignment.py:341-342` `json.loads` とアサーションが `for` の外にあり最後のコマンドしか検証していない。同フィクスチャ `:306` の `evals/rag-eval.yml` は mapping で `kb validate` が 1 を返している可能性が高く、`returncode in {0, 1}` が隠す。(b) 同ファイル `:17-20` の `pytestmark = skipif(兄弟なし)` がモジュール全体に掛かり、monkeypatch だけで動く doctor の 5 テスト（`:89-222`）まで skip。コア無し環境で doctor.py のコア整合分岐がゼロ実行。(c) `:32-33,53,244` タグ `v0.2.0` と checkout ディレクトリ名 `kb-harness-core` のハードコード。(d) `_validate_evals`（`validation.py:147-185`）、`fix_timestamps`（`:699-742`、git 管理外で `CalledProcessError` が漏れる）、`_url_reachable` の 403/405 → GET フォールバックにテストが無い。(e) `scripts/hooks/pre-commit:16` は `kb validate` のみで `kb sync --check` を呼ばない。omnibus-kb の AGENTS.md は両方を要求。足すか、Stop hook 側の責務と `docs/integration.md` に明記するかを決める。（出所: 全体レビュー）（コミット: 4363ba4）
- [x] **R7 文書の片側更新を直す**。(a) `docs/scripts.md`: `ndl_search.py` / `cinii_search.py` の `--format yaml|json`、`eval_summary.py --open`、`concerns_summary.py --actionable`、`browse.py open|close|url` が無い（いずれもスキルか integration.md が使う）。(b) `docs/configuration.md`: 実装済みで未記載の検査（title の括弧禁止、TODO プレースホルダ、生成物混入、aliases 重複、timestamp 形式、未知ディレクトリ、`type: Index` 必須、relations の `confidence: C`）と `evals/rag-eval.yml` の `kind` / `gap`。`:369` の `kb eval smoke --limit` は #30 で実装されたので整合を確認。(c) README の CLI 表に `kb serve` が無い。`docs/design-rationale.md:10` の `kb --check` は存在しない。`find-book SKILL.md:16` の `corpus_root` は contract に無い。`find-book` / `find-paper` SKILL.md:14 の `lineage` 新旧 2 文の重複。`add-entity SKILL.md:13`「`--help` が正」は誤り（正は configuration.md の spec 節）。(d) AGENTS.md:26「CI は Python 3.12 で」は #30 で 3.10 / 3.12 matrix になった。`docs/notes/hyojun-kata-memo.md:49`「Organization / Place を持つ KB はまだ無い」は omnibus-kb で陳腐化。完了条件: `.apm/skills/audit-harness` を実行して差分ゼロ。（出所: 全体レビュー）（コミット: 7a5ff61）
- [ ] R5 の残り: オントロジーコアの `CLAIM_STATUSES` / `CLAIM_CONFIDENCES` が `kb_ontology_core.__all__` に無く、ハーネスは `kb_ontology_core.claims.CLAIM_STATUSES` を直接参照している（`kb_harness.ontology.claim_statuses`）。コア側で公開 API に加え、タグを上げたら参照先を切り替える。（出所: R5 実装時）
- [ ] `evals/rag-eval.yml` の検査が 2 系統に分かれている。`kb validate` は `id` / `query` / `expected` / `evidence` の必須と実在だけを見て、`kind` 必須・`history` の形式・`gap` の語彙は `scripts/eval_summary.py`（`evaluation.validate_entries`）にしか無い。`kb validate` から `validate_entries` を呼ぶか決める。（出所: R7 実装時）
- [x] `Unreleased` をタグ付きリリース v0.11.0 にし、omnibus-kb の `apm.yml` の固定コミットを上げて `apm install` でスキルとエージェントを再生成する。（出所: 懸念台帳の実装（#41）。ハーネス側 3fe592e、omnibus-kb 側 4e7cbe3。タグ v0.11.0 は 3fe592e に手動で打つ）
- [x] omnibus-kb の `docs/CONCERNS.md` を懸念台帳へ移す。移行時点で 23 件あり、出典・内容の懸念 17 件を YAML に、型・述語・規約・本文の見直し 4 件を BACKLOG へ、解決済みのモデリング 2 件を BACKLOG の該当項目へ経緯として移した。（出所: 懸念台帳の実装時。omnibus-kb 798f989）
- [x] `Unreleased` をタグ付きリリース v0.11.1 にし、tommy-farm の `apm.yml` のタグを上げて `apm install` で再生成し、`kb validate --check-urls` で e-種や の誤判定が消えたことを確かめる。（出所: HEAD の 5xx の修正。ハーネス側 04f2104（#43）、タグ v0.11.1 は Tag release ワークフローで打った。tommy-farm 側は lostandfound/tommy-farm#2（bf016ea））
- [ ] R1 で `kb validate` が web 以外の文献にも「`url` か書誌（`author` / `publisher`）」を要求するようになった（従来は `kb reference health` のみ）。導入先（omnibus-kb）で固定コミットを上げる前に `kb validate` を回し、新規 ERROR を確認する。（出所: R1 実装時）
- [ ] **R8 Low（急がない）**。出典表記 regex 3 本（`validation.CITATION_RE` / `references._CITATION_RE` / `scripts/check_source_attrition.py`）と kebab regex 3 本、`TIMESTAMP_RE` 2 本の統合。`validate()` が `vocabulary.yml` を 4 回読む。`validation.py:32-42,699-769` の旧 CLI（`default_content_root` / `fix_timestamps` / `main`）の置き場。`okf.py:383` 脚注参照 regex が 1 行 1 件しか拾わない。`sync.py:126` の `newline=""` 未指定（Windows で CRLF が `\r\r\n`、未検証）。`scripts/explore_diff.py:159` の `kb-domain.yml` 決め打ち、`cinii_search.py:23` の `.env` 探索位置、`generate_index.py` が `by_tag` を渡さない、`browse.py` の macOS 固定と `playwright` 未宣言。`install-hooks.sh:9` の `.git/hooks` 直書き（worktree で失敗）。`pyproject.toml` package-data の階層列挙（`static/**/*` に）。`kb --version` が無い。`cli.py` の `_main` を handler テーブル + `_fail` ヘルパに整理。（出所: 全体レビュー）

## 完了
- [x] `Unreleased` をタグ付きリリース v0.10.0 にし、omnibus-kb の `apm.yml` の固定コミットを上げて `apm install` でスキルを再生成する。（出所: 2026-09-28 ディスカッション。ハーネス側 838bd29（#36）、omnibus-kb 側 07d1303（omnibus-kb#16）。タグ v0.10.0 は 838bd29 に手動で打つ）
- [x] `kb validate --check-urls` に `--for ENTITY` / `--ref ID` を足して確かめる対象を絞り、確認を並列化して同じ URL の重複を除き、HEAD が 404 のときも GET で確かめ直すようにした。add-entity / find-book / find-paper の手順を絞った形に改めた。omnibus-kb で KB 全体の確認が約 305 秒から約 42 秒になった。（出所: 2026-09-27 ディスカッション。[考察メモ](docs/notes/url-kakunin-memo.md#実装の記録)。コミット: 9ec3f09）
- [x] レビュー指摘に対応し、`timestamp` の元の表記と YAML マージ継承を検査し、Claim の状態変更で非正典時刻を拒否した。`evals/rag-eval.yml` の `entries:` 形式を検証で受け付け、出典照会の YAML 日付を JSON 出力できるようにした。（出所: 2026-09-28 レビュー。コミット: 5a172f9）
- [x] `Unreleased` をタグ付きリリース v0.8.0 にし、omnibus-kb の `apm.yml` の固定コミットを上げて `apm install` で `.claude/agents/evidence-reviewer.md` を再生成する。（出所: 2026-09-27 ディスカッション。ハーネス側 4880f24、omnibus-kb 側 3a54dd3。タグ v0.8.0 は ce52d66 に手動で打つ）

- [x] `kb reference show ID... / --for ENTITY` と `kb reference search` を追加し、エージェントが `references.yml` を丸ごと読まずに書誌を引けるようにした。evidence-reviewer と find-book / find-paper / add-entity の手順を対応させた。（出所: 2026-09-27 ディスカッション。コミット: e6a33d9, 67ba53c）
- [x] `references.yml` の `lineage` を「同じ由来の資料群のラベル」として汎用化し、設定リファレンスに必須キーと合わせて明記、find-book / find-paper / add-entity に付与手順を戻した。（出所: 同上。コミット: 7b952a5, 67ba53c）

## 保留した判断（考察メモの未決事項）

正本は各メモの「未決事項」節。ここは所在の一覧だけを持つ。

- [フィールドのプリセット化](docs/notes/field-preset-memo.md#未決事項) — 年表現の定義がハーネスとオントロジーコアで食い違う。`same_as` による突合。`query` ビューへのフィールド条件
- [型の標準化](docs/notes/hyojun-kata-memo.md#未決事項) — 型の `maps_to` を足す時点。`Organization` / `Place` を持つ KB が現れたときの層 2 の扱い
- [述語の階層](docs/notes/jutsugo-kaisou-memo.md#未決事項) — 標準述語の改版規則。層 2 の追加条件。既存述語の移行支援。CURIE 展開表の置き場。対称な関係
- [関係をあとから見出す](docs/notes/kankei-hakken-memo.md#未決事項) — ハブ Concept を立てる閾値。出典由来 / 解釈由来の明示を規約に載せるか
- [出典 URL の到達確認](docs/notes/url-kakunin-memo.md#未決事項) — 一時的な失敗を ERROR にするか。実行環境に依存する 403 をどこまで吸収するか
- [懸念台帳の構造化](docs/notes/kenen-daichou-memo.md#未決事項) — Claim の `disputed` との関係。GitHub Issues との関係
- [問い合わせへの答え方](docs/notes/kaitou-tejun-memo.md#未決事項) — サブエージェントを持たないランタイムでの rag-tester。kb-retrieval-core の使い方を書くか
- [RAG の自己改善](docs/notes/rag-jiko-kaizen-memo.md#未決事項) — キーの台帳のスキーマと kb-retrieval-core への交換形式。`description` を重みづけに含めるか。周回の停止条件と費用。固定セットの作り手（再考の節の追加分を含む）
