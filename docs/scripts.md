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
| `--check-urls` | `references.yml` の URL に到達可能か HTTP で確認する |

### new_entity.py

エンティティ雛形（frontmatter・見出し構成）を生成する。

```bash
python3 scripts/new_entity.py <type> <slug> [--root DIR]
```

### generate_index.py

各ディレクトリの `index.md` にエンティティ一覧を生成する。

```bash
python3 scripts/generate_index.py [--root DIR]
```

### export_graph.py

ナレッジグラフ（`nodes` / `edges` / `claims`）を JSON でエクスポートする。既定では出力前に `validate()` を実行し、エラーがあれば中断する。

```bash
python3 scripts/export_graph.py [--root DIR] [--out FILE] [--force]
```

| オプション | 内容 |
|---|---|
| `--out` | 出力先。省略時は標準出力 |
| `--force` | 検証をスキップする（デバッグ用） |

## 評価

### rag_smoke.py

`evals/rag-eval.yml` の各クエリについて、期待根拠が字面検索の上位へ入るかを検査する。回答品質ではなく検索可能性の回帰を検出する。失敗があれば exit 1。

```bash
python3 scripts/rag_smoke.py [--root DIR] [--eval-file FILE] [--limit N]
```

### eval_summary.py

`evals/rag-eval.yml` の最新判定を集計し、退行（過去 OK → 最新非 OK）を検出する。退行検出時は exit 1。

```bash
python3 scripts/eval_summary.py [--eval-file FILE] [--since YYYY-MM-DD] [--stale-days N]
```

| オプション | 内容 |
|---|---|
| `--since` | 指定日以降の `history` のみ集計する |
| `--stale-days` | 未評価とみなす経過日数の閾値（既定 30） |

## 文献・外部情報

### ndl_search.py

NDL サーチ API で書籍・資料を検索し、`references.yml` 登録用の YAML を出力する。

```bash
python3 scripts/ndl_search.py <query> [--count N] [--title-only] [--mediatype books|periodicals]
```

### cinii_search.py

CiNii Research API で論文を検索し、`references.yml` 登録用の YAML を出力する。環境変数 `CINII_APP_ID` が必要（リポジトリ直下の `.env` からも読む）。

```bash
python3 scripts/cinii_search.py <query> [--count N]
```

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
python3 scripts/browse.py goto <url>
python3 scripts/browse.py text [--limit N]
python3 scripts/browse.py find <word> [--ctx N]
python3 scripts/browse.py click <target>
python3 scripts/browse.py fill <selector> <value>
python3 scripts/browse.py press <key>
```

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

懸念台帳（Markdown）の状態別集計と、着手可能な懸念の抽出。台帳の形式は導入先が定める。雛形と状態語彙は [導入ガイド](integration.md#7-運用ファイルを置く任意) を参照。

```bash
python3 scripts/concerns_summary.py [--ledger FILE]
```

## 補助

### hooks/pre-commit, install-hooks.sh

導入先リポジトリ向けの pre-commit テンプレート。ステージに `.md` / `.yml` / `.py` が含まれるとき次を順に実行し、いずれかが失敗すればコミットを中止する。`install-hooks.sh` が自身と同じ場所の `hooks/pre-commit` を `.git/hooks/pre-commit` へ冪等にコピーする（`bash apm_modules/lostandfound/kb-harness-core/scripts/install-hooks.sh`）。テンプレートは `kb` CLI だけを呼び、導入先の `scripts/` には依存しない。

1. `kb validate`（`kb-domain.yml` の `validate.extra_checks` もここで走る）
2. `tests/` が存在すれば `python3 -m pytest tests -q`
3. `evals/rag-eval.yml` が存在すれば `kb eval smoke`
4. `.kb/hooks/pre-commit.d/` が存在すれば、その中の実行可能ファイルを名前順に実行する

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
