# scripts リファレンス

`scripts/` 配下の CLI 一覧。`--root` を持つものはコンテンツルートを指定でき、省略時は `kb-domain.yml` の `domain.content_root` から自動解決する。導入先からは `python3 apm_modules/lostandfound/kb-harness-core/scripts/<name>.py` のようにモジュール配下のパスで呼ぶ（導入先ルートに `scripts/` の symlink は張らない。[導入ガイド](integration.md) §5）。

`kb_config.py` と `ontology_adapter.py` は共有モジュールであり、単体では実行しない。

「検証・生成」「評価」の各スクリプトは `kb` CLI と同じ API を呼ぶ互換入口である。新規導入では [`kb` CLI](cli.md) を使う。

## 検証・生成

### validate.py

frontmatter・リンク・relations・語彙・書誌参照（ファイル単位 `sources` + 本文インライン `（出典: ref-id）`）・Claim・`evals/rag-eval.yml` を検証する。エラーがあれば exit 1。

```bash
python3 scripts/validate.py [--root DIR] [--fix-timestamps] [--check-urls]
```

| オプション | 内容 |
|---|---|
| `--fix-timestamps` | frontmatter の `timestamp` を現在時刻で補正する |
| `--check-urls` | エンティティの `sources` と `references.yml` の出典に到達できるか確認する。DOI は DOI レジストリで登録の有無を確かめ、レジストリに届かないときは ERROR にせず WARNING にする（詳細は [CLI リファレンス](cli.md) の `kb validate`） |

### new_entity.py

エンティティ雛形（frontmatter・見出し構成）を生成する。見出しは `vocabulary.yml` の型の `sections`、無ければ 概要 / 詳細 / 関連項目。型名による既定の章立ては持たない。

```bash
python3 scripts/new_entity.py <type> <slug> [--root DIR]
```

### generate_index.py

各ディレクトリの `index.md` にエンティティ一覧を生成する。

```bash
python3 scripts/generate_index.py [--root DIR]
```

### export_graph.py

ナレッジグラフ（`nodes` / `edges` / `claims`、`views.root` を設定した KB では `views` も）を JSON でエクスポートする。既定では出力前に `validate()` を実行し、エラーがあれば中断する。

```bash
python3 scripts/export_graph.py [--root DIR] [--out FILE] [--force]
```

| オプション | 内容 |
|---|---|
| `--out` | 出力先。省略時は標準出力 |
| `--force` | 検証をスキップする（デバッグ用） |

## 評価

### rag_smoke.py

`evals/rag-eval.yml` の各クエリについて、期待根拠が字面検索の上位へ入るかを検査する。回答品質ではなく検索可能性の回帰を検出する。失敗があれば exit 1。`kb eval smoke` の互換入口で、実装は `kb_harness.evaluation`。`--root` 省略時は cwd から上へ `kb-domain.yml` を探して解決する。

```bash
python3 scripts/rag_smoke.py [--root DIR] [--eval-file FILE] [--limit N]
```

### eval_summary.py

`evals/rag-eval.yml` の最新判定を集計し、退行（過去 OK → 最新非 OK）を検出する。退行検出時は exit 1。`kb eval summary` の互換入口で、実装は `kb_harness.evaluation`（`--since` / `--stale-days` / `--open` と `INVALID` のスキーマ報告はスクリプト側だけが持つ）。

```bash
python3 scripts/eval_summary.py [--eval-file FILE] [--since YYYY-MM-DD] [--stale-days N] [--open]
```

| オプション | 内容 |
|---|---|
| `--since` | 指定日以降の `history` のみ集計する |
| `--stale-days` | 未評価とみなす経過日数の閾値（既定 30） |
| `--open` | 未解決の欠落のみを BACKLOG 転記用の行形式で出力する（退行検出の exit code は据え置き） |

## 文献・外部情報

### ndl_search.py

NDL サーチ API で書籍・資料を検索し、`references.yml` 登録用の YAML を出力する。

```bash
python3 scripts/ndl_search.py <query> [--count N] [--title-only] [--mediatype books|periodicals] [--format yaml|json]
```

`--format` は出力形式を切り替える（既定 `yaml`）。`json` はスクリプトからのパース用。

### cinii_search.py

CiNii Research API で論文を検索し、`references.yml` 登録用の YAML を出力する。環境変数 `CINII_APP_ID` が必要（リポジトリ直下の `.env` からも読む）。

```bash
python3 scripts/cinii_search.py <query> [--count N] [--format yaml|json]
```

`--format` は `ndl_search.py` と同じ（既定 `yaml`）。

### wiki_fetch.py

MediaWiki API で Wikipedia 記事の全文を取得する。考証の裏取り用であり、取得した本文の転載は禁止する。

```bash
python3 scripts/wiki_fetch.py <title> [--lang ja]
```

### explore_diff.py

Wikipedia カテゴリと KB 収録の機械的差分を出し、未収録候補を出力する。カテゴリ省略時は `kb-domain.yml` の `exploration.wikipedia_categories` を読む。一覧記事・名前空間付きタイトルは既定で除外し、429/503 は自動リトライする。

```bash
python3 scripts/explore_diff.py [category ...] [--depth N] [--root DIR] [--include-lists]
```

### browse.py

軽量ブラウザ操作 CLI。CDP 経由で可視 Chromium を操作し、抽出テキストのみを出力する。`ndl-digicolle` スキルが使う。Playwright 相当の CDP 対応 Chromium 環境が別途必要。

