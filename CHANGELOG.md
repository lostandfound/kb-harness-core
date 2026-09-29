# Changelog

## Unreleased

### Fixed

- `--check-urls` が、HEAD がエラー応答を返した URL を状態コードを問わず GET で確かめ直す。これまでは 403 / 404 / 405 だけを確かめ直しており、HEAD にだけ 500 を返すサイト（e-種や など）を到達不能と誤判定していた。タイムアウトや接続失敗は従来どおり確かめ直さない。`scripts/validate.py --check-urls` も同じ

## 0.11.0 — 2026-09-29

スキル（add-entity / audit-harness / expand-kb / explore-kb / ndl-digicolle / review-entity-model）とエージェント（evidence-reviewer）の懸念台帳の扱いを改めたため、導入先は固定コミットを上げたあと `apm install` で `.claude/` を再生成する。

### Added

- 懸念台帳（`kb-domain.yml` の `concerns.root`、任意）。エンティティと出典の確からしさについての懸念を 1 件 1 YAML で置く。各懸念は実在するエンティティ（`/dir/file.md`）か `ref: <id>` を `targets` に必須で持ち、`kind`（`conflict` / `weak-source` / `indirect` / `unreachable` / `judgment`）と `status`（従来の 6 値）を語彙で固定する。状態ごとに `resolution` / `awaiting` / `resume_when` を必須にし、未知のキーは ERROR。`kb validate` が検査し、`kb sync` が懸念一覧（`concerns.index`、既定 `<root>/index.md`）を生成して陳腐化を `concerns.stale` で検出する。`kb entity create` / `kb claim create` の一時 KB での全体検証も懸念を含む（判断の経緯は docs/notes/kenen-daichou-memo.md）
- `kb concern list [--for TARGET] [--status STATUS] [--actionable]` / `kb concern summary` / `kb concern validate`
- `concerns.root` を設定した KB に旧来の `docs/CONCERNS.md` が残っていると、`kb validate` が `concern.legacy_ledger` の WARNING を出す

### Changed

- `scripts/concerns_summary.py` が、`concerns.root` のある KB では構造化した台帳を集計する。`--ledger` を渡すか `concerns.root` が無ければ従来どおり Markdown の台帳を集計する
- 導入ガイドの運用ファイルの定義を改めた。懸念台帳は KB の知識の確からしさの台帳、`docs/BACKLOG.md` は KB を作る作業の予定と記録で、行を移し合わない。旧来の `docs/CONCERNS.md` の雛形を外し、移行の手順を載せた
- スキルが懸念台帳へ目的外の記録をしないようにした。audit-harness はハーネス文書の不整合を監査結果で報告するだけにし、review-entity-model は型・境界の判断を懸念に送らず保留として報告し、expand-kb は対象を特定できる出典・内容の懸念だけを懸念にする
- evidence-reviewer が対象の既存の懸念を `kb concern list --for` で読み、確度 C / D のうち本文の修正で解消しないものを懸念の YAML 案として報告する。add-entity は執筆時に残った食い違いや値の選択を、作成したエンティティを対象とする懸念として書く
- `kb sync` が、壊れた懸念 YAML を内部エラーにせず `concern.*` の診断として終了コード 1 で返す

## 0.10.0 — 2026-09-28

スキル（add-entity / find-book / find-paper）の手順を改めたため、導入先は固定コミットを上げたあと `apm install` で `.claude/` を再生成する。

### Added

- `kb validate --check-urls` が `--for ENTITY` / `--ref ID`（繰り返し可）を受け、確かめる対象を指定したエンティティの出典と指定した出典 ID に絞る。見つからないエンティティ・出典 ID は ERROR。`--check-urls` なしで渡すと `validation.arguments` で exit 2。`check_urls()` も `entities` / `ref_ids` 引数を受ける（判断の経緯は docs/notes/url-kakunin-memo.md）

### Changed

