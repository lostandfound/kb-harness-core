# Changelog

## Unreleased

### Fixed
- pre-commit テンプレートが `tests/` と `evals/rag-eval.yml` の存在を前提にしていたのを、存在するときだけ実行するよう修正。併せて `.kb/hooks/pre-commit.d/*` を名前順に実行し、テンプレートを編集せず導入先固有のチェックを足せるようにした（#3）

### Changed
- 導入先ルートの `scripts/` をモジュールへの symlink にする手順を廃止。補助スクリプトは `apm_modules/lostandfound/kb-harness-core/scripts/<name>.py` で直接呼び、pre-commit テンプレートは `kb validate` / `kb eval smoke` のみを呼ぶ。`install-hooks.sh` は自身の位置から `hooks/pre-commit` を探すので `apm_modules` 配下から実行できる（#4）

### Added
- `kb-domain.yml` に `index.by_tag` / `index.tag_labels` を追加。有効にすると `kb sync` / `kb index build` / `kb entity create` がルート `index.md` のマーカー区間にタグ別（分野別）一覧を生成し、`kb sync --check` が陳腐化を検出する（#1）
- `kb-domain.yml` に `validate.extra_checks` を追加。`kb validate` が本体の検証後に導入先固有のコマンドを順に実行して失敗を ERROR に集約し、`kb doctor` がコマンドの存在を WARNING で報告する（#2）
- `vocabulary.yml` の型定義に `sources_required: false` を追加。出典を求めない型（個人メモ等）を定義できる。`kb validate` と `kb entity create` の両方が従う

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