```bash
python3 scripts/browse.py open
python3 scripts/browse.py close
python3 scripts/browse.py url
python3 scripts/browse.py goto <url>
python3 scripts/browse.py text [--limit N]
python3 scripts/browse.py find <word> [--ctx N]
python3 scripts/browse.py click <target>
python3 scripts/browse.py fill <selector> <value>
python3 scripts/browse.py press <key>
```

`open` / `close` は CDP 対応 Chromium の起動・終了、`url` は現在タブの URL 取得。

## 点検

### refs_health.py

`references.yml` の健全性を点検する。Web 資料の到達確認日の古さと、`pending` の滞留期間を表面化させる。

```bash
python3 scripts/refs_health.py [--refs FILE] [--stale-days N] [--lineage] [--pending] [--record-check]
```

| オプション | 内容 |
|---|---|
| `--refs` | レジストリのパス。省略時は `kb-domain.yml` の content_root 配下 |
| `--stale-days` | 到達確認が古いとみなす経過日数（既定 180） |
| `--lineage` | lineage 未判定の文献のみ出力 |
| `--pending` | `pending` の文献のみを滞留日数順に出力 |
| `--record-check` | 到達確認を実行し、成功した文献の `checked` を更新（ネットワーク使用） |

### concerns_summary.py

懸念台帳の状態別集計と、着手可能な懸念の抽出。`kb-domain.yml` に `concerns.root` があれば構造化した台帳（1 件 1 YAML、[設定リファレンス](configuration.md#懸念台帳任意)）を `kb_harness.concerns` で読む互換入口として動き、`kb concern summary` / `kb concern list --actionable` と同じ台帳を集計する。無いか `--ledger` を渡したときは、旧来の Markdown の台帳（行末の `status:` で分類）を集計する。移行の手順は [導入ガイド](integration.md#8-運用ファイルを置く任意) を参照。

```bash
python3 scripts/concerns_summary.py [--ledger FILE] [--actionable]
```

| オプション | 内容 |
|---|---|
| `--ledger` | Markdown の台帳のパス（既定 `docs/CONCERNS.md`）。渡すと `concerns.root` があっても Markdown を読む |
| `--actionable` | 着手可能な懸念のみを 1 行ずつ出力する |

## 補助

### hooks/pre-commit, install-hooks.sh

導入先リポジトリ向けの pre-commit テンプレート。ステージに `.md` / `.yml` / `.py` が含まれるとき次を順に実行し、いずれかが失敗すればコミットを中止する。`install-hooks.sh` が自身と同じ場所の `hooks/pre-commit` を `.git/hooks/pre-commit` へ冪等にコピーする（`bash apm_modules/lostandfound/kb-harness-core/scripts/install-hooks.sh`）。テンプレートは `kb` CLI だけを呼び、導入先の `scripts/` には依存しない。

1. `kb validate`（`kb-domain.yml` の `validate.extra_checks` もここで走る）
2. `kb sync --check`（index / graph / views の陳腐化。`kb validate` が通っても独立に失敗しうる）
3. `tests/` が存在すれば `python3 -m pytest tests -q`
4. `evals/rag-eval.yml` が存在すれば `kb eval smoke`
5. `.kb/hooks/pre-commit.d/` が存在すれば、その中の実行可能ファイルを名前順に実行する

導入先固有のチェックはテンプレートを編集せず `.kb/hooks/pre-commit.d/` に置く。`kb-domain.yml` の `validate.extra_checks` に登録すれば `kb validate` 側で実行されるので、通常はそちらを使う。

### check_source_attrition.py

改版で先行する出典の記述が失われていないかを検出する。複数の出典を並存させるエンティティに別の出典の記述を追記するとき、本文を新しい出典に沿って書き直してしまい、先行出典の段落がまとめて消えることがある。形式は壊れないので `kb validate` は通る。

```bash
python3 scripts/check_source_attrition.py [PATH ...] [--base REV] [--strict]
```

改版前（既定は `HEAD`）と現在を突き合わせ、front matter の `sources` が挙げる ref-id ごとに主張単位の出典表記（`（出典: <ref-id>）`）の数を比べる。過半が失われた出典があれば内訳を標準エラーに出して終了コード 1 を返す。`sources` から ref-id が外された場合も、本文に表記が残っていても失われたものとして扱う（この状態は `kb validate` では検出できない）。

引数を省略するとステージ済みの変更（`--diff-filter=M`）を対象にする。新規追加ファイルは比較対象がないので見ない。推敲で段落をまとめた程度の減少は見逃す。すべての減少を検出するには `--strict` を使う。意図した削除は `KB_ALLOW_SOURCE_ATTRITION=1` で通す。

`.kb/hooks/pre-commit.d/` から呼び出して使う。

### verify_turn.sh

Claude Code の Stop hook から呼び、ターンの終了を `kb validate` と `kb sync --check` で閉じる。pre-commit が閉じるのはコミットするときだけで、コミットせずに終わるターンでは検証が一度も走らない。

標準入力でフックのペイロードを受け取り、検証に失敗すると終了コード 2 を返す。終了コード 2 のとき標準エラーがそのまま Claude に返るため、指示しなくてもその場で修正してからターンを終える。終了コード 1 ではブロックにならない。

`stop_hook_active` が真のときは何もしない（停止と再開が繰り返されるのを防ぐ）。カレントディレクトリに `kb-domain.yml` がない場合も何もしないので、KB 以外の作業では起動しない。

導入先の `.claude/settings.json` に登録する。

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash apm_modules/lostandfound/kb-harness-core/scripts/verify_turn.sh"
          }
        ]
      }
    ]
  }
}
```
