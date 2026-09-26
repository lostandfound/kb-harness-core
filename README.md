# kb-harness-core

特定分野に依存しない、知識ベース（KB: Knowledge Base）運用ハーネス（基盤ツールキット）。

## 概要

`kb-harness-core` は、構造化された知識ベース（KB）リポジトリの構築・運用・保守を支援するツール群である。

対象とする KB リポジトリでは、個々の知識を「エンティティ」（1 件につき 1 つの Markdown ファイル）として管理する。各エンティティの frontmatter（メタデータ）には、型・タグ・出典・他エンティティとの関係（relations）を構造化して記述する。

本パッケージは、これらを安全かつ一貫して管理するために、以下の資産を提供する。

- **`kb` CLI**: スキーマ検証、関連グラフの構築、インデックス同期、原子的書き込みなどを行うコマンドラインツール
- **検証スクリプト**: リンク切れ、語彙の整合性、書誌情報の検査などを行うツール群
- **エージェント定義・スキル**: AI エージェント（Claude Code 等）が KB の調査・執筆・レビューを自律的に進めるためのワークフロー

本パッケージ自体には特定の専門分野（ドメイン）の知識は含まれていない。エンティティの型、関係（述語）、タグの語彙、ディレクトリ構成などは、導入先リポジトリ側の `kb-domain.yml` や `vocabulary.yml` で定義する。ハーネスはその定義を読み込んで動作するため、あらゆる領域の知識ベースに適用できる。

## 主な特徴

