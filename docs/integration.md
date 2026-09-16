# 導入ガイド

新しい KB リポジトリにこのハーネスを組み込む手順。

## 前提

- Python 3.10 以上
- [`apm`](https://github.com/microsoft/apm) CLI（0.28 以上で動作確認）

## 1. `kb-domain.yml` を書く

リポジトリルートにドメイン定義を置く。フィールドは [設定リファレンス](configuration.md#kb-domainyml) を参照。

## 2. `vocabulary.yml` と `references.yml` を書く

`<content_root>/` 配下に語彙と文献レジストリを置く。契約は [設定リファレンス](configuration.md) を参照。

## 3. `apm.yml` に依存を追加してデプロイする

```yaml
dependencies:
  apm:
    - lostandfound/kb-harness-core          # GitHub。#tag または #sha で固定を推奨
    # - ../kb-harness-core                  # ローカルパス（モノレポ内・開発中）
```

依存は文字列形式で書く。`github:` キーを持つオブジェクト形式は apm が受理しない。

```bash
apm install --target claude
```

`apm install` はパッケージを `apm_modules/lostandfound/kb-harness-core/` に展開し、`.apm/skills/` `.apm/agents/` を `.claude/skills/` `.claude/agents/` へ配置する。`--target codex` など他ランタイムも選べる。

## 4. `kb` CLI をインストールする

```bash
python3 -m pip install apm_modules/lostandfound/kb-harness-core
kb doctor
```

`pyproject.toml` は `kb-ontology-core` を `git+https://` で参照するため、ssh 鍵は不要。

## 5. scripts を配線する

`scripts/` 配下の補助ツールは APM のデプロイ対象に含まれない。展開先へ symlink を張るか、コピーする。

```bash
ln -s apm_modules/lostandfound/kb-harness-core/scripts scripts
```

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
bash scripts/install-hooks.sh
```

ステージに `.md` / `.yml` / `.py` が含まれるとき `validate.py` → テスト（`tests/` がある場合）→ `rag_smoke.py`（`evals/rag-eval.yml` がある場合）→ `.kb/hooks/pre-commit.d/*`（ある場合）を順に実行する。導入先固有のチェックは `kb-domain.yml` の `validate.extra_checks` か `.kb/hooks/pre-commit.d/` に置き、テンプレート自体は編集しない。

## 運用上の注意

- **正本は `.apm/`。** スキル・エージェントを修正するときはパッケージ側の `.apm/` を編集し、`apm install` で再デプロイする。ランタイム配下（`.claude/skills/` など）の同名ファイルは生成物であり直接編集しない。
- `apm audit` で、正本と展開先のドリフト（未反映の差分）を検査できる。
- エージェント定義は `.apm/agents/` では `*.agent.md` だが、デプロイ後は対象ランタイムの形式（Claude は `.md`、Codex は `.toml`）になる。
- scripts の正本はパッケージの `scripts/`。導入先ルートの `scripts/` はそこへの symlink またはコピーとして運用する。submodule + symlink で組み込んでいる場合、導入先で実行されるのは submodule 側のコードである。
- `kb doctor` は `pyproject.toml` が宣言する `kb-ontology-core` のタグとインストール済みバージョンの不一致を報告する。依存を更新したら再インストールする。
