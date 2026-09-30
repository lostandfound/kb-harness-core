---
description: kb-harness-core を使う知識ベースでの作業の入口（問い合わせへの答え方、主要な手順、コミット前の検証）
applyTo: "**"
---

このリポジトリは kb-harness-core を使う知識ベース（KB）である。ハーネスの契約の正本は `apm_modules/lostandfound/kb-harness-core/docs/` にある。KB 固有の規約は、このリポジトリの `AGENTS.md` と `kb-domain.yml` が正本である。

- KB の内容を問われたら、`ask-kb` スキルの手順で、KB の記述だけを根拠に、出典と確度を示して答える。
- エンティティの追加は `add-entity`、出典の審査は `review-evidence`、RAG 評価は `test-rag`、KB の拡張は `expand-kb` スキルに従う。スキルを呼ぶ機能が無いランタイムでは、`apm_modules/lostandfound/kb-harness-core/.apm/skills/<名前>/SKILL.md` を読んで従う。
- 生成物（`index.md` の生成区間・`graph.json`・ビューと懸念の一覧）は手で編集せず、`kb sync` で生成する。
- コミットの前に `kb validate` と `kb sync --check` を通す。
