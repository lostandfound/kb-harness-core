---
name: audit-harness
description: ハーネス文書群（CLAUDE.md・CONTRIBUTING・スキル・エージェント・スクリプト）の整合性を監査し正本参照型で修正する手順。「整合性チェック」「ハーネス監査」「文書の陳腐化確認」で使用。大きな構造変更（語彙追加・スクリプト追加・規約変更）の後に実行する。
---

ハーネス文書群の整合性を監査するときは以下を実行する。監査は読み取り → 修正 → 検証の順。

## 対象（すべて読む）

- `kb-domain.yml`（ドメイン定義。実態との乖離も監査対象）
- CLAUDE.md（**25 行以内の制約あり**）
- CONTRIBUTING.md、README.md
- docs/expansion-loop.md、docs/BACKLOG.md、docs/CONCERNS.md
- packages/kb-harness-core/.apm/ 配下の全 SKILL.md・エージェント定義（**KB ハーネス資産の正本**。`.claude/` 配下の同名資産は `apm install` による生成物 — 正本と `.claude/` 側の同一性も確認し、ドリフトがあれば正本を直して `apm install` で再デプロイする）
- .claude/skills/ .claude/agents/ 配下のうちパッケージ外の資産（プロジェクト固有スキル等）
- apm.yml・packages/kb-harness-core/apm.yml（依存宣言・パッケージ内容の一致）
- scripts/*.py の CLI 実引数（--help 相当）と docstring（正本は `packages/kb-harness-core/scripts`、リポジトリルート `scripts/` は symlink）
- `<content_root>/vocabulary.yml`、`references.yml`（content_root は `kb-domain.yml` の `domain.content_root`）のスキーマ実態
- evals/ 配下、.env.example、.github/workflows/

## 監査の 5 観点

1. **文書↔実装の乖離** — 文書が語るコマンド・フラグ・パス・フィールド名が実在するか。スクリプトの実引数と文書の記述を突き合わせる
2. **文書間の矛盾** — 同じ規約が複数文書で違う値・表現になっていないか（述語・born/died 値域・sources 形式・レビュー工程）
3. **陳腐化ハードコード** — 語数・件数・列挙のハードコードで実態に追随していないもの。前例: 「述語 6 語」（2 回再発）。一覧を載せる文書は正本（vocabulary.yml 等）と突き合わせる
4. **新規要素の記載漏れ** — 最近増えたファイル・スキル・エージェント・スクリプトが、README / CONTRIBUTING / CLAUDE.md の言及すべき箇所で欠けていないか（`git log --oneline -20` で最近の追加を把握）
5. **CLAUDE.md の過不足** — 25 行以内を維持しつつ、現行ハーネスへの導線が過不足ないか

## 修正方針

- **正本参照型**で直す: 値の重複記載を減らし、正となるファイル（vocabulary.yml / CONTRIBUTING / スクリプト自身）を指す記述にする。列挙をやむを得ず残す場合は「正は◯◯」と明記
- どちらが正か判断できない矛盾は修正せずユーザーへ報告
- 発見した不整合はすべて報告する（修正済み / 報告のみ を区別）。信頼性に関わるものは docs/CONCERNS.md に記録

## 検証

修正後: `python3 -m unittest discover tests` 全パス + `python3 scripts/validate.py` エラーゼロ + `wc -l CLAUDE.md` で 25 行以内 → コミット（docs: / fix:、pre-commit hook 成功確認）。
