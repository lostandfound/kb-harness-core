#!/bin/bash
# このスクリプトと同じ場所にある hooks/pre-commit を、導入先の .git/hooks/pre-commit にインストールする。冪等。
# 導入先ルートの scripts/ には依存しない（apm_modules 配下から直接実行できる）。
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
script_dir=$(cd "$(dirname "$0")" && pwd)

cp "$script_dir/hooks/pre-commit" "$repo_root/.git/hooks/pre-commit"
chmod +x "$repo_root/.git/hooks/pre-commit"

echo "pre-commit hook をインストールしました: $repo_root/.git/hooks/pre-commit"
