# Changelog

## Unreleased

### Fixed
- pre-commit テンプレートが `tests/` と `evals/rag-eval.yml` の存在を前提にしていたのを、存在するときだけ実行するよう修正。併せて `.kb/hooks/pre-commit.d/*` を名前順に実行し、テンプレートを編集せず導入先固有のチェックを足せるようにした（#3）

### Changed
- 同梱スキルから導入先固有の記述（AGENTS.md の行数上限、`packages/kb-harness-core` パス、born/died、特定考証エージェント名、CONTRIBUTING の節番号）を除き、正本参照に置き換えた
- 導入先ルートの `scripts/` をモジュールへの symlink にする手順を廃止。補助スクリプトは `apm_modules/lostandfound/kb-harness-core/scripts/<name>.py` で直接呼び、pre-commit テンプレートは `kb validate` / `kb eval smoke` のみを呼ぶ。`install-hooks.sh` は自身の位置から `hooks/pre-commit` を探すので `apm_modules` 配下から実行できる（#4）
- 動作確認する apm の版を 0.32 に上げた。0.32 で `--target claude` / `--target codex` の配置と `apm audit` を確認済み。導入ガイドに、配置先 target の指定が必須であること、短縮 SHA での固定が拒否されること、Codex ではエージェントの `tools` が落ちることを追記した

### Added
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