- `kb validate --check-urls` が URL と DOI を並列に確かめ（同じホストへは同時 2 本まで）、1 回の実行の中で同じ URL・DOI を 1 回だけ確かめる。ERROR の並びは従来どおり走査順。omnibus-kb（出典約 380 件）で約 305 秒が約 42 秒になった
- `--check-urls` が、HEAD に 404 を返した URL も GET で確かめ直す。これまでは 403 / 405 だけを確かめ直しており、HEAD にだけ 404 を返すサイト（tower.jp など）を到達不能と誤判定していた。`scripts/validate.py --check-urls` も同じ
- add-entity / find-book / find-paper の手順が、足したエンティティや出典に絞って `--check-urls` を回すようにした
- `kb validate --check-urls` が、DOI レジストリに届かなかった DOI を ERROR にせず `validation.url.doi_registry_unreachable` の WARNING にする。これまでは未登録とレジストリの障害を区別せず `DOI unregistered or registry unreachable` の ERROR にしていたため、一時的なネットワーク障害でも検証が落ちていた。レジストリが未登録と答えた DOI（404、または別のハンドル）は従来どおり ERROR で、メッセージは `DOI unregistered` に改めた。`scripts/validate.py --check-urls` も同じ
- `check_urls()` が任意の `warnings` 引数を受け、WARNING をそこへ加える。省略したときは従来どおり ERROR だけを返す
- docs/cli.md と docs/scripts.md に `--check-urls` の確かめ方（DOI はレジストリで確認、`doi` と `url` の両方があれば `doi` だけ、出版社 URL 中の DOI は認識しない）を記した

## 0.9.1 — 2026-09-28

### Fixed

- `kb validate` が YAML の型変換後も `timestamp` の元の表記を検査する。マージキーで継承した値も扱い、`+00:00`・空白区切り・小数秒を規定外として報告する。
- `kb validate` が `evals/rag-eval.yml` の `entries:` 形式を受け付ける。
- `kb reference show` / `search --format json` が `references.yml` 内の YAML 日付を ISO 形式の文字列で出力する。
- Claim の状態変更が非正典形式の時刻を丸めて保存せず、変更前に拒否する。

## 0.9.0 — 2026-09-27

互換性に影響する変更を含む。導入先は固定コミットを上げる前に `kb validate` を回し、新たな ERROR を確認する。

### Changed
- `--format json` の出力は成否にかかわらず常に stdout に出す。これまで `entity create` / `project show` / `view` / `reference show|search|health` / `eval` / `okf validate` は失敗時に stderr へ出していた。stderr から JSON を読んでいた消費側は stdout に切り替える（R2）
- `--dry-run` の text 出力は `would update: <path>` と書く。これまで書き込み済みと同じ `updated:` を出していた（R2）
- `kb reference create` は重複 ID・必須キー欠落などの内容エラーで exit 1 を返す（`kb entity create` と揃えた）。spec やレジストリが読めない等の構成の問題は従来どおり exit 2（R2）
- `references.yml` の検査規則を `kb_harness.references.check_reference_entry` に一本化し、`kb validate` / `kb reference health` / `kb reference create` / `show` / `search` が同じローダと規則を使う。`kb validate` も web 以外の型に「`url` か書誌（`author` / `publisher`）」を要求するようになり、既存 KB でこれを欠くエントリは新たに ERROR になる。`kb reference create` で通った spec が直後の `kb validate` で弾かれることはなくなった（R1）
- Claim の status / confidence / 形式の事前検査をハーネスから撤去し、オントロジーコアの診断（`claim.status.unknown` / `claim.form.invalid` 等）に委ねた。okf の `claim_status` 写像もコアの許容集合を参照するため、オントロジーコアなしで Claim を含む KB を `kb export okf` すると `ontology.core.missing` で止まる（R5）
- list ビューの member に `graph: false` の型や `Index` を置くと ERROR にし、graph.json の `views[].members` が `nodes` に無いパスを指さないようにした（R4）
- `scripts/hooks/pre-commit` が `kb validate` に続けて `kb sync --check` を実行する（R6）
- AGENTS.md の `scripts/` 配線の記述を現行（`apm_modules/` の固定コミットを直接実行、symlink は 0.3.0 で廃止）に合わせた
- docs/scripts.md・configuration.md・cli.md・README・スキル（`.apm/`）の実装との食い違いを直した。実装済みで未記載だった検査（title の括弧禁止、TODO プレースホルダ、生成物混入、aliases 重複、timestamp 形式、未知ディレクトリ、`type: Index` 必須、relations の `confidence: C`）と `references.yml` のエントリ規則を設定リファレンスに記した（R7）

