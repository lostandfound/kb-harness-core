# `kb` CLI リファレンス

`python3 -m pip install <このパッケージ>` で `kb` コマンドが入る。導入先 KB リポジトリ内で実行し、`kb-domain.yml` を起点にプロジェクトを解決する。

## 共通仕様

| 項目 | 内容 |
|---|---|
| `--start DIR` | プロジェクト探索の起点。省略時はカレントディレクトリから上へ `kb-domain.yml` を探す |
| `--format text\|json` | 出力形式。`json` は `ok` / `changed` / `diagnostics` を基本フィールドとし、CI やエージェントから機械的に扱える |
| `--dry-run` | 書き込み系コマンドで、変更を適用せず統一 diff のみを返す |

終了コード:

| コード | 意味 |
|---|---|
| `0` | 成功・同期済み |
| `1` | 検証不合格・差分あり |
| `2` | 引数または設定の不備 |
| `3` | 予期しない内部エラー |

## 読み取り・検証

### `kb project show`

`kb-domain.yml` の解決結果（ドメイン名、content_root など）を表示する。

### `kb validate`

KB 全体を検証する。frontmatter・リンク・relations の型制約・タグ語彙・出典参照・Claim・`evals/rag-eval.yml` を対象とする。`kb-domain.yml` に `validate.extra_checks` があれば本体の検証後に順に実行し、失敗を ERROR として集約する（[設定リファレンス](configuration.md#kb-domainyml)）。

### `kb doctor`

設定、`kb-ontology-core` のインストール状態と宣言タグとの一致、生成物の同期状態、`validate.extra_checks` のコマンド存在を診断する。導入直後や依存更新後の確認に使う。`severity: warning` の診断だけなら終了コードは 0。

## 生成物の同期

### `kb index build` / `kb index check`

各型ディレクトリの `index.md` を生成する（`build`）、または同期済みか確認する（`check`）。`build` は `--dry-run` に対応する。`kb-domain.yml` で `index.by_tag: true` のときは、ルート `index.md` の `<!-- tag-index:start -->` 〜 `<!-- tag-index:end -->` 区間にタグ別一覧も生成する（[設定リファレンス](configuration.md#kb-domainyml)）。

### `kb graph build` / `kb graph check`

ルートの `graph.json`（`nodes` / `edges` / `claims`）を生成・同期確認する。`build` は `--dry-run` に対応する。

### `kb sync` / `kb sync --check`

index と graph をまとめて生成・同期確認する。`--dry-run` に対応する。`index.by_tag` が有効ならタグ別一覧の陳腐化も `--check` で検出する。

## 書き込み（原子的）

書き込み系コマンドは spec ファイルから変更を計画し、一時 KB で全体検証を通してから反映する。検証に失敗した場合は何も書き込まない。

### `kb entity create --from entity.yml`

spec からエンティティ本体と index / graph を原子的に作成する。

| オプション | 内容 |
|---|---|
| `--from PATH` | エンティティ spec（[設定リファレンス](configuration.md#エンティティ-spec)） |
| `--timestamp` | frontmatter の `timestamp` を明示する |
| `--dry-run` | 統一 diff のみを返す |

`timestamp` は CLI 引数 → spec → 環境変数 `SOURCE_DATE_EPOCH` → 注入 clock の順で解決する。

### `kb claim create --from claim.yml`

spec から Claim ファイルを作成する。`--dry-run` に対応する。

### `kb claim inspect PATH` / `kb claim list [--status STATUS]` / `kb claim validate PATH`

Claim の照会・一覧・単体検証。

### `kb claim transition PATH --to STATUS`

Claim の `status` を明示的に遷移させる。許容される遷移は `kb-ontology-core` の `plan_transition` が定義する。`--dry-run` に対応する。

### `kb reference health`

`references.yml` の構造を検査する。

### `kb reference spec --from search-result.json --output reference.yml`

`ndl_search.py` / `cinii_search.py` の検索結果（JSON / YAML）を登録用 spec に変換する。`--dry-run` / `--force`（出力先の上書き）に対応する。

### `kb reference create --from reference.yml`

spec を `references.yml` に原子的に追加する。既存レジストリのコメント・引用符・順序・空行・改行コードは再シリアライズせず保持し、末尾に新規エントリのみを canonical YAML で追記する。空 mapping（`{}`）の場合は新規エントリ全体に置換する。`--dry-run` に対応する。

## 評価

### `kb eval summary`

`evals/rag-eval.yml` の評価履歴を集計し、退行（過去 OK → 最新非 OK）を検出する。

### `kb eval smoke`

各クエリの期待根拠が字面検索の上位に入るかを検査する。回答品質ではなく検索可能性の回帰を検出する。

## OKF

### `kb export okf --output PATH`

内部プロファイルを strict OKF v0.2 bundle に決定論的に変換する。出力パスは output root 配下に限定され、ref ID は小文字 kebab-case、入力 Markdown の symlink は拒否し（symlink ディレクトリは走査対象外）、任意階層の `log.md` は予約ファイルとして扱う。`--dry-run` に対応する。

内部プロファイルから OKF への変換方針（どの型・述語をどう対応付けるか）は導入先 KB が文書化する。

### `kb okf validate PATH [--strict]`

既存の OKF bundle の適合性を検証する。

## Python API

`kb_harness` パッケージは CLI と同じ計画・適用 API を公開する。主なモジュール:

| モジュール | 役割 |
|---|---|
| `kb_harness.project` | `kb-domain.yml` の探索と `Project` の解決 |
| `kb_harness.diagnostics` | 安定した `code` / `field` / `context` を持つ構造化診断 |
| `kb_harness.markdown` | frontmatter 付き Markdown の解析・シリアライズ |
| `kb_harness.entity` / `kb_harness.actions.entity` | エンティティ spec の検証と作成計画 |
| `kb_harness.claim` | Claim の作成・照会・遷移 |
| `kb_harness.references` | `references.yml` の点検・追記 |
| `kb_harness.index` / `kb_harness.graph` / `kb_harness.sync` | 生成物の計画と適用 |
| `kb_harness.okf` | OKF v0.2 の export と検証 |
| `kb_harness.ontology` | `kb-ontology-core` の `Diagnostic` を構造化診断へ翻訳する。従来の `validate_claim`（文字列リスト）も互換入口として残る |
| `kb_harness.doctor` | 環境診断 |
