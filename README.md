# kb-harness-core

ドメイン非依存の知識ベース（KB）運用ハーネス。

特定分野の知識を「エンティティ」（1 件 1 ファイルの Markdown。frontmatter に型・タグ・出典・他エンティティへの関係を持つ）の集合として管理する KB リポジトリに、`kb` CLI・検証スクリプト・各種エージェント向けのスキルとエージェント定義を提供する。

このパッケージ自体はどのドメインの知識も持たない。型・述語・タグの語彙やディレクトリ構成は導入先が `kb-domain.yml` と `vocabulary.yml` に書き、ハーネスはそれを読んで動作する。

## 特徴

- **検証** — frontmatter・リンク・relations の型制約・タグ語彙・出典参照を `vocabulary.yml` の契約で検査する
- **生成物同期** — 各型の `index.md` とルートの `graph.json` を決定論的に生成し、CI で差分を検出する
- **原子的な書き込み** — エンティティ・Claim・文献の追加を spec ファイルから行い、全体検証を通してから反映する。`--dry-run` で diff のみ確認できる
- **Claim** — 出典と確度を伴う関係主張を、確定した relation と区別して記録・検証・状態遷移する（[`kb-ontology-core`](https://github.com/lostandfound/kb-ontology-core) 連携）
- **OKF export** — 内部プロファイルを strict OKF v0.2 bundle に決定論的に変換する
- **RAG 評価** — 想定クエリに対する検索可能性の回帰検出と、評価履歴の退行検出
- **文献ワークフロー** — NDL サーチ・CiNii・NDL デジタルコレクションからの書誌登録をスキル化
- **エージェント連携** — 全コマンドが `--format json` と定義済み終了コードを持ち、スキル・エージェントから機械的に扱える

## クイックスタート

導入先 KB リポジトリの `apm.yml` に依存を追加する。

```yaml
dependencies:
  apm:
    - lostandfound/kb-harness-core
```

```bash
apm install --target claude                                   # スキル・エージェントを .claude/ へ展開
python3 -m pip install apm_modules/lostandfound/kb-harness-core   # kb CLI と Python API
kb doctor                                                     # 設定・依存・生成物の状態を診断
kb validate
kb sync --check
```

`kb-domain.yml` / `vocabulary.yml` の書き方を含む手順は [導入ガイド](docs/integration.md) を参照。

## 提供物

### `kb` CLI

| コマンド | 役割 |
|---|---|
| `kb project show` | `kb-domain.yml` の解決結果を表示 |
| `kb validate` | KB 全体を検証 |
| `kb index build\|check` / `kb graph build\|check` / `kb sync` | `index.md` と `graph.json` の生成・同期確認 |
| `kb entity create --from spec.yml` | spec からエンティティを原子的に作成 |
| `kb claim create\|inspect\|list\|validate\|transition` | Claim の作成・照会・検証・状態遷移 |
| `kb reference health\|spec\|create` | `references.yml` の点検・登録 spec 変換・原子的追加 |
| `kb eval summary\|smoke` | RAG 評価履歴の集計と検索可能性の確認 |
| `kb okf validate` / `kb export okf` | OKF v0.2 bundle の検証と export |
| `kb doctor` | 設定・依存バージョン・生成物の診断 |

全コマンドが `--format json` に対応する。詳細は [CLI リファレンス](docs/cli.md) を参照。

### スキル

| スキル | 用途 |
|---|---|
| `add-entity` | KB に新規エンティティを追加する確定的手順 |
| `find-book` | NDL サーチ API で書籍・資料を検索し `references.yml` に登録する |
| `find-paper` | CiNii API で論文を検索し `references.yml` に登録する |
| `ndl-digicolle` | NDL デジタルコレクション（個人送信サービス）で資料本文を確認する半自動手順 |
| `check-okf` | OKF v0.2 bundle の適合性・strict export・決定性を確認する |
| `audit-harness` | ハーネス文書群の整合性を監査し正本参照型で修正する |
| `review-doc` | README・方針書など説明文書 1 件を役割適合の観点でレビューする |

### エージェント

| エージェント | 用途 |
|---|---|
| `evidence-reviewer` | KB の主張と出典の対応、情報の鮮度、確度を審査する証拠レビュアー |
| `rag-tester` | KB だけを根拠に想定クエリへ回答を試み、回答不能・誤答・曖昧な箇所を報告する敵対的テスター |

### scripts

`kb` CLI に統合済みの機能の互換入口（`validate.py` / `new_entity.py` / `generate_index.py` / `export_graph.py` / `rag_smoke.py` / `eval_summary.py`）と、外部 API を叩く補助ツール（`ndl_search.py` / `cinii_search.py` / `wiki_fetch.py` / `explore_diff.py` / `browse.py`）、点検ツール（`refs_health.py` / `concerns_summary.py`）。一覧とオプションは [scripts リファレンス](docs/scripts.md) を参照。

## ドキュメント

- [導入ガイド](docs/integration.md) — apm install、pip install、scripts の配線、hooks、運用上の注意
- [設定リファレンス](docs/configuration.md) — `kb-domain.yml` / `vocabulary.yml` / `references.yml` / エンティティ spec / Claim / `evals/rag-eval.yml` の契約
- [CLI リファレンス](docs/cli.md) — `kb` の各コマンド、終了コード、JSON 出力、Python API
- [scripts リファレンス](docs/scripts.md) — 各スクリプトのオプション

## 動作要件

- Python 3.10 以上（CI は 3.12）
- PyYAML、[`kb-ontology-core`](https://github.com/lostandfound/kb-ontology-core) v0.2.0（`pyproject.toml` / `requirements.txt`）
- [`apm`](https://github.com/microsoft/apm) CLI
- 一部スクリプトは追加の環境（API キー、Chromium）を要する。[scripts リファレンス](docs/scripts.md) 参照

## 開発

```bash
pip install -r requirements.txt pytest
python3 -m pytest
```

`tests/test_distribution_alignment.py` は兄弟ディレクトリ `../kb-ontology-core`（v0.2.0）の存在を前提とする。

## ライセンス

MIT
