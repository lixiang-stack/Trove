#!/usr/bin/env bash
# 本地 Git 策略:禁止直接 push main、已合并分支;commit subject 前缀在 push 前兜底检查。
set -euo pipefail

remote=${1:-origin}
main_ref="refs/remotes/$remote/main"
status=0
zero_sha=0000000000000000000000000000000000000000
msg_file=$(mktemp)
trap 'rm -f "$msg_file"' EXIT

# 已合并分支守卫需要最新 main;离线时退回本地引用。
git fetch --quiet "$remote" main 2>/dev/null || \
  echo "⚠ 无法刷新 $remote/main，使用本地引用检查。" >&2

while read -r local_ref local_sha remote_ref remote_sha; do
  [ -n "${local_ref:-}" ] || continue

  case "$remote_ref" in
    refs/heads/main)
      echo "✖ direct pushes to main are not allowed; merge via PR." >&2
      status=1
      ;;
    refs/heads/*)
      if [ "$local_sha" = "$zero_sha" ]; then
        continue
      fi
      if git rev-parse --verify --quiet "$main_ref" >/dev/null; then
        if git merge-base --is-ancestor "$local_sha" "$main_ref"; then
          echo "✖ $local_ref 已合并到 ${main_ref}；请从 main 新建 worktree/branch。" >&2
          status=1
          continue
        fi
        base=$(git merge-base "$main_ref" "$local_sha" 2>/dev/null || true)
        if [ -n "$base" ]; then
          # commit-msg hook 在 core.hooksPath 环境可能未安装;push 前兜底检查。
          while IFS= read -r sha; do
            git log -1 --format=%B "$sha" > "$msg_file"
            if ! bash scripts/git/check-commit-msg.sh "$msg_file"; then
              status=1
            fi
          done < <(git rev-list --no-merges "$base..$local_sha")
        fi
      fi
      ;;
  esac
done

exit "$status"
