#!/usr/bin/env bash
# 推送前的全量回归（skill: regression）。用法：tools/regress.sh [提交，默认 HEAD] [worktree 目录]
# 在独立 worktree 里跑：后端全量 → SDK/Web/App → lint → 类型检查 → 前端计数核对 → 构建 → 真浏览器联调。
# 结果：<worktree>/be.txt（后端）、<worktree>/fe.txt（其余，最后一行 done）。
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REV="${1:-HEAD}"
W="${2:-${TMPDIR:-/tmp}/regress-wt}"
SHA="$(git -C "$REPO" rev-parse "$REV")"
if [ ! -d "$W/.git" ] && [ ! -f "$W/.git" ]; then
  git -C "$REPO" worktree prune
  git -C "$REPO" worktree add -q --detach "$W" "$SHA"
else
  git -C "$W" checkout -q --detach "$SHA"
fi
for d in node_modules web/node_modules app/node_modules packages/core/node_modules; do
  [ -e "$W/$d" ] || ln -s "$REPO/$d" "$W/$d"
done
rm -rf "$W/reg.db" "$W/be.txt" "$W/fe.txt" "$W/counts"
echo "回归 $SHA 于 $W"
( cd "$W/server" && PLATFORM_DATABASE_URL="sqlite:///$W/reg.db" python -m pytest -q -p no:cacheprovider 2>&1 | tail -3 > "$W/be.txt" )
J="$W/counts"; mkdir -p "$J"
( cd "$W" && {
  npm test -w packages/core -- --reporter=default --reporter=json --outputFile.json="$J/core.json" 2>&1 | grep -E "Tests |FAIL"
  npm test -w web -- --reporter=default --reporter=json --outputFile.json="$J/web.json" 2>&1 | grep -E "Tests |FAIL"
  ( cd app && npx jest --json --outputFile="$J/app.json" 2>&1 | grep -E "^Tests:|FAIL" )
  npx eslint packages/core/src web/src app 2>&1 | tail -3
  npx tsc -p web --noEmit 2>&1 | tail -3
  ( cd server && python3 -m scripts.check_frontend_counts --dir "$J" core web && python3 -m scripts.check_frontend_counts --dir "$J" app )
  ( cd server && python3 -m scripts.harness check )
  npm run build:web 2>&1 | tail -1
  ( cd server && timeout 600 python -m scripts.e2e_web 2>&1 | tail -4 )
} > "$W/fe.txt" )
echo done >> "$W/fe.txt"
cat "$W/be.txt" "$W/fe.txt"