### Added
- `kb okf validate` が `--start` を受ける。相対の `PATH` はそこを起点に解決する（R2）

### Fixed
- `kb validate` が list / 文字列ルートの `references.yml` で内部エラー（exit 3）にならず `reference.root.mapping` を報告する。1 エントリ内の重複キー（`author:` を 2 回など）を `reference.duplicate.id` と誤報告しなくなった（R1）
- `kb validate` が `content_root` 直下の `index.md` 以外の `.md` を ERROR にする。これまで検査を素通りして graph.json に載っていた（R3）
- `directory` を欠く型を `types.<Name>.directory` の未設定として報告する。これまでルート index に `/None/index.md` へのリンクを要求していた（R3）
- `evals/rag-eval.yml` をリポジトリルートから探す。`content_root: kb/entities` のような配置で evals の検査が黙って飛ばされていた（R3）
- `kb serve` が壊れた `graph.json` / `vocabulary.yml` でトレースバックを出して接続を切らず、HTTP 500 を返す（R4）
- `kb doctor` がビュー YAML の不備で内部エラー（exit 3）にならず、`doctor.sync_failed` 診断を返す（R4）
- `validation.fix_timestamps` が git 管理外で `CalledProcessError` を漏らさず、`validation.timestamps.git_required` を返す（R6）
- `kb validate` が `timestamp` を、YAML が datetime に解決した値（無引用の `2024-01-01T00:00:00Z` など）でも検査するようになった。これまで文字列のときだけ検査していたため、`kb entity create` が書く無引用の正典形式は素通りし、UTC でない時刻や日付だけの値も通っていた。`title` / `description` が文字列でない（`description: 2020-01-01` が date に解決される等）場合も ERROR にする。これまでは validate が通るのに `kb sync` が内部エラーで落ちていた。既存 KB でこれらの値を持つファイルは新たに ERROR になる
- `kb eval smoke` が文書どおり「期待根拠が字面検索の上位に入るか」を検査するようになった（`--limit`、`eval.smoke.miss`）。これまで `summary` と同一の集計を返し、pre-commit の 3 段目は実質何も検査していなかった。`kb eval summary` は退行（過去 OK → 最新非 OK）を `eval.regression` として報告し exit 1 を返す。評価ファイルは `evals/rag-eval.yml` 固定になり、`evals/` に別ファイルがあっても落ちない
- 集計と字面検索の実装を `kb_harness.evaluation` に移し、`scripts/rag_smoke.py` / `scripts/eval_summary.py` はそれを呼ぶ互換入口にした（AGENTS.md の「scripts にロジックを二重に持たない」を回復）
- `kb claim transition` がオントロジーコアの解決を `ontology.load_ontology_core` に委ねるようになった。これまで `kb_ontology_core` を直接 import していたため、兄弟ディレクトリへのフォールバックが効かず、コア不在時に `ontology.core.missing` ではなく内部エラーになっていた
- `scripts/kb_config.default_content_root()` が絶対パスを返し、探索起点をカレントディレクトリにした。これまでリポジトリ相対の文字列を返していたため、cwd がリポジトリ直下でないと別の場所を読んでいた。`new_entity.py` / `validate.py` / `rag_smoke.py` の `--root` 既定値は遅延評価になり、`--help` や `--root` 指定が KB 探索で落ちなくなった
- Python 3.10 でテストが通るようにした（`tomllib` のフォールバック）。CI は 3.10 と 3.12 の両方で回す

## 0.8.0 — 2026-09-27

