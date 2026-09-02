# kb-harness-core

ドメイン非依存の知識ベース（KB）運用ハーネスである。
特定分野の知識を Markdown エンティティ集合として管理する KB リポジトリに、検証スクリプトと Claude Code 用のスキル・エージェントを提供する。

このパッケージ自体はどのドメインの知識も持たない。
ドメイン固有の情報（型・述語・タグの語彙、ディレクトリ構成）は導入先の KB リポジトリ側が `kb-domain.yml` と `vocabulary.yml` に書き、ハーネスはそれを読んで動作する。

## Python パッケージと CLI

`kb-harness-core` は、既存 scripts と同じドメイン設定を読むインストール可能な Python パッケージである。Phase 2 では読み取り・検証・生成物同期を `kb` CLI に統合した。

```bash
python3 -m pip install ./packages/kb-harness-core
kb project show
kb project show --format json
kb validate
kb sync --check
```

CLI の Phase 2 コマンドは次のとおりである。

- `kb validate` — KB 全体を検証する。
- `kb index build` / `kb index check` — 各型の `index.md` を生成・同期確認する。
- `kb graph build` / `kb graph check` — ルートの `graph.json` を生成・同期確認する。
- `kb sync` / `kb sync --check` — index と graph をまとめて生成・同期確認する。
- `kb doctor` — 設定、依存バージョン、生成物の状態を診断する。
- `kb entity create --from entity.yml` — 検証済み spec から entity と index/graph を原子的に作成する。`--dry-run` は統一 diff のみを返す。

すべてのコマンドは `--format json` を指定できる。JSON は `ok`、`changed`、`diagnostics` を基本フィールドとし、CI やエージェントから機械的に扱える。終了コードは `0`（成功・同期済み）、`1`（検証不合格・差分あり）、`2`（引数または設定不備）、`3`（予期しない内部エラー）である。`build` は生成予定をメモリ上で作成し、共通の原子的適用処理で書き込む。

共通 API の責務:

- `kb_harness.project`: `kb-domain.yml` の探索とパス解決
- `kb_harness.diagnostics`: 安定したコードを持つ構造化診断
- `kb_harness.markdown`: YAML frontmatter と本文の解析
- `kb_harness.entity`: エンティティ雛形生成と clock 注入

エンティティ作成 spec は `type`、`slug`、`title`、`description`、`tags`、`sources`、`sections`（見出しから非空本文への mapping）を必須とし、`aliases`、`relations`、`fields`、`timestamp` を任意とする。型ごとの章構成と extra fields は導入先の `vocabulary.yml` を正本とする。timestamp は CLI、spec、`SOURCE_DATE_EPOCH`、注入 clock の順で解決される。

`scripts/new_entity.py` と `scripts/kb_config.py` は共通 API を呼ぶ互換入口であり、`scripts/validate.py` も共通 Markdown 解析を利用する。
`scripts/generate_index.py` と `scripts/export_graph.py` も同じ計画・適用 API を使う互換入口である。

## 提供物

### スキル（5件）

`.apm/skills/` 配下。frontmatter の `description` から採録。

| スキル | 説明 |
|---|---|
| `add-entity` | KB に新規エンティティを追加する確定的手順。「エンティティ追加」「新しいエンティティ（人物・概念等）を追加」で使用。 |
| `audit-harness` | ハーネス文書群（CLAUDE.md・CONTRIBUTING・スキル・エージェント・スクリプト）の整合性を監査し正本参照型で修正する手順。「整合性チェック」「ハーネス監査」「文書の陳腐化確認」で使用。 |
| `find-book` | NDL サーチ（国立国会図書館）API で書籍・資料を検索し、文献レジストリ references.yml に登録する手順。「書籍を探して」「NDLで検索」「書誌を確認して」で使用。 |
| `find-paper` | CiNii API で論文を検索し references.yml へ登録する確定的手順。「論文を探して」「文献を追加」「CiNii で検索」で使用。 |
| `ndl-digicolle` | NDL デジタルコレクション（個人送信サービス）で資料本文を確認する半自動手順。ログイン等のブラウザ操作はユーザーが行い、Claude は準備と結果の反映を担当する。 |

### エージェント（2件）

`.apm/agents/` 配下。frontmatter の `description` から採録。

| エージェント | 説明 |
|---|---|
| `evidence-reviewer` | KBの主張と出典の対応、情報の鮮度、製品仕様・提供条件・導入効果の確度を審査する証拠レビュアー。 |
| `rag-tester` | RAG 消費者役。KB だけを根拠に想定クエリへ回答を試み、回答不能・誤答・曖昧になる箇所を報告する敵対的テスター。周期的な品質測定やエンティティ追加後の受け入れ確認に使用。 |

### scripts（一覧は下表が正、件数は記載しない）

