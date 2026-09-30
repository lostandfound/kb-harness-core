# 考察メモ: ハーネスを特定のエージェントランタイムに依存させない

2026-09-30 のディスカッションの記録。`ask-kb` スキルを足した際、「Claude 以外（Codex・Cursor など）でも使う。汎用性は考慮されているか」と問われた。さらに、「対象となるランタイムは『すべて』であり、具体的なランタイムが記述されたのは場当たり的な作業の結果である」と示された。

結論は「**配布資産と対外契約はランタイム名・ツール名・配置先パスを持たない。対応ランタイムの一覧は作らない。これを AGENTS.md の指針、テストによる機械検査、audit-harness の意味の監査の 3 層で守る。ランタイムの仕組みに合わせる部品（アダプタ）は、隔離の印をつけた場所にだけ置き、無くても全機能が成り立つようにする**」。

## 観察された問題

v0.11.1 以降の `main`（a3d7565）で、`.apm/`・README・AGENTS.md・`docs/*.md`・`scripts/`・`src/` を、既知のランタイム名・ツール名・配置先パスで検索した。

| 分類 | 件数 | 箇所 |
|---|---|---|
| スキル・エージェントの本文に特定ランタイムのツール名 | 7 行 / 5 ファイル | `WebFetch`・`WebSearch`（add-entity・find-book・find-paper・ndl-digicolle・evidence-reviewer） |
| エージェント定義の frontmatter に特定ランタイムの値 | 2 ファイル | `tools: Read, Grep, …`（特定ランタイムのツール名）、`model: sonnet`（特定ベンダーのモデル名） |
| 配置先ディレクトリの列挙 | 3 ファイル | audit-harness（`.codex/`・`.claude/`・`.agents/skills/`）、AGENTS.md・README・integration.md（`--target claude`・`.claude/`） |
| 特定ランタイム名 | 4 ファイル | README「Claude Code 等」×2、integration.md（ランタイム名の列挙、「Claude は `.md`、Codex は `.toml`」）、review-doc（`CLAUDE.md`） |
| 特定ランタイムの hooks | 3 ファイル | integration.md の hooks の節（`.claude/settings.json` の JSON 例）、`scripts/verify_turn.sh` とその scripts.md の節 |
| ランタイムの挙動についての注記 | 2 ファイル | evidence-reviewer・`scripts/wiki_fetch.py`（「WebFetch は要約を挟む」） |

どれも、その時点で使っていたランタイムに合わせて書いた結果である。規則が無いので、足すたびに増える。`ask-kb` の直後にも、rag-tester が `.claude/skills/` を読む形で書かれ、指摘を受けて直した。

frontmatter の `tools` の制限は、もともと実効性が弱い。rag-tester も evidence-reviewer もシェルを持つので、書き込みを禁じたことにはならない。さらに、`tools` をそのまま写さない配置先もある（導入ガイドにある Codex の警告）。

## 対応の選択肢

**対象の定め方**

- (a) 対応ランタイムを列挙し、それぞれに合わせて書く。列挙に無いランタイムが最初から外れ、列挙の保守も要る。
- (b) 対象は「すべて」とし、列挙しない。資産は、どのランタイムにもある能力（ファイルを読む、文字列検索、シェルで実行、Web ページを取得、Web 検索、利用者に確認する）だけで書く。

**ランタイムの仕組みに合わせる部品（hooks など）**

- (c) すべて撤去する。`verify_turn.sh` を使っている導入先が壊れる。
- (d) アダプタとして残す。ただし隔離の印をつけた場所にだけ置き、無くても全機能が成り立つようにする。検証の本体は `kb validate`・`kb sync --check` と git の pre-commit が持ち、これらはランタイムに依存しない。
- (e) 撤去しないが、文書から外す。存在が分からない部品は保守されない。

**frontmatter の `tools` / `model`**

- (f) 残す。特定ランタイムの語彙がそのまま配布される。
- (g) 外し、制約は本文に書く（「ファイルを書き換えない」など）。

**守り方**

- (h) AGENTS.md の指針だけ。今回の経緯のとおり、書き手が思い出さなければ守られない。
- (i) 指針に加え、テストで既知の語を検出する。語の一覧は検出のための手がかりであり、対応ランタイムの一覧ではない。例外はテスト内に理由つきで列挙するか、文書中の隔離の印で囲む。
- (j) さらに audit-harness の観点に加える。「サブエージェントで並列に回す」のような、語ではなく手順の前提としての依存は、テストでは捉えられない。
- (k) CI で `apm install --target` を配置先ごとに実行し、配置の結果を確かめる。

## 判断