### Added
- `kb reference show ID...` / `kb reference show --for ENTITY` と `kb reference search TERM... [--field] [--url] [--doi] [--limit] [--full]` を追加。エージェントが `references.yml` を丸ごと文脈に読み込まず、ID・エンティティ・語句・URL・DOI で必要な書誌だけを引ける。`--url` / `--doi` は正規化後の完全一致で、登録前の重複確認に使う
- 設定リファレンスの `references.yml` 節に必須キーと任意キー `lineage` を明記。`lineage` は「同じ由来の資料群のラベル」として汎用化し、流派・学派の伝承だけでなく、同じ記事の別言語版・転載、当事者の自己発信も単位に含める

### Changed
- evidence-reviewer は `references.yml` を丸ごと読まず `kb reference show --for` で対象の出典だけを引く。`lineage` 未記載を未判定として扱い、由来の共有を見極めて付与を提案する
- find-book / find-paper に登録前の `kb reference search` による重複確認と、`lineage` 付与の手順を戻した。add-entity の出典登録にも同じ手順を足した

## 0.7.0 — 2026-09-26

### Changed
- 本文リンクをリンク元ファイルからの相対パス（`[名前](../people/example.md)`）で書く契約に改めた。これまでの `content_root` 起点のルート相対リンク（`/people/example.md`）は、GitHub が `/` をリポジトリルートとして解釈するため、`content_root` がサブディレクトリだとクリックしても遷移しなかった。相対リンクなら GitHub・Obsidian・エディタのどれでも遷移できる。規則は設定リファレンス「本文リンク」（#27）
- `kb validate` が相対リンクを解決して、存在と index の網羅を検査するようになった。これまで検査の対象外だった相対リンクも見るので、既存の切れた相対リンクは新たに ERROR になる。`content_root` の外を指すリンクはファイルの実在だけを見る。旧形式のルート相対リンクは解決するが、件数をまとめて `validation.link.root_relative`（WARNING）で示す（#27）
- `kb index build` / `kb sync` が生成する型別 index、タグ別一覧、ビュー一覧（`views.index`）を相対リンクで出力する。導入先はこの版に上げた後に `kb link migrate` と `kb sync` を実行する（#27）
- `kb flashcards` は本文の相対リンクを識別子へ直して画面へ渡す。relations の `target`、Claim の `subject` / `object`、ビューの `members`、`evidence` は識別子なので、ルート相対のまま変わらない（#27）

### Added
- `kb link migrate [--check] [--dry-run]` を追加。旧形式のルート相対の本文リンクを相対リンクへ書き換える。見出しへのフラグメントは保つ（#27）
- `kb okf validate` と `kb export okf` が、bundle 内で解決できない本文リンクを `okf.link.broken` の警告にする。`content_root` の外を指すリンクは bundle に写らないので切れる。書き出しは止めず、`kb okf validate --strict` のときだけ失敗扱いにする（#27）

## 0.6.0 — 2026-09-26

### Added
- 語彙の名前の文字種を定め、`kb validate` が検査するようにした。型名は PascalCase、述語名とプロパティ名は kebab-case、フィールド名は snake_case、タグは kebab-case で、外れていれば ERROR。これまでは規則が文書に無く、検査もしていなかった（slug・ファイル名・ref ID は従来どおり）。規則は設定リファレンス「名前の文字種」

## 0.5.0 — 2026-09-26

### Changed
- `kb-ontology-core` を必須の依存から `claims` extra に移した。`pip install kb-harness-core` ではオントロジーコアが入らず、Claim を使う導入先は `pip install "kb-harness-core[claims] @ ..."`（apm 配下なら `"apm_modules/lostandfound/kb-harness-core[claims]"`）で入れる。既に Claim を使っている導入先は、次に `pip install` し直すときに extra を付けないとオントロジーコアが落ちる（`kb doctor` が WARNING、Claim の検証が `ontology.core.missing` で止まる）。`requirements.txt` は開発・CI 用の全部入りのまま
- `kb entity create` と `scripts/new_entity.py` が、型が `sections` を宣言しないときに型名（`Person` / `Style` / `Kata` / `Term` / `HistoricalEvent` / `Note`）で選んでいた既定の章立てを廃止した。特定の導入先の章立てがハーネスに焼き込まれていたもので、`sections` を書かない型はすべて 概要 / 詳細 / 関連項目 になる。`kb validate` は章立てを見ないので既存エンティティの検証は変わらないが、これらの型名で既定に依存していた導入先（omnibus-kb の `Person` / `Note`、沖縄空手 KB の `Person` / `Style` / `Kata`）は、この版に上げる前に `vocabulary.yml` の `sections` に既存エンティティと同じ章立てを書く。書かないと新規作成の章立てが既存と食い違う
- 型定義（`types:`）の読み込みと `extra_fields` / `optional_fields` の宣言検査を `kb_harness.types` に一本化した。`kb validate` と `kb entity create` で判定が食い違っていた（空文字のフィールド名を validate は拒み、entity create は通していた）
- 型固有フィールドの値が空（`died:` や `died: null`）のときは、キーを書いていないものとして扱う。任意フィールドなら通り、必須フィールドなら「missing required field」になる。これまでは「非空の文字列でなければならない」だった

