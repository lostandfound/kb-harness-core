# 導入ガイド

新しい KB リポジトリにこのハーネスを組み込む手順。

## 前提

- Python 3.10 以上
- [`apm`](https://github.com/microsoft/apm) CLI（0.32 以上で動作確認）

## 1. `kb-domain.yml` を書く

リポジトリルートにドメイン定義を置く。フィールドは [設定リファレンス](configuration.md#kb-domainyml) を参照。

## 2. `vocabulary.yml` と `references.yml` を書く

`<content_root>/` 配下に語彙と文献レジストリを置く。契約は [設定リファレンス](configuration.md) を参照。

## 3. `apm.yml` に依存を追加してデプロイする

```yaml
dependencies:
  apm:
    - lostandfound/kb-harness-core          # GitHub。#tag または完全な #sha で固定を推奨
    # - ../kb-harness-core                  # ローカルパス（モノレポ内・開発中）
```

依存は文字列形式で書く。`github:` キーを持つオブジェクト形式は apm が受理しない。

apm 0.32 以降は短縮 SHA での固定を受理しない。SHA で固定するときは 40 桁で書く。

```bash
apm install --target <ランタイム>
```

`apm install` はパッケージを `apm_modules/lostandfound/kb-harness-core/` に展開し、`.apm/` の資産を、指定したランタイムの配置先ディレクトリへ配置する。`--target` に渡せる名前と配置先は apm の文書に従う。複数のランタイムを使うなら `apm.yml` の `targets:` にすべて並べる。配置先ランタイムは `--target` か `targets:` で必ず指定する。どちらも無いと `apm install` はエラーで止まる。

このパッケージが配る資産は 3 種類で、ランタイムごとに届く範囲が違う（正本は apm の文書の「Primitives and Targets」）。

| 資産 | 置き場所 | 届く範囲 |
|---|---|---|
| スキル | `.apm/skills/` | すべてのランタイム。手順の正本はすべてスキルにある |
| エージェント | `.apm/agents/` | エージェントの仕組みを持つランタイムだけ。`evidence-reviewer` と `rag-tester` は、それぞれ `review-evidence` / `test-rag` スキルを読んで従うだけの入口なので、届かないランタイムでもスキルとして同じ手順を使える |
| 常時の指示 | `.apm/instructions/kb-harness.instructions.md` | 多くのランタイムでは、`apm install` がそのランタイムの規則ファイルとして配置する。ランタイムによっては `apm install` では配置されず、`apm compile` で `AGENTS.md` にまとめて届く（下記） |

資産はどのランタイムにもある能力だけで書いてあり、frontmatter は apm がどのランタイムにも写せるキーだけである。ツールの制限は本文に書いてある。

### 常時の指示を `AGENTS.md` に入れる

常時の指示は、KB への問い合わせには `ask-kb` に従うこと、主要なスキル、コミット前の検証を案内する。`apm install` が規則ファイルを配置しないランタイムでは、`apm compile --target <ランタイム>` で `AGENTS.md` に入れる。どのランタイムが該当するかは、`apm install` の出力に規則（rule / instruction）の配置が出るかで分かる。

手書きの `AGENTS.md` があると、`apm compile` はそれを上書きせず、警告を出して指示も入れない。手書きの内容を保ったまま指示を入れるには、apm の managed-section モードを使う。`AGENTS.md` に次の 2 行を置き、導入先の `apm.yml` に設定を足す。印の外側は `apm compile` のたびにそのまま保たれ、印の内側だけが生成される。

```markdown
<!-- apm:start -->
<!-- apm:end -->
```

```yaml
compilation:
  agents_md:
    mode: managed_section
```

`apm compile` を使わない場合は、`AGENTS.md` に次の 1 行を手で書けば、問い合わせへの答え方だけは同じにできる。

```markdown
- KB の内容を問われたら、`apm_modules/lostandfound/kb-harness-core/.apm/skills/ask-kb/SKILL.md` の手順で、KB の記述だけを根拠に答える。
```

## 4. `kb` CLI をインストールする

```bash
python3 -m pip install apm_modules/lostandfound/kb-harness-core              # Claim を使わない KB
python3 -m pip install "apm_modules/lostandfound/kb-harness-core[claims]"    # Claim を使う KB
kb doctor
```

`kb-ontology-core` は `claims` extra でだけ入る。Claim 型を `vocabulary.yml` に定義しない KB には要らず、無ければ `kb doctor` が `doctor.ontology.not_installed` の WARNING で知らせる。Claim を扱おうとした時点で `ontology.core.missing` の診断になる。`pyproject.toml` は `kb-ontology-core` を `git+https://` で参照するため、ssh 鍵は不要。

## 5. 補助スクリプトの呼び出し

検証・生成・評価は `kb` CLI を正本として使う。`scripts/` 配下の補助ツール（`ndl_search.py` / `cinii_search.py` / `wiki_fetch.py` / `browse.py` など）は APM のデプロイ対象に含まれないので、モジュール配下のパスで直接実行する。

```bash
python3 apm_modules/lostandfound/kb-harness-core/scripts/ndl_search.py "<検索語>" --count 5
```

導入先ルートの `scripts/` をモジュールへの symlink にはしない。symlink だと導入先固有のスクリプトを `scripts/` に置けず（`git add` が symlink 越しのパスを拒む）、配下を編集すると git 管理外の外部モジュールを汚すためである。導入先固有のスクリプトは導入先自身の `scripts/` に置いてよい。

## 6. hooks を設定する（任意）

### エージェントのフック

ファイルの編集後やターンの終了時にコマンドを実行できるランタイムでは、そこに `kb validate`（と `kb sync --check`）を登録すると、壊れた状態のまま作業が終わるのを防げる。登録の形式は各ランタイムの文書に従う。このパッケージはフックの設定を同梱しない（検証の自動実行を強制しないため）。フックが無くても、下の git pre-commit が同じ検証を閉じる。

### git pre-commit

```bash
bash apm_modules/lostandfound/kb-harness-core/scripts/install-hooks.sh
```

ステージに `.md` / `.yml` / `.py` が含まれるとき `kb validate` → `kb sync --check` → テスト（`tests/` がある場合）→ `kb eval smoke`（`evals/rag-eval.yml` がある場合）→ `.kb/hooks/pre-commit.d/*`（ある場合）を順に実行する。`kb validate` はエンティティ内容を、`kb sync --check` は index / graph / views の陳腐化を見る（[CLI リファレンス](cli.md#kb-sync--kb-sync---check)）。前者が通っても後者は独立に落ちうるので両方を通す。テンプレートは `kb` CLI だけを呼び、導入先の `scripts/` には依存しない。導入先固有のチェックは `kb-domain.yml` の `validate.extra_checks` か `.kb/hooks/pre-commit.d/` に置き、テンプレート自体は編集しない。

### 出典の消失を検出する（任意）

複数の出典を並存させる KB では、既存エンティティの改版で先行出典の記述が丸ごと消える事故が起きる。形式は壊れないため `kb validate` では検出できない。`.kb/hooks/pre-commit.d/20-source-attrition` を置いて pre-commit で止める。

```bash
#!/bin/bash
set -euo pipefail
python3 apm_modules/lostandfound/kb-harness-core/scripts/check_source_attrition.py
```

判定の基準と逃げ道は [スクリプト一覧](scripts.md#check_source_attritionpy) を参照。

### ターンの終了を検証で閉じる（任意）

<!-- runtime-adapter -->
特定のランタイムのフック形式に合わせた任意のアダプタである。pre-commit が閉じるのはコミットするときだけなので、コミットせずに終わるターンでは検証が走らない。`.claude/settings.json` の Stop hook に `scripts/verify_turn.sh` を登録すると、ターンの終了時に `kb validate` と `kb sync --check` を実行し、失敗したらその場で Claude に直させる。設定例は [スクリプト一覧](scripts.md#verify_turnsh) を参照。
<!-- /runtime-adapter -->

## 7. 版を上げるとき

`apm.yml` の固定コミットを新しいタグへ変え、`apm install` で lock と配布物を再生成してから `kb validate` と `kb sync --check` を通す。その前に CHANGELOG の **Changed** を読む。`kb validate` は通るのに新規作成の挙動だけが変わる項目（型の既定の章立てなど）は、検証では見つからない。

## 8. 運用ファイルを置く（任意）

導入先の運用ファイルは二つあり、役割が違う。どちらも任意で、無くても `kb validate` は失敗しない。

- **懸念台帳（`concerns/`）**: KB の知識の確からしさの台帳。出典どうしの食い違い、出典の弱さ、孫引き、出典の取得不能、値や系統を選んだ判断の根拠を、対象のエンティティか出典に結びつけて 1 件 1 YAML で置く。行が表すのは「やること」ではなく知識の状態で、決着しない（両論併記で記述側は完了）ことも正常な終わり方である。本文と同じコミットで更新する。
- **BACKLOG（`docs/BACKLOG.md`）**: KB を作る作業の予定と記録。未着手の行が予定、`[x]` の行が経緯つきの作業ログになる。収録タスク、RAG 評価の欠落、探索候補、運用タスク（ハーネスの版上げなど）を置く。

二つは参照し合うが、行を移し合わない。懸念が作業を生んだら、BACKLOG の行は出所に懸念 ID を書くだけにし、懸念は作業の結果に応じて状態を改める。どちらにも入らないもの（ハーネス自身の問題）はハーネスへ報告する。型やエンティティ境界の判断は `review-entity-model` の出力であり、懸念台帳には入らない。

### 懸念台帳を有効にする

`kb-domain.yml` に `concerns.root` を書き、そのディレクトリを作る。フィールドと検査の契約は [設定リファレンス](configuration.md#懸念台帳任意) が正本である。

```yaml
concerns:
  root: concerns
```

懸念は YAML を手で書き、`kb validate` で検査し、`kb sync` で一覧（既定 `concerns/index.md`）を生成する。着手できる懸念は `kb concern list --actionable`、あるエンティティの懸念は `kb concern list --for <entity>` で引く。`scripts/concerns_summary.py` は `concerns.root` があれば同じ台帳を集計する。

### 旧来の `docs/CONCERNS.md` から移す

これまでの雛形は、Markdown の 1 行 1 懸念（`- [ ] <対象>: <内容> status: <状態>`）だった。この形式は対象の実在も種別も検査されず、作業や違和感も入り込んだため、構造化した台帳に置き換えた。`concerns.root` を設定した KB に `docs/CONCERNS.md` が残っていると `kb validate` が `concern.legacy_ledger` の WARNING を出す。

各行を次のように移し、移し終えたら `docs/CONCERNS.md` を消す。旧形式は種別を持たず対象欄の解釈も要るので、移行コマンドは用意していない。

- 対象欄の slug を `/dir/file.md` に、`references.yml` の行は本文中の出典 ID を `ref: <id>` にして `targets` に並べる。「〜ほか 5 件」のような書き方は列挙し直す。
- 内容から `kind` を選ぶ。どれにも当たらない行（作業の予定、型・境界の判断、ハーネスの問題）は懸念ではないので、BACKLOG か `review-entity-model` の出力、またはハーネスへの報告へ回す。
- `status` はそのまま使える。`[x]` の行は `resolved` にし、対応を `resolution` に書く。`blocked-source` は `awaiting`、`suspended` は `resume_when`、`settled-hedged` は `resolution` を書く。

### `docs/BACKLOG.md` の雛形

行形式は導入先が定めてよいが、対象・型・一行説明・relations 案・根拠・完了時のコミットを 1 行に収めると、`expand-kb` が候補選定と完了記録を機械的に行える。探索候補セクションの書式コメントは `explore-kb` が追記時に参照する。滞留上限（探索候補が何件を超えたら新規探索を止めるか）と棚卸周期は導入先の拡張方針文書で決め、ここから参照する。

````markdown
# 拡張バックログ

KB を作る作業の予定と記録。上から優先。着手中という中間状態は書かず、実装と検証が完了した後に `[x]` へ変更し、経緯とコミットを付記する。
出典や内容の懸念はここではなく懸念台帳（`concerns/`）に置く。懸念から生まれた作業は、出所に懸念 ID を書く。

形式: `- [ ] <slug> (<type>): <一行説明>。relations 案: <述語 → パス>。根拠: <言及済み未収録 / RAG 欠落 / カテゴリバランス / 懸念 <id> など>（コミット: <hash>）`

## 収録タスク

## RAG 評価の欠落

`kb eval` の未解決欠落は次で行形式に出力して貼る。

```bash
python3 apm_modules/lostandfound/kb-harness-core/scripts/eval_summary.py --open
```

## 探索候補（explore-kb 供給、未考証）

<!-- 書式: - [ ] <名称>: <一行説明>。出所: <探索経路 + URL> -->
<!-- 滞留上限: N 件。超えたら新規探索を止め、考証・却下で減らす -->

## 保留（除外基準該当）

却下した候補と理由。同じ候補が再浮上したときの参照先。
````

## 運用上の注意

- **正本は `.apm/`。** スキル・エージェントを修正するときはパッケージ側の `.apm/` を編集し、`apm install` で再デプロイする。ランタイムの配置先にある同名ファイルは生成物であり直接編集しない。
- `apm audit` で、正本と展開先のドリフト（未反映の差分）を検査できる。
- エージェント定義は `.apm/agents/` では `*.agent.md` だが、デプロイ後は対象ランタイムの形式になる。
- scripts の正本はパッケージの `scripts/`。導入先からは `apm_modules/lostandfound/kb-harness-core/scripts/<name>.py` で直接呼び、導入先ルートに symlink を張らない。導入先ルートの `scripts/` は導入先固有のスクリプト置き場として使える。
- `kb doctor` は `pyproject.toml` が宣言する `kb-ontology-core` のタグとインストール済みバージョンの不一致を報告する。依存を更新したら再インストールする。
