# Changelog

## Unreleased

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