`scripts/` 配下。多くは `--root` でコンテンツルートを指定でき、省略時は `kb-domain.yml` から自動解決する（`kb_config.py` が共有ヘルパー、単体では実行しない）。

| スクリプト | 役割 |
|---|---|
| `validate.py` | frontmatter・リンク・エッジ・語彙・書誌参照（ファイル単位 `sources` + 本文インライン `（出典: ref-id）`）を検証する。`--fix-timestamps` / `--check-urls` オプションあり。 |
| `new_entity.py` | エンティティ雛形（frontmatter・見出し構成）を生成する。 |
| `generate_index.py` | 各ディレクトリの index.md にエンティティ一覧を生成する。 |
| `export_graph.py` | ナレッジグラフ（nodes/edges）を JSON でエクスポートする。 |
| `eval_summary.py` | `evals/rag-eval.yml` の最新判定を集計し、退行（過去 OK→最新非 OK）を検出する。`--eval-file` / `--since` / `--stale-days` オプションあり。退行検出時は exit 1。 |
| `rag_smoke.py` | 固定クエリごとに期待根拠が字面検索の上位へ入るかを検査する。回答品質ではなく検索可能性の回帰を検出する。 |
| `cinii_search.py` | CiNii Research API で論文を検索し references.yml 登録用の YAML を出力する。 |
| `ndl_search.py` | NDL サーチ API で書籍・資料を検索し references.yml 登録用の YAML を出力する。 |
| `wiki_fetch.py` | MediaWiki API で Wikipedia 記事の全文を取得する（考証の裏取り用、転載禁止）。 |
| `browse.py` | 軽量ブラウザ操作 CLI。CDP 経由で可視 Chromium を操作し、抽出テキストのみを出力する。 |
| `explore_diff.py` | Wikipedia カテゴリと KB 収録の機械的差分を出す（探索ループ経路A用）。未収録候補を出力する。一覧記事・名前空間付きタイトルは既定で除外（`--include-lists` で無効化）、429/503 は自動リトライする。 |

## 導入手順（新しい KB リポジトリで使う場合）

### ① `kb-domain.yml` をルートに書く

ハーネスの各スクリプト・スキル・エージェントは、ドメイン名やパスをハードコードせず、リポジトリルートの `kb-domain.yml` を読んで動作する。
このリポジトリの実物を例として示す。

```yaml
domain:
  name: 沖縄空手史
  kb_title: 沖縄空手 OKF 知識ベース
  description: 沖縄空手の流派・型・人物・用語・史実を扱う知識ベース
  content_root: okinawa-karate
  lineage_example: 上地流系・劉衛流系など流派・系統単位
```

| フィールド | 必須 | 内容 |
|---|---|---|
| `domain.name` | 要 | ドメインの名称。エージェントが「専門家として」振る舞う対象を特定する。 |
| `domain.kb_title` | 要 | KB 自体の呼称。エージェントの説明文中で使う。 |
| `domain.description` | 要 | KB が扱う範囲の一文説明。 |
| `domain.content_root` | 要 | エンティティ Markdown を置くディレクトリ名。scripts はここを起点に走査する。 |
| `domain.lineage_example` | 任意 | 系統・分類の具体例。エージェントのプロンプトが参照する補助情報。 |

### ② `<content_root>/vocabulary.yml` を書く

`scripts/validate.py` はこのファイルを読み、エンティティの型・relations・タグを検証する。契約は次のとおりである。

```yaml
types:
  <型名>:
    directory: <対応ディレクトリ名>     # 必須。frontmatter の type とディレクトリの対応検査に使う
    extra_fields: [born, died]           # 任意。この型で追加必須になる frontmatter フィールド
    graph: false                         # 任意（既定 true）。false の型は relations を持てない
predicates:
  <述語名>:
    description: <説明>
    domain: [<型名>, ...]                # この述語の始点になれる型
    range: [<型名>, ...]                  # この述語の終点になれる型
tags:
  - <タグ1>
  - <タグ2>
```

- `types.<型>.extra_fields` に `born` または `died` を含めると、`validate.py` は値を「西暦4桁（`?` 付き可）」「西暦4桁+頃」「不詳」のいずれかの形式に限定して検証する（`PERSON_DATE_RE`）。それ以外のフィールド名は非空文字列であることのみ検査する。
- `types.<型>.graph: false` を指定した型のエンティティは `relations` フィールドを持てない（付与すると validate エラーになる）。索引・付録的なエンティティ型に使う。
- `predicates` の `domain` / `range` は、frontmatter の `relations` に書かれた `predicate` と `target` エンティティの型が一致するかを検査する型制約である。
- `tags` は frontmatter の `tags` に使える語の全量であり、一覧にない語を使うと validate エラーになる。
- `<content_root>/references.yml` の各エントリは optional key `pending`（非空文字列の待ち理由）を持てる。付与すると未参照 WARNING が個別に出ず件数集計の INFO 1行にまとまり、参照済みなのに `pending` が残っていると WARNING で警告される。