- **厳格な整合性検証** — `vocabulary.yml` に定義されたスキーマに基づき、frontmatter、リンク切れ、relations の型制約、タグ語彙、出典の参照先を網羅的に検査する。
- **決定論的なインデックス・グラフ同期** — 各型の目次となる `index.md` や、リポジトリ全体の関連図を表す `graph.json` を決定論的（再現可能）に自動生成し、未更新の差分を CI で検出する。
- **原子的（アトミック）な変更適用** — エンティティ・Claim・文献の追加を spec ファイルから行い、一時環境での全体検証を通過した場合にのみ実ファイルへ反映する。`--dry-run` による事前差分確認も可能。
- **Claim（仮説・主張）のライフサイクル管理** — 確定した関係（relation）とは区別し、出典や確度（確信度）を伴う不確定な関係主張を「Claim」として記録・検証・状態遷移する（[`kb-ontology-core`](https://github.com/lostandfound/kb-ontology-core) と連携）。
- **OKF エクスポート** — 内部のデータ構造を、オープン知識ベース規格である strict OKF (Open Knowledge Format) v0.2 バンドルへ決定論的に変換・出力する。
- **RAG 評価と退行検知** — 想定クエリに対してエンティティが正しく検索・参照されるかをテストし、評価履歴を通じて検索精度の劣化（リグレッション）を検知する。
- **文献調査・書誌登録ワークフロー** — NDL サーチ（国立国会図書館）、CiNii（学術論文）、NDL デジタルコレクションなどから書誌情報を検索し、`references.yml` へ登録する手順をスキル化している。
- **AI エージェント親和性** — 全コマンドが `--format json` 出力と明確な終了コードに対応しており、AI エージェントや各種スクリプトから自動実行・判定しやすい設計になっている。

## クイックスタート

導入先 KB リポジトリの `apm.yml` に依存関係を追加する。

```yaml
dependencies:
  apm:
    - lostandfound/kb-harness-core
```

パッケージをインストールし、KB の状態を診断・検証する。

```bash
apm install --target claude                                       # スキルとエージェント定義を .claude/ へ展開
python3 -m pip install apm_modules/lostandfound/kb-harness-core   # kb CLI と Python API をインストール
kb doctor                                                         # 設定・依存パッケージ・生成物の整合性を診断
kb validate                                                       # KB 全体のスキーマとリレーションを検証
kb sync --check                                                   # index.md や graph.json の未反映差分を検査
```

設定ファイル（`kb-domain.yml` / `vocabulary.yml`）の書き方を含む詳しい手順は [導入ガイド](docs/integration.md) を参照。

## 導入先 KB の標準構成

導入先リポジトリの標準的なディレクトリ構成は以下の通りである。

```text
<repo_root>/
├── kb-domain.yml                 # 【必須】ドメイン定義・パス設定
├── graph.json                    # 【生成物】関連グラフ（kb sync 等で自動生成）
├── views/                        # 【任意】ビュー定義（kb-domain.yml の views.root で有効化）
│   └── index.md                  # 【生成物】ビュー一覧（kb sync が生成）
├── evals/
│   └── rag-eval.yml              # 【任意】RAG 評価クエリ設定
├── docs/
│   ├── CONCERNS.md               # 【任意】未整理の懸念や課題を記録する受信箱
│   └── BACKLOG.md                # 【任意】着手を決定した将来タスク
└── <content_root>/
    ├── vocabulary.yml            # 【必須】型・述語・タグの語彙定義
    ├── references.yml            # 【任意】文献・出典レジストリ
    ├── index.md                  # 【自動同期】ルートインデックス
    ├── log.md                    # 【任意】OKF 仕様上の更新履歴
    └── <type-directory>/
        ├── index.md              # 【自動同期】型別インデックス
        ├── log.md                # 【任意】OKF 仕様上の更新履歴
        └── <entity>.md           # 各エンティティの Markdown ファイル
```

### 各ファイル・ディレクトリの役割

- **`<content_root>` / `<type-directory>`**: 実際のディレクトリ名は、それぞれ `kb-domain.yml` および `vocabulary.yml` の設定に従って決定される。
- **`graph.json`**: エンティティ間の関係を記録した知識グラフファイル。`kb graph build` または `kb sync` によって自動生成される。
- **`index.md`**: 各ディレクトリのエンティティ一覧などを記載するインデックス文書。ファイル内の管理対象セクションが `kb sync` によって自動同期される。
- **`log.md`**: 各階層の更新履歴を記録するファイル（OKF v0.2 仕様で予約されているが、必須ではない）。
- **`docs/CONCERNS.md` / `docs/BACKLOG.md`**: 知識の抜け漏れや運用上の課題を記録するための運用文書（任意）。ファイルが存在しなくても検証エラーにはならない。また、エンティティそのものではないため OKF バンドルには含めない。 ハーネスは自動生成しないため、使う場合は [導入ガイド](docs/integration.md#8-運用ファイルを置く任意) の雛形から手で置く。
- **その他の `docs/` 配下**: 上記以外のファイル名や用途は、導入先が自由に定めてよい。

## 提供物

### `kb` CLI

| コマンド | 役割 |
|---|---|
| `kb project show` | `kb-domain.yml` の設定解決結果を表示 |
| `kb flashcards` | 任意の KB をローカルの学習カード画面で学ぶ |
| `kb validate` | KB 全体のスキーマ・リンク・リレーションを検証 |
| `kb index build\|check` / `kb graph build\|check` / `kb sync` | `index.md` と `graph.json` の自動生成・差分検査 |
| `kb entity create --from spec.yml` | spec ファイルからエンティティを検証付きで原子的に作成 |
| `kb claim create\|inspect\|list\|validate\|transition` | Claim の作成・照会・一覧表示・検証・状態遷移 |
| `kb view list\|resolve\|validate` | エンティティの外に置いたビュー（束ね・導出）の一覧・解決・検証 |
| `kb reference health\|spec\|create` | `references.yml` の点検・登録 spec への変換・原子的追加 |
| `kb eval summary\|smoke` | RAG 評価履歴の集計および検索可能性の回帰確認 |
| `kb okf validate` / `kb export okf` | OKF v0.2 バンドルの検証およびエクスポート |
| `kb doctor` | 設定・依存パッケージのバージョン・生成物の状態診断 |

すべてのコマンドが `--format json` による構造化出力に対応している。詳細は [CLI リファレンス](docs/cli.md) を参照。

### スキル

AI エージェント（Claude Code 等）から呼び出して利用する定義済みワークフロー。

| スキル | 用途 |
|---|---|
| `add-entity` | 対話的に新規エンティティを作成し、検証を経て配置するワークフロー |
| `find-book` | NDL サーチ API で書籍・資料を検索し、`references.yml` に登録する |
| `find-paper` | CiNii API で学術論文を検索し、`references.yml` に登録する |
| `ndl-digicolle` | NDL デジタルコレクション（個人送信サービス）で資料本文を確認しながら書誌・引用を整える手順 |
| `check-okf` | OKF v0.2 バンドルの仕様適合性・エクスポート結果・決定性を確認する |
| `expand-kb` | 未収録項目の候補選定・調査・執筆・レビュー・検証までの一連の追加サイクルを進める |
| `explore-kb` | 外部の一覧・カテゴリ・文献から未収録候補を発見し、検討用として `BACKLOG.md` へ渡す |
| `review-entity-model` | 型の適合性、エンティティ境界、ノード化、relation、タグの設計をレビューする |
| `audit-harness` | ハーネス関連ドキュメント間の整合性を監査し、正本（一次情報）に沿って修正する |
| `review-doc` | README や運用方針書などの説明文書が、その目的に適した構成・記述になっているかをレビューする |

### エージェント

特定のレビュー・テスト作業を自律的に担当するサブエージェント。

| エージェント | 用途 |
|---|---|
| `evidence-reviewer` | KB 内の記述と出典文献の対応関係、情報の鮮度、確度を審査する証拠レビュアー |
| `rag-tester` | KB の記述のみを根拠に想定クエリへの回答を試み、回答不能・誤答・曖昧な記述を洗い出す敵対的テスター |

### scripts

`kb` CLI に統合された各機能の後方互換スクリプト（`validate.py` / `new_entity.py` / `generate_index.py` / `export_graph.py` / `rag_smoke.py` / `eval_summary.py`）に加え、外部 API を利用する補助ツール（`ndl_search.py` / `cinii_search.py` / `wiki_fetch.py` / `explore_diff.py` / `browse.py`）や点検ツール（`refs_health.py` / `concerns_summary.py`）を提供している。各スクリプトの一覧とオプションについては [scripts リファレンス](docs/scripts.md) を参照。

## ドキュメント

- [導入ガイド](docs/integration.md) — インストール手順、scripts の配置、Git hooks 設定、運用上の注意点
- [設定リファレンス](docs/configuration.md) — `kb-domain.yml` / `vocabulary.yml` / `references.yml` / エンティティ spec / Claim / `evals/rag-eval.yml` のスキーマ仕様
- [CLI リファレンス](docs/cli.md) — `kb` コマンドの詳細、終了コード、JSON 出力仕様、Python API
- [scripts リファレンス](docs/scripts.md) — 提供スクリプトの一覧とオプション
- [設計判断](docs/design-rationale.md) — Markdown を正データとし、グラフ DB を採用しない理由と再検討の条件。語彙を小さく保つ理由とビューの位置づけ
- [考察メモ](docs/notes/) — 設計判断の背景にある議論の記録

## 動作要件

- **Python**: 3.10 以上（CI は 3.12 で実行）
- **主要な依存パッケージ**: PyYAML、[`kb-ontology-core`](https://github.com/lostandfound/kb-ontology-core) v0.2.0（詳細は `pyproject.toml` / `requirements.txt` を参照）
- **ツール**: [`apm`](https://github.com/microsoft/apm) CLI 0.32 以上
- **その他**: 一部の補助スクリプトは追加の環境（外部 API キー、Chromium 等）を必要とする（詳細は [scripts リファレンス](docs/scripts.md) を参照）

## 開発

```bash
pip install -r requirements.txt pytest
python3 -m pytest
```

※ `tests/test_distribution_alignment.py` を実行する場合は、兄弟ディレクトリに `../kb-ontology-core`（v0.2.0）が存在することを前提とする。

### リリース

1. `CHANGELOG.md` の Unreleased を版と日付に確定し、`pyproject.toml` / `src/kb_harness/__init__.py` / `apm.yml` の版を揃えて `main` にマージする。
2. Actions の **Tag release** ワークフロー（`.github/workflows/release.yml`）を `main` で手動実行し、`version` にその版を渡す。版ファイルが一致するコミットにだけ注釈付きタグ `v<version>` が打たれる。`target` に SHA を渡せば `main` 上の特定コミットを指せる。
3. GitHub Releases は使わない。導入先は `apm.yml` / `requirements.txt` でタグを指す。

## ライセンス

MIT
