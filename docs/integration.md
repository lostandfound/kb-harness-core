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
apm install --target claude
```

`apm install` はパッケージを `apm_modules/lostandfound/kb-harness-core/` に展開し、`.apm/skills/` `.apm/agents/` を `.claude/skills/` `.claude/agents/` へ配置する。`--target codex` など他ランタイムも選べる。

配置先ランタイムは `--target` か導入先 `apm.yml` の `targets:` で必ず指定する。どちらも無いと `apm install` はエラーで止まる。`--target codex` では、エージェント定義の `tools` が Codex 側に写らず落ちる旨の警告が出る。Codex でエージェントのツールを絞りたい場合は、生成された `.codex/agents/*.toml` を使わない。

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

### Claude Code の hooks

apm は `.apm/hooks/*.json` を `.claude/settings.json` にマージする機能を持つが、このパッケージは hooks を同梱していない（検証の自動実行を強制しないため）。必要なら導入先の `.claude/settings.json` に書く。`.md` 編集後に `kb validate` を実行する例:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "f=$(jq -r '.tool_input.file_path // empty'); case \"$f\" in *.md) kb validate >&2 || exit 2;; esac",
            "timeout": 60,
            "statusMessage": "kb validate 実行中..."
          }
        ]
      }
    ]
  }
}
```

### git pre-commit

```bash
bash apm_modules/lostandfound/kb-harness-core/scripts/install-hooks.sh
```

ステージに `.md` / `.yml` / `.py` が含まれるとき `kb validate` → テスト（`tests/` がある場合）→ `kb eval smoke`（`evals/rag-eval.yml` がある場合）→ `.kb/hooks/pre-commit.d/*`（ある場合）を順に実行する。テンプレートは `kb` CLI だけを呼び、導入先の `scripts/` には依存しない。導入先固有のチェックは `kb-domain.yml` の `validate.extra_checks` か `.kb/hooks/pre-commit.d/` に置き、テンプレート自体は編集しない。

### 出典の消失を検出する（任意）

複数の出典を並存させる KB では、既存エンティティの改版で先行出典の記述が丸ごと消える事故が起きる。形式は壊れないため `kb validate` では検出できない。`.kb/hooks/pre-commit.d/20-source-attrition` を置いて pre-commit で止める。

```bash
#!/bin/bash
set -euo pipefail
python3 apm_modules/lostandfound/kb-harness-core/scripts/check_source_attrition.py
```

判定の基準と逃げ道は [スクリプト一覧](scripts.md#check_source_attritionpy) を参照。

### ターンの終了を検証で閉じる（任意）

pre-commit が閉じるのはコミットするときだけなので、コミットせずに終わるターンでは検証が走らない。`.claude/settings.json` の Stop hook に `scripts/verify_turn.sh` を登録すると、ターンの終了時に `kb validate` と `kb sync --check` を実行し、失敗したらその場で Claude に直させる。設定例は [スクリプト一覧](scripts.md#verify_turnsh) を参照。

## 7. 版を上げるとき

`apm.yml` の固定コミットを新しいタグへ変え、`apm install` で lock と配布物を再生成してから `kb validate` と `kb sync --check` を通す。その前に CHANGELOG の **Changed** を読む。`kb validate` は通るのに新規作成の挙動だけが変わる項目（型の既定の章立てなど）は、検証では見つからない。

## 8. 運用ファイルを置く（任意）

`docs/CONCERNS.md`（懸念台帳）と `docs/BACKLOG.md`（拡張バックログ）は、README の推奨構成に載せている任意の運用ファイルである。ハーネスはこれらを自動生成しない。`explore-kb` `expand-kb` スキルは既存ファイルにだけ追記し、依頼がなければ新設しないため、使う場合は導入時に手で置く。存在しなくても `kb validate` は失敗しない。

両ファイルの役割分担は次のとおり。

- **CONCERNS.md**: 未整理の懸念や違和感の受信箱。出典間の食い違い、根拠不足で本文に書けない事項を 1 行ずつ置く。`scripts/concerns_summary.py` が状態別に集計する。
- **BACKLOG.md**: 実施すると判断した将来作業の正本。CONCERNS からの移動、RAG 評価の欠落、探索候補を受け、実装と検証が完了したら `[x]` にする。

### `docs/CONCERNS.md` の雛形

`concerns_summary.py` はチェックボックス行（`- [ ]` / `- [x]`）を懸念として拾い、行末の `status: <状態>` で分類する。`status` を省いた行は未分類として着手可能側に現れる。書式の例を本文中に書くときは、行頭から `- [ ]` を書かない（字下げやコードブロック外の文に変える）。

````markdown
# 懸念台帳

レビュー指摘・執筆時の懸念・保留判断のうち、コンテンツの信頼性に関わるものを記録する。
解決したら `[x]` にして対応コミットを付記する。着手を決めたものは [BACKLOG.md](BACKLOG.md) へ移す。

形式: `<対象ファイル>: <懸念内容>。出所: <レビュー/執筆者/ユーザー>。対応方針: <方針>。status: <状態>`

`status` は行末に置く。集計と抽出:

```bash
python3 apm_modules/lostandfound/kb-harness-core/scripts/concerns_summary.py
python3 apm_modules/lostandfound/kb-harness-core/scripts/concerns_summary.py --actionable
```

- `open` … 着手できる。調査の手立てがある
- `investigating` … 調査中
- `blocked-source` … 一次資料の入手待ちで着手できない。何を入手すれば動くかを対応方針に書く
- `settled-hedged` … 史料的に決着しないが、両論併記・ヘッジで記述側は完了している。新資料が出るまで動かさない
- `suspended` … 打ち切り。再開条件を対応方針に明記する
- `resolved` … 解決（`[x]` と併記する）

`settled-hedged` と `suspended` は「もう手を入れない」宣言であり、誤って付けると懸念が沈む。
資料が出れば動く見込みがあるものには使わない。

## 未解決

## 解決済み
````

### `docs/BACKLOG.md` の雛形

行形式は導入先が定めてよいが、対象・型・一行説明・relations 案・根拠・完了時のコミットを 1 行に収めると、`expand-kb` が候補選定と完了記録を機械的に行える。探索候補セクションの書式コメントは `explore-kb` が追記時に参照する。滞留上限（探索候補が何件を超えたら新規探索を止めるか）と棚卸周期は導入先の拡張方針文書で決め、ここから参照する。

````markdown
# 拡張バックログ

実施すると判断した将来作業の正本。上から優先。着手中という中間状態は書かず、実装と検証が完了した後に `[x]` へ変更する。
未整理の疑問は [CONCERNS.md](CONCERNS.md) に置き、対応方針が決まったものだけをここへ移す。

形式: `- [ ] <slug> (<type>): <一行説明>。relations 案: <述語 → パス>。根拠: <言及済み未収録 / RAG 欠落 / カテゴリバランス など>（コミット: <hash>）`

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

- **正本は `.apm/`。** スキル・エージェントを修正するときはパッケージ側の `.apm/` を編集し、`apm install` で再デプロイする。ランタイム配下（`.claude/skills/` など）の同名ファイルは生成物であり直接編集しない。
- `apm audit` で、正本と展開先のドリフト（未反映の差分）を検査できる。
- エージェント定義は `.apm/agents/` では `*.agent.md` だが、デプロイ後は対象ランタイムの形式（Claude は `.md`、Codex は `.toml`）になる。
- scripts の正本はパッケージの `scripts/`。導入先からは `apm_modules/lostandfound/kb-harness-core/scripts/<name>.py` で直接呼び、導入先ルートに symlink を張らない。導入先ルートの `scripts/` は導入先固有のスクリプト置き場として使える。
- `kb doctor` は `pyproject.toml` が宣言する `kb-ontology-core` のタグとインストール済みバージョンの不一致を報告する。依存を更新したら再インストールする。
