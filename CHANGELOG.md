# Changelog

## Unreleased

### Fixed
- `kb validate` が `timestamp` を、YAML が datetime に解決した値（無引用の `2024-01-01T00:00:00Z` など）でも検査するようになった。これまで文字列のときだけ検査していたため、`kb entity create` が書く無引用の正典形式は素通りし、UTC でない時刻や日付だけの値も通っていた。`title` / `description` が文字列でない（`description: 2020-01-01` が date に解決される等）場合も ERROR にする。これまでは validate が通るのに `kb sync` が内部エラーで落ちていた。既存 KB でこれらの値を持つファイルは新たに ERROR になる
- `kb eval smoke` が文書どおり「期待根拠が字面検索の上位に入るか」を検査するようになった（`--limit`、`eval.smoke.miss`）。これまで `summary` と同一の集計を返し、pre-commit の 3 段目は実質何も検査していなかった。`kb eval summary` は退行（過去 OK → 最新非 OK）を `eval.regression` として報告し exit 1 を返す。評価ファイルは `evals/rag-eval.yml` 固定になり、`evals/` に別ファイルがあっても落ちない
- 集計と字面検索の実装を `kb_harness.evaluation` に移し、`scripts/rag_smoke.py` / `scripts/eval_summary.py` はそれを呼ぶ互換入口にした（AGENTS.md の「scripts にロジックを二重に持たない」を回復）
- `kb claim transition` がオントロジーコアの解決を `ontology.load_ontology_core` に委ねるようになった。これまで `kb_ontology_core` を直接 import していたため、兄弟ディレクトリへのフォールバックが効かず、コア不在時に `ontology.core.missing` ではなく内部エラーになっていた
- `scripts/kb_config.default_content_root()` が絶対パスを返し、探索起点をカレントディレクトリにした。これまでリポジトリ相対の文字列を返していたため、cwd がリポジトリ直下でないと別の場所を読んでいた。`new_entity.py` / `validate.py` / `rag_smoke.py` の `--root` 既定値は遅延評価になり、`--help` や `--root` 指定が KB 探索で落ちなくなった
- Python 3.10 でテストが通るようにした（`tomllib` のフォールバック）。CI は 3.10 と 3.12 の両方で回す

### Changed
- AGENTS.md の `scripts/` 配線の記述を現行（`apm_modules/` の固定コミットを直接実行、symlink は 0.3.0 で廃止）に合わせた

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