- **採る: (b)。** 対応ランタイムの一覧は作らない。
- **採る: (d)。** 隔離の印は、Markdown では `<!-- runtime-adapter -->` と `<!-- /runtime-adapter -->` で囲んだ区間とし、ファイル全体がアダプタのもの（`scripts/verify_turn.sh`）はテスト内の一覧に理由つきで載せる。アダプタは任意の部品であり、どの手順もこれを前提にしない。
- **採る: (g)。** 実効性の弱い制限のために、特定ランタイムの語彙を配布しない。
- **採る: (h)(i)(j)。** 検査の範囲は `.apm/`・README・AGENTS.md・`docs/*.md`・`scripts/`・`src/kb_harness/`。CHANGELOG・`docs/notes/`・`BACKLOG.md` は過去の記録なので対象外とする。`tests/` もアダプタのテストを含むので対象外とする。
- **見送る: (a)。** 再開条件は、ランタイムごとに書き分けないと成り立たない手順が現れたとき。その場合もまずアダプタとして隔離できないかを考える。
- **見送る: (c)(e)。** (c) の再開条件は、アダプタの保守が本体の変更を妨げるようになったとき。
- **見送る: (k)。** この環境にも CI にも `apm` が無い。再開条件は、配置の違いが原因の不具合が導入先で起きたとき。

## 実装の記録

- **指針**: AGENTS.md に「ランタイム非依存」の節を足した。「資産の正本とデプロイ」の節の `--target claude`・`.claude/`・「`*.md` に正規化」も一般的な書き方に改めた。
- **機械検査**: `tests/test_runtime_neutrality.py` を足した。次の 4 つを検査する。(1) 範囲内のファイルに既知の語が無いこと（アダプタ区間と `FILE_EXCEPTIONS` を除く）。(2) アダプタの印の対応がとれていること。(3) 例外一覧が実在するファイルを指すこと。(4) `.apm/` の frontmatter が `name` / `description` だけであること。変更前の状態に対して実行すると失敗し、変更後は通ることを確かめた。
- **意味の監査**: audit-harness の観点を 7 から 8 に増やし、「ランタイム非依存」（手順の前提としての依存）を足した。
- **既存資産の修正**: 観察の節の違反をすべて直した。Web 取得・Web 検索は能力で書いた。audit-harness の配置先の列挙は「導入先 `apm.yml` の `targets` による配置先」にした。review-doc の `CLAUDE.md` は「ランタイム固有の同等ファイル」にした。README の「Claude Code 等」は外した。`wiki_fetch.py` の docstring も直した。
- **エージェントの frontmatter**: evidence-reviewer・rag-tester から `tools` / `model` を外した。本文に書き換えの制約を足した（evidence-reviewer は KB のファイルを書き換えない、rag-tester は `evals/rag-eval.yml` だけ）。
- **hooks**: 導入ガイドの特定ランタイムの hooks の JSON 例を外し、「フックを持つランタイムでは `kb validate` / `kb sync --check` を登録する。形式は各ランタイムの文書に従う」とした。`verify_turn.sh` の記述（導入ガイドの節 6 の末尾と scripts.md の節）はアダプタの印で囲み、スクリプト本体は `FILE_EXCEPTIONS` に載せた。
- **当初の判断から変えた点**: 大文字小文字を区別しない検出では、ツール名の `Grep` / `Glob` が普通名詞の grep / glob（コマンドやパターン）と衝突するので、この 2 語だけ大文字始まりに限った。
- **範囲外として残したもの**: このリポジトリのルートの `CLAUDE.md`（`AGENTS.md` への symlink）。開発者の手元の便宜で、配布資産でも対外契約でもない。`tests/` のアダプタのテスト（`test_verify_turn.py`）。

## 未決事項

- **アダプタをパッケージに置き続けるか。** `verify_turn.sh` は特定ランタイムのフックの入出力（ペイロードの `stop_hook_active`、終了コード 2 の意味）に依存する。他のランタイム向けのアダプタを求められたときに、パッケージに足すのか、導入先に委ねるのかを決める。
- **既知の語の一覧の保守。** 新しいランタイムやツール名が現れても、一覧は自動では増えない。audit-harness の観点 8 で見つけたら一覧に足す運用にしているが、足す契機がこれで十分かは運用して確かめる。
- **エージェントをスキルにするか。** evidence-reviewer と rag-tester はエージェントとして配っているが、APM は gemini・antigravity・windsurf・hermes にエージェントを届けない。omnibus-kb の `targets` にある antigravity にも届いていない（実際、`.agents/` にはスキルしか無い）。スキルにすれば全ランタイムに届く。ただし、別のコンテキストで独立に審査するという利点は、サブエージェントを持つランタイムでしか得られない。スキルを正本にし、エージェントはそれを読む薄い入口にする案が有力である。
- **導入先への指示を instructions プリミティブで配るか。** `ask-kb` を指す 1 行は、いまは導入先に `AGENTS.md` へ書いてもらう。`.apm/instructions/` に置けば、APM が各ランタイムの規則ファイルか `AGENTS.md` に届ける。ただし codex・gemini・opencode・hermes では導入先が `apm compile` を実行する必要がある。また、導入先の `AGENTS.md` が生成物に変わることの影響もある。
- **frontmatter を外したことの影響。** ランタイムによっては、エージェントが既定のツールとモデルで動くようになった。書き込みの制限は本文の指示に頼る。導入先で本文の指示が破られる事例が出たら、ランタイムに依存しない制限の書き方（APM 側の仕組みなど）を探す。