### Added
- `kb-ontology-core` が無い環境でもハーネスが動くようにした。オントロジーコアの import を Claim の検証・出力・語彙構築を呼ぶ時点まで遅らせ、Claim を使わない KB では `kb validate` / `kb sync` / `kb graph build` / `kb doctor` などがオントロジーコアなしで通る。Claim を扱おうとしたときは `ontology.core.missing` の診断（終了コード 1）で止まり、内部エラーにはしない。`kb doctor` はオントロジーコアが無いことを `doctor.ontology.not_installed`（WARNING）で報告する。CI にオントロジーコアなしのジョブを足し、Claim を使うテストと `test_distribution_alignment.py` はそれぞれオントロジーコア・兄弟ディレクトリが無ければ skip する
- 標準型を文書で定めた。`Person` / `Organization` / `Place` / `Event` / `Work` / `Concept` の 6 つで、名前と意味と schema.org / CIDOC-CRM / Wikidata への対応だけを定め、フィールド・章立て・ディレクトリ名は導入先が決める。検査はしない。標準述語の `domain` / `range` を束縛する目安もこの型名で書いた。考察は `docs/notes/hyojun-kata-memo.md`

## 0.4.0 — 2026-09-26

### Added
- `vocabulary.yml` の型定義に `optional_fields` を追加。書いてもよいが無くても通る frontmatter フィールドを宣言できる。これまで `extra_fields` は必須しか宣言できず、存命の人物の `died` や継続中の出来事の `end` を `不詳` や「なし」で埋めるしかなかった。`kb validate` は任意フィールドが書かれていれば必須と同じ検査を行い、同じ名前が両方に宣言されていれば ERROR にする。`kb entity create` の spec `fields` に任意フィールドを書ける。考察は `docs/notes/field-preset-memo.md`（#19）
- リリースタグを打つ GitHub Actions ワークフロー `release.yml` を追加。`workflow_dispatch` で版を受け取り、`pyproject.toml` / `__init__.py` / `apm.yml` / `CHANGELOG.md` が一致するコミットにだけ注釈付きタグ `v<version>` を作る。手順は README の「リリース」

### Fixed
- 型固有フィールドを `year: 2021` や `born: 1940` のように引用符なしで書くと、YAML が数値として読むために `kb validate` が「missing required field」と誤った診断を出していた。数値・日付として読まれた値は文字列として扱い、文字列にできない値（リストなど）には「非空の文字列でなければならない」と実際の値を示す診断を出す。`kb entity create` の spec `fields` も同じ扱いにした（#19）

## 0.3.0 — 2026-09-26

