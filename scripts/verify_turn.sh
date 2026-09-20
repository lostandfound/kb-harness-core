#!/bin/bash
# Claude Code の Stop hook から呼び、ターンの終了を検証で閉じるためのスクリプト。
#
# WHY: pre-commit が閉じるのはコミットするときだけで、コミットせずに終わるターンでは
# 検証が一度も走らない。生成物の陳腐化や本文の壊れは、次に誰かがコミットするまで
# 残り続ける。exit 2 で終了すると標準エラーがそのまま Claude に返るため、指示しなくても
# その場で直してから終わる。
#
# 導入先の .claude/settings.json の Stop hook に登録して使う。
set -uo pipefail

payload=$(cat)

# stop_hook_active のときに再度ブロックすると、停止と再開が延々と繰り返される。
if printf '%s' "$payload" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    exit 0
fi

# KB 以外の作業ディレクトリでは何もしない。
if [ ! -f kb-domain.yml ]; then
    exit 0
fi

if ! output=$(kb validate 2>&1); then
    echo "$output" >&2
    echo "kb validate が失敗しています。修正してからターンを終えてください。" >&2
    exit 2
fi

if ! output=$(kb sync --check 2>&1); then
    echo "$output" >&2
    echo "生成物が古くなっています。kb sync を実行してください。" >&2
    exit 2
fi

exit 0