## 再考（同日）: APM の仕様

APM 0.32.0（microsoft/apm、2026-09-25 リリース、73d6d0e 時点の `main`）の文書とソースを読み、判断を確かめた。正本は同リポジトリの `docs/src/content/docs/concepts/primitives-and-targets.md` と `reference/targets-matrix.md` である。

**対象ランタイム。** `targets:` と `--target` が受ける値は `copilot`・`claude`・`grok-build`・`cursor`・`opencode`・`codex`・`gemini`・`antigravity`・`windsurf`・`kiro`・`agent-skills`・`hermes` の 12 種である。このほか、`intellij` は Copilot の設定を経由して配置する。`copilot-cowork`・`copilot-app`・`grok-cloud`・`openclaw` は実験的な機能として有効にしたときだけ使える。`agent-skills`・`antigravity`・`hermes` は明示したときだけ対象になり、自動検出にも `all` にも含まれない。ランタイムは今後も増えるので、(b) の「一覧を作らない」は妥当である。

**プリミティブごとの届く範囲。**

| プリミティブ | 届かないランタイム | 備考 |
|---|---|---|
| skills | なし（全ランタイム） | 形式は agent-skills 標準の `SKILL.md`。多くのランタイムは共通の `.agents/skills/` に置かれ、claude・grok-build・kiro だけが固有のディレクトリに置かれる |
| agents | gemini・antigravity・windsurf・hermes（と agent-skills） | windsurf 向けには、エージェントをスキルとして書くよう APM 自身が案内している |
| instructions | 全ランタイム。ただし codex・gemini・opencode・hermes は `apm compile` で `AGENTS.md` / `GEMINI.md` にまとめて届く | frontmatter は `description` と `applyTo` |
| hooks | grok-build・opencode・hermes | APM は「移植可能のふりをしない」プリミティブと位置づける。イベント名は写す（`Stop` → copilot では `agentStop`、gemini では `SessionEnd`）が、ペイロードと終了コードの意味は写さない |

**エージェントの frontmatter。** `model` と `tools` をそのまま受けるのは copilot・claude・grok-build・cursor・opencode だけである。codex は `name`・`description`・本文だけを写し、`tools` があると警告する。kiro は `tools` を権限として扱い、許された値（`read`・`write`・`shell`・`web` など）以外があると配置しない。opencode は `tools` をツール名から真偽値への対応表として要求する。以前の `tools: Read, Grep, Glob, Bash` は、kiro では配置が止まり、opencode では形式が合わない。frontmatter を外した (g) の判断は仕様からも支持される。

**スキルの形式（agent-skills 標準）。** `name` は英小文字・数字・ハイフンの 1〜64 字で、ディレクトリ名と一致させる。`description` は 1024 字以内、本文は 500 行・5000 トークン以内が目安である。ハーネスのスキル 11 件はいずれも満たす（最大で 89 行、description 150 字）。スキルのフォルダは丸ごと複製されるので、`scripts/` や `references/` を同梱できる。

**リンクの書き換え。** スキルからパッケージ内の他のファイルへの相対リンクは、`apm install` のときに `apm_modules/<owner>/<repo>/...` を指すよう書き換えられる。コードとして書いたパス（`python3 apm_modules/lostandfound/kb-harness-core/scripts/...`）は書き換えられないが、配置先に依存しない点では同じである。

**アダプタ。** `verify_turn.sh` は、特定ランタイムの Stop フックのペイロード（`stop_hook_active`）と終了コード 2 の意味に依存する。APM の hooks プリミティブで配っても、イベント名が写るだけで意味は写らない。(d) の「任意のアダプタとして隔離する」を維持する。

**このリポジトリの `CLAUDE.md`。** APM の自動検出は、ルートに `CLAUDE.md` があるだけで claude を対象にする。このリポジトリは導入先ではないので実害は無いが、導入先の雛形として持ち込まないよう注意する。

**判断への追加。**

- テストの検出語に、APM の対象一覧のランタイム名と配置先（kiro・opencode・grok・hermes・openclaw、`.grok/`・`.kiro/`・`.opencode/`・`.windsurf/`）を足した。
- 下の未決事項に 2 件を足した。

## 参照

- [問い合わせへの答え方のメモ](kaitou-tejun-memo.md)（`ask-kb` とこの論点のきっかけ）
- [導入ガイド](../integration.md) の節 3（配置）と節 6（hooks）