#### Claim 型（任意）

Claim のドメイン検証とグラフ用シリアライズは
[`kb-ontology-core`](https://github.com/lostandfound/kb-ontology-core) が正本である。
通常は `pip install -r requirements.txt` で依存を導入する。ソースから併用する場合は、
`kb-harness-core` と `kb-ontology-core` を同じ親ディレクトリへ配置してもよい。

`Claim` という型を `vocabulary.yml` に定義すると、確定した relation と区別して、出典と評価を伴う関係主張を記録できる。

```yaml
types:
  Claim:
    directory: claims
    graph: false
    extra_fields: [subject, status, confidence]
```

Claim frontmatter の契約は次のとおりである。

- `subject` / `object`: 存在するエンティティへのルート相対パス
- `predicate`: `vocabulary.yml` に定義済みの述語。domain/range 制約を適用する
- `status`: `proposed` / `accepted` / `disputed` / `rejected`
- `confidence`: `A` / `B` / `C` / `D`
- `sources`: 1件以上。通常エンティティと同じ出典検証を適用する

通常 relation と同じ subject / predicate / object の三つ組を重複登録すると `validate.py` はエラーにする。`export_graph.py` は Claim を通常の `nodes` / `edges` に混ぜず、独立した `claims` 配列へ出力する。値Claimは `property` と `value` を使い、`vocabulary.yml` の `properties` に定義した domain と value_type で検証する。関係形式との混在は禁止する。期間付き主張は現時点の共通契約に含まれない。

### ③ ルート `apm.yml` に依存を追加し、デプロイする

```yaml
# ローカルパスで参照する場合（モノレポ内・開発中）
dependencies:
  apm:
    - ../kb-harness-core

# GitHub 参照で導入する場合
dependencies:
  apm:
    - github: lostandfound/kb-harness-core
```

```bash
apm install --target claude
```

`apm install` はパッケージの `.apm/skills/` `.apm/agents/` を `.claude/skills/` `.claude/agents/` へ展開する。scripts はこのデプロイ対象に含まれないため、別途コピーまたは symlink を張る。

```bash
ln -s ../kb-harness-core/scripts scripts
```

## 実行前提

- Python 3.11 系（動作確認済み。3.9 以降の型ヒント構文 `X | None` を使うため 3.10 以上を推奨）
- 依存パッケージ: PyYAML（`validate.py` / `kb_config.py` が `import yaml` する。標準ライブラリ外で唯一必須）
- `cinii_search.py` を使う場合、環境変数 `CINII_APP_ID` が必要。リポジトリ直下の `.env`（`KEY=VALUE` 形式）からも自動で読み込む
- `apm` CLI（[microsoft/apm](https://github.com/microsoft/apm)）。スキル・エージェントのデプロイに使う
- `jq`（下記の hooks 例で使用）
- `browse.py` を使う場合は Playwright 相当の CDP 対応 Chromium 環境が別途必要

## 制約・既知の非対応

- **hooks は APM の管理対象外である。** `apm install` はスキル・エージェントのみをデプロイし、Claude Code の hooks（`.claude/settings.json` の `hooks` フィールド）は生成しない。導入先リポジトリで手書きする必要がある。このリポジトリでは `.md` 編集後に `validate.py` を自動実行する PostToolUse hook を次のように設定している。

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "f=$(jq -r '.tool_input.file_path // empty'); case \"$f\" in *.md) python3 scripts/validate.py >&2 || exit 2;; esac",
            "timeout": 60,
            "statusMessage": "validate.py 実行中..."
          }
        ]
      }
    ]
  }
}
```

- **エージェント定義の拡張子は正規化される。** `.apm/agents/` 配下では `*.agent.md` という名前で定義するが、`apm install --target claude` でデプロイすると `.claude/agents/` 配下では `.md`（例: `evidence-reviewer.agent.md` → `evidence-reviewer.md`）になる。
- scripts はエンティティ検証・生成のみを対象とし、hooks からの呼び出しも含めて APM のデプロイ機構の外側で手動配線する前提である。

## 運用

- 資産（スキル・エージェント）を修正するときは `.apm/` 側の正本を編集し、`apm install --target claude` で再デプロイする。`.claude/skills/` `.claude/agents/` の同名ファイルは生成物であり直接編集しない。
- `apm audit` で、正本（`.apm/`）とデプロイ先（`.claude/`）のドリフト（未反映の差分）を検査できる。
- scripts はこのパッケージの `scripts/` が正本である。導入先リポジトリのルート `scripts/` はそこへのコピーまたは symlink として運用する。
