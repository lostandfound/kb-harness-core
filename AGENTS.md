# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## このリポジトリの性質

`kb-harness-core` は**ドメイン非依存のハーネス本体**であり、知識ベース（KB）そのものではない。
エンティティ Markdown も `kb-domain.yml` も**ここには存在しない**。導入先の KB リポジトリ側が持つ。

この非対称性が作業上の最大の注意点である。

- `kb validate` や `scripts/validate.py` は、このリポジトリのルートで単体実行しても `kb-domain.yml` が無いため失敗する。
- したがって動作確認は **tests/ 経由**（tmpdir に最小 KB を組み立てて API または CLI を呼ぶ）で行う。
- `scripts/hooks/pre-commit` は `kb validate` を呼ぶが、これは**導入先リポジトリで使う前提**のテンプレートである。このリポジトリ自体に入れると失敗する。

## コマンド

```bash
pip install -r requirements.txt pytest

python3 -m pytest                                    # 全テスト（CI と同じ）
python3 -m pytest tests/test_claim.py                # ファイル単位
python3 -m pytest tests/test_claim.py -k test_xxx    # 単体テスト
```

CI は Python 3.12 で `python3 -m pytest` を、`kb-ontology-core` あり・なしの 2 ジョブで回す。リンタは未導入。Claim を使うテストはオントロジーコアが無ければ skip され、`tests/test_distribution_alignment.py` は兄弟ディレクトリ `../kb-ontology-core`（`pyproject.toml` が宣言するタグと同じ版）が無ければ skip される。オントロジーコアなしの挙動は `tests/test_without_ontology_core.py` が固定する。

## アーキテクチャ

### 二層構造: `src/kb_harness` と `scripts/`

- `src/kb_harness/` が本体。`kb` CLI（`cli.py`）と計画・適用 API（`entity` / `claim` / `references` / `index` / `graph` / `sync` / `okf`）を持つ。書き込み系は「spec → 計画 → 一時 KB で全体検証 → 適用」の流れで統一されている（`staging.py`）。
- `scripts/` は歴史的な単体スクリプト群。`validate.py` / `new_entity.py` / `generate_index.py` / `export_graph.py` / `rag_smoke.py` / `eval_summary.py` は `kb_harness` の API を呼ぶ互換入口であり、ロジックを二重に持たない。外部 API を叩く補助ツール（NDL / CiNii / Wikipedia / ブラウザ）は `scripts/` にのみ存在する。
- 新しい検証・生成ロジックは `src/kb_harness/` に足し、必要なら `scripts/` から呼ぶ。逆方向（scripts にロジックを書く）はしない。

### 設定解決の層

すべてのコードはドメイン名・パスをハードコードしない。

1. `kb_harness.project.Project.discover()` — 起点から上へ `kb-domain.yml` を探索する。`scripts/kb_config.py` は同じ役割の互換入口。
2. `<content_root>/vocabulary.yml` — 型・述語・プロパティ・タグの語彙。`validate.py` の検査ルールは全部ここ由来。
3. `<content_root>/references.yml` — 文献レジストリ。出典 ID の解決先。

新しい検査を足すときは、語彙ファイルの契約（`docs/configuration.md` が正本）を壊さないこと。

### kb-ontology-core との境界

呼称: この文書とコード内のコメントでは、本パッケージ `kb-harness-core` を「ハーネス」、`kb-ontology-core` を「オントロジーコア」と呼ぶ。どちらも `-core` で終わるので、「コア」単独では書かない。

- 通常エンティティ（frontmatter・リンク・relations・タグ・出典）の検証は `kb_harness.validation` に閉じている。
- **Claim（出典と確度を伴う関係主張）の検証・状態遷移・シリアライズは `kb-ontology-core` が正本**。ここには実装を持たない。
- `kb_harness.ontology`（旧 `scripts/ontology_adapter.py`）が橋渡しで、責務は 2 つだけ：(a) `kb_ontology_core` の import 解決（pip 導入か、兄弟ディレクトリ `../kb-ontology-core/src` へのフォールバック）、(b) オントロジーコアの `Diagnostic` をハーネスの構造化診断（`code` / `field` / `context`）へ翻訳。解決は**遅延**で、Claim の検証・出力・語彙構築を呼んだ時点で行う。オントロジーコアはモジュール読み込み時に import しない。Claim を使わない KB はオントロジーコアなしで全機能が動き、Claim を扱おうとしたときだけ `ontology.core.missing` で止まる。
- 依存タグは `pyproject.toml` / `requirements.txt` に固定し、`kb doctor` と `test_distribution_alignment.py` が整合を検査する。タグを上げるときは両方と CI の clone ブランチを同時に更新する。

Claim のルール（許容 status、遷移、domain/range 制約、値Claim の形式）を変えたくなったら、変更先は `kb-ontology-core` であってこのリポジトリではない。翻訳層に条件分岐を足して挙動を変えるのは層の侵犯。

### 資産の正本とデプロイ

- スキル・エージェントの正本は `.apm/skills/` `.apm/agents/`。`apm install --target claude` が `.claude/` 配下へ展開する。**`.claude/` 側は生成物であり編集しない。**
- エージェント定義は `.apm/` では `*.agent.md`、デプロイ後は `*.md` に正規化される。
- `scripts/` は APM のデプロイ対象外。導入先ではコピーか symlink で手動配線する。
- hooks も APM 管理外（`docs/integration.md` 参照）。
- 導入先が本パッケージを submodule + `scripts/` symlink で組み込んでいる場合、導入先で実行されるのは submodule 側のコードである。ハーネスの修正は本リポジトリ側をコミットし、導入先で submodule 参照を更新して反映する。

## 変更時の作法

- README.md と `docs/` はこのパッケージの**対外契約の正本**である。`kb` サブコマンドの追加・変更は `docs/cli.md` と README の一覧を、スクリプトの追加・オプション変更は `docs/scripts.md` を、語彙・spec 契約の変更は `docs/configuration.md` を同時に更新する。乖離はハーネス利用者側の破損に直結する。
- `.apm/skills/audit-harness` は、文書・スキル・エージェント・スクリプト間の整合性を監査するスキル。大きめの変更の後に使える。
- 記述言語は日本語、常体（「〜である」「〜する」）で統一されている。