### Changed
- `kb validate` が warnings を返すようになった。これまで CLI は `validate()` の warnings を捨てていた。`--format json` では `diagnostics` と同じ `{severity, code, message}` の配列 `warnings` を常に含め、text では `<SEVERITY> <message>` の形で stderr に出す。既存の description の警告にも `WARNING` 接頭辞とコードを付けた（#15）
- `vocabulary.yml` の述語の domain / range がスカラー（例 `domain: Script`）のとき、無制約や部分一致として扱われていたのを、1 要素として扱った上で「型名のリストでなければならない」ERROR にした（#15）
- 同梱スキルから導入先固有の記述（AGENTS.md の行数上限、`packages/kb-harness-core` パス、born/died、特定考証エージェント名、CONTRIBUTING の節番号）を除き、正本参照に置き換えた
- 導入先ルートの `scripts/` をモジュールへの symlink にする手順を廃止。補助スクリプトは `apm_modules/lostandfound/kb-harness-core/scripts/<name>.py` で直接呼び、pre-commit テンプレートは `kb validate` / `kb eval smoke` のみを呼ぶ。`install-hooks.sh` は自身の位置から `hooks/pre-commit` を探すので `apm_modules` 配下から実行できる（#4）
- 動作確認する apm の版を 0.32 に上げた。0.32 で `--target claude` / `--target codex` の配置と `apm audit` を確認済み。導入ガイドに、配置先 target の指定が必須であること、短縮 SHA での固定が拒否されること、Codex ではエージェントの `tools` が落ちることを追記した

### Added
- `vocabulary.yml` の述語に `broader`（親述語）と `maps_to`（標準語彙の CURIE / IRI）を追加。述語を詳細度で三層（`related-to` = 未分類 / 層 1 = 方向と型制約 / 層 2 = 導入先が親の下に吊るす精緻化）に分けて扱う。`kb validate` が親の実在・自己参照・`related-to` への参照・循環・domain / range の包含・`maps_to` の形式を検査し、`query` ビューは親の述語で子孫のエッジも拾う（推移閉包は導かない）。`kb graph build` は `broader` か `maps_to` を持つ語彙だけ `graph.json` に `predicates` を出す（#15）
- 標準述語を文書で定めた。`part-of` / `derived-from` / `created-by` / `located-in` / `follows` の 5 つで、向きは「依存する側から依存される側へ」に統一。名前と向きはハーネスが決め、domain / range は導入先が型で束縛する。族の選び方（含意の強い族に置く、所属と順序・血縁と継承は別のエッジ、対称な関係はエッジにしない、順序をフィールドで持たない）を運用規約として `docs/configuration.md` に置いた。考察は `docs/notes/jutsugo-kaisou-memo.md`（#15）
- `kb validate` が `related-to` のエッジ件数を INFO で、始点と終点の型が層 1 のちょうど 1 つの述語に収まるエッジを精緻化の余地として WARNING で報告する。`kb doctor` は標準述語でも `related-to` でもなく `broader` も持たない述語を `doctor.predicate.nonstandard`（WARNING）で示す（#15）
- `kb validate --check-urls` を追加。出典 URL・DOI の到達性確認を `scripts/validate.py` と同じく CLI からも行える。スキルが前提にしていたが CLI に無かった
- `kb serve` を追加。知識グラフをローカルでブラウザ閲覧するコマンド。`graph.json` を読み、127.0.0.1 に限定して待ち受ける。表示情報（型の色・述語表示名・題名）は `vocabulary.yml` と `kb-domain.yml` から導出し、新規の設定項目は増やさない
- `kb serve` の閲覧画面を neon-graph-design-system のトークンと書体で描き直した。Sigma.js の描画に発光・艶・選択輪・フォーカス中の辺の流れを重ね、フォーカス時は近傍以外を減光する。トークンと JetBrains Mono は同梱し、外部の書体や CDN は読まない
- `kb serve` のノードを力学配置（ForceAtlas2 + noverlap）で並べるようにした。関係の近いエンティティが寄り、初期表示は右の詳細パネルを避けて収まる。同じ `graph.json` からは毎回同じ配置になる
- `kb serve` の型の色が 8 型を超えると循環して重なっていたのを、12 色のパレットとそれ以降の生成色で重ならないようにした
- `kb-domain.yml` に `views.root` / `views.index` を追加。エンティティ本文の外に置く「ビュー」（`kind: list` の割り当てと `kind: query` の導出）を 1 件 1 YAML で定義でき、`kb validate` が語彙と実在エンティティに照らして検査し、`kb sync` / `kb entity create` がビュー一覧と `graph.json` の `views` 配列を生成する。`kb view list|resolve|validate` を追加。出典で支えられた事実はエンティティに、書き手の見方による束ねはビューに置く分離を機械的に保つための層で、ビューの内容はエンティティへ書き戻さない
- `kb-domain.yml` に `index.by_tag` / `index.tag_labels` を追加。有効にすると `kb sync` / `kb index build` / `kb entity create` がルート `index.md` のマーカー区間にタグ別（分野別）一覧を生成し、`kb sync --check` が陳腐化を検出する（#1）
- `kb-domain.yml` に `validate.extra_checks` を追加。`kb validate` が本体の検証後に導入先固有のコマンドを順に実行して失敗を ERROR に集約し、`kb doctor` がコマンドの存在を WARNING で報告する（#2）
- `vocabulary.yml` の型定義に `sources_required: false` を追加。出典を求めない型（個人メモ等）を定義できる。`kb validate` と `kb entity create` の両方が従う
- `scripts/check_source_attrition.py` を追加。改版で先行する出典の記述が失われたエンティティを検出する。`kb validate` は形式しか見ないため、複数出典を並存させる本文が新しい出典で上書きされても通ってしまう。`.kb/hooks/pre-commit.d/` から呼んで止める
- `scripts/verify_turn.sh` を追加。Claude Code の Stop hook からターンの終了時に `kb validate` と `kb sync --check` を実行する。pre-commit が閉じるのはコミット時だけで、コミットせずに終わるターンでは検証が走らないため

