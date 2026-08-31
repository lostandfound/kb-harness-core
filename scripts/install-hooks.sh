#!/bin/bash
# scripts/hooks/pre-commit を .git/hooks/pre-commit にインストールする。冪等。
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)

cp "$repo_root/scripts/hooks/pre-commit" "$repo_root/.git/hooks/pre-commit"
chmod +x "$repo_root/.git/hooks/pre-commit"

echo "pre-commit hook をインストールしました: $repo_root/.git/hooks/pre-commit"
