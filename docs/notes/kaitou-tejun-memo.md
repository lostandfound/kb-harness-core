# 考察メモ: KB への問い合わせに答える手順をスキルにするか

2026-09-30 のディスカッションの記録。問いは「KB に問い合わせたときの答え方（RAG）をスキルにするべきか」。

結論は「**スキル（`ask-kb`）にする。中身は検索の実装ではなく、KB を根拠に答えるときの手順（探す順序・根拠の示し方・確度の扱い・KB の外の知識との分離・欠落の記録）に絞る。rag-tester は答え方をこのスキルに委ね、判定と記録だけを持つ**」。

## 観察された問題

- **答え方の手順がどこにも無い。** KB の評価の主軸は「RAG での回答精度」（`rag-tester` エージェント）だが、答え方の手順は rag-tester の作業手順 3 に、テストの一部として 1 行あるだけである。導入先 omnibus-kb の AGENTS.md・README にも、問い合わせへの答え方の記述は無い。利用者がセッションで KB に質問すると、エージェントは探し方をその場で決め、学習知識で穴を埋める、出典を示さない、懸念台帳を見ない、という答え方になりうる。
- **字面の検索だけでは relations の先にある答えに届かない。** [RAG の自己改善のメモ](rag-jiko-kaizen-memo.md)の測定では、字面検索で根拠が上位 5 件に入ったのは「作り手」の問いで 8/15、「所属」の問いで 23/33 だった。kb-retrieval-core の `--expand-graph` でも 7/15、25/33 である。答えるエージェントが graph.json と frontmatter の relations を辿れば届く種類の失敗である。
- **確度を下げるべき記述が少なくない。** omnibus-kb（8b64001、エンティティ 268 件）では、懸念が 43 件あり、対象のエンティティは 43 件である。確度 C / D の relation は 28 ファイルに計 30 本ある。graph.json の `edges` は `confidence` を持たないので、graph.json だけを読んで答えると確度 C の関係を断定してしまう。
- **テストと本番の答え方が別になる。** rag-tester が固有の手順で答える限り、rag-tester の判定は「実際に答えるときの手順」の品質を測っていない。

## 対応の選択肢

- (a) スキルにしない。導入先の AGENTS.md に数行の方針を書いてもらう。導入先ごとに書き方がばらつき、ハーネスの語彙（懸念台帳・`kb reference show --for`・ビュー・relations の確度）に追従しない。
- (b) ハーネスのスキル（`ask-kb`）にする。導入先は `apm install` で受け取る。
- (c) エージェントにする。答えるたびに別コンテキストのサブエージェントを起こすのは重く、会話の文脈（前の問い、利用者の関心）が失われる。問い合わせは会話の中で繰り返されるので、メインのセッションで使う手順のほうが向く。
- (d) 回答生成の CLI（`kb ask`）をハーネス本体に足す。ハーネスは LLM を呼ばない決定的な本体であり（RAG の自己改善のメモの (l) を見送った理由と同じ）、回答生成は利用側の責務である。
- (e) rag-tester との関係: (e1) 手順をスキルと rag-tester の両方に書く。(e2) 答え方をスキルに寄せ、rag-tester はスキルに従って答えたうえで判定・`history` の追記・新規クエリの作成だけを持つ。

## 判断

- **採る: (b) と (e2)。** 答え方はスキル `ask-kb` が正本で、rag-tester はそれを読んで同じ手順で答える。二重に持たないので、どちらかが古くなることがない。
- スキルの範囲は「読んで答える」に限る。エンティティ・出典・懸念・評価セットは書き換えない。答えられなかった問いの記録は、利用者が同意した場合に限り、導入先の `docs/BACKLOG.md` の「RAG 評価の欠落」か `evals/rag-eval.yml` へ候補として示す。固定セットへの追加は人が選ぶ（RAG の自己改善のメモの (f)）ので、スキルは直接追記しない。
- 検索器は固定しない。kb-retrieval-core が入っていれば使ってよいと書くが、無くても grep と graph.json で完結する手順にする。検索・重みづけ・評価は kb-retrieval-core の責務であり、スキルがその代わりをするわけではない。
- **見送る: (a)。** 再開条件は、導入先ごとに答え方の要求が大きく異なり、共通の手順が足かせになったとき。
- **見送る: (c)。** 再開条件は、答えるための探索が大きくなり、メインの文脈を圧迫することが運用で問題になったとき。
- **見送る: (d)。** 再開条件は、ハーネス本体が LLM を呼ぶ機能を持つと別途決めたとき。

## 実装の記録

- `.apm/skills/ask-kb/SKILL.md` を足した。探す順序は title・aliases → description・tags・一覧 → 本文 → `graph.json` の relations（1〜2 段、逆向きを含む）→ ビュー → 導入先の検索器（任意）。読むものは本文と frontmatter、`kb reference show --for`、`kb concern list --for`（エンティティと出典の両方）、`kb claim list`。答えは「答え・根拠・確度と注意・KB に無いこと・KB の外の知識（任意）」の順にする。欠落は `evals/rag-eval.yml` の `gap` と同じ語彙で示す。
- 当初の判断から変えた点: relations の確度は `graph.json` の `edges` に載らないので、答えに使う関係は始点の frontmatter で確度を確かめる手順にした。`graph.json` が古い場合も生成し直さず（スキルは読むだけ）、frontmatter の `relations` を正とする。rag-tester がこれまで実行していた `export_graph.py --force` もこの手順に置き換えた。
- rag-tester は、制約の節で `ask-kb` の `SKILL.md` を読むように改め、作業手順 3 をスキルの手順で答えることに置き換えた。どの経路で根拠に届いたかを記録させ、`gap: retrieval` の判定材料にした。KB の外の知識の補足は rag-tester では使わない。
- omnibus-kb（8b64001）で、スキルが使うコマンド（`kb sync --check`、`kb reference show --for`、`kb concern list --for` のエンティティと `ref:`、`kb view list` / `resolve`、`kb claim list`）がすべて期待どおりに動くことを確かめた。

## 未決事項

- **導入先の AGENTS.md から `ask-kb` を指すか。** スキルは description で呼ばれるが、導入先が「KB への質問にはこのスキルを使う」と明記するほうが確実である。ハーネスの `docs/integration.md` で推奨するかを、omnibus-kb で使ってみてから決める。
- **rag-tester がスキルを読むパス。** エージェントは Skill ツールを持たないので、展開先のパス（Claude Code なら `.claude/skills/ask-kb/SKILL.md`）を直接読ませている。`--target` を複数持つ導入先が現れたら、パスの書き方を見直す。
- **kb-retrieval-core の使い方をスキルに書くか。** 今は「入っていれば候補に加える」とだけ書いた。導入先に kb-retrieval-core が入り、呼び出し方が安定したら、コマンド例を足すかを決める。

## 参照

- [RAG の自己改善のメモ](rag-jiko-kaizen-memo.md)（検索の測定、kb-retrieval-core との分担）
- `.apm/agents/rag-tester.agent.md`
- [設定リファレンス](../configuration.md) の懸念台帳・ビュー・`evals/rag-eval.yml` の節