### Fixed
- `kb validate --check-urls` が DOI を出版社サイトまで辿って到達性を見ていたため、ボット遮断で登録済みの DOI まで失敗扱いになっていた。DOI（`references.yml` の `doi` と `doi.org` の URL）は DOI レジストリ（Handle API）で登録の有無だけを確かめるよう修正
- pre-commit テンプレートが `tests/` と `evals/rag-eval.yml` の存在を前提にしていたのを、存在するときだけ実行するよう修正。併せて `.kb/hooks/pre-commit.d/*` を名前順に実行し、テンプレートを編集せず導入先固有のチェックを足せるようにした（#3）
- `scripts/` の互換スクリプト（`validate.py` / `export_graph.py` など）が、同じチェックアウトの `src/` より pip で入った `kb_harness` を優先して読んでいたのを修正。導入先に古い版が入っていると submodule 側の修正が効かなかった
- ビュー YAML に形式の不備があると `kb sync` / `kb graph build` / `kb entity create` / `kb claim create` が internal error で落ちていたのを、ビューの診断（`view.*`）または検証エラーとして返すよう修正
- `views.root` が `content_root` を含む配置（例 `content_root: kb/entities` と `views.root: kb`）で、一時 KB にビュー定義が写らず entity / claim create が必ず `entity.sync.failed` になっていたのを修正
- query ビューが `Index` 型と `graph: false` の型のエンティティも拾い、`graph.json` の `views[].members` が `nodes` に無いパスを指していたのを修正
- 学習カード画面に別 KB の述語名がハードコードされていたのを除き、述語の表示名を `vocabulary.yml` の description から出すよう修正。日本語表示でブランド名が「学習 学習カード」と重なっていたのを「知識 学習カード」に修正
- `kb serve` のノード ID をファイル名だけでなく KB 相対パスから生成するよう修正。同名ファイルが別ディレクトリにあっても、グラフ画面でノードが融合しない

## 0.2.1 — 2026-09-11

### Fixed
- `scripts/refs_health.py` の既定レジストリパスをドメイン固有値から `kb-domain.yml` 解決に変更
- `kb validate --check-urls` の User-Agent が別リポジトリを指していたのを修正

### Changed
- `pyproject.toml` に readme / license / classifiers / urls を追加
- ビルド生成物 `*.egg-info/` を追跡対象から除外

## 0.2.0 — 2026-09-11

初回タグ。`kb` CLI と Python API（`src/kb_harness`）、スキル 7 件、エージェント 2 件、補助スクリプトを含む。

### Changed
- `kb-ontology-core` 依存を `git+https://` 参照に変更（ssh 鍵不要に）
- README を公開パッケージ向けに再編し、契約・CLI・導入手順を `docs/` に分離
- `apm.yml` 依存記法を apm が受理する文字列形式に修正

### Added
- `LICENSE`（MIT）
