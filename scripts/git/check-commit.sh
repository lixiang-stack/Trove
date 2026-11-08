#!/usr/bin/env bash
# 本地 Git 策略:禁止在 detached HEAD、main 或主检出(非 .worktree)提交。
set -euo pipefail

branch=$(git branch --show-current)
if [ -z "$branch" ]; then
  echo "✖ detached HEAD: run 'git switch -c <branch>' before committing." >&2
  exit 1
fi
if [ "$branch" = "main" ]; then
  echo "✖ commits on main are not allowed; use a feature branch and merge via PR." >&2
  exit 1
fi

root=$(git rev-parse --show-toplevel)
main_worktree=$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)
if [ "$root" = "$main_worktree" ]; then
  echo "✖ development in the main checkout is not allowed; use a .worktree/<name> workspace (branch: ${branch:-detached})." >&2
  exit 1
fi
