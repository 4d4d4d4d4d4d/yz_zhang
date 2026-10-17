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
  # CI-002：只 grep「Tests」那行会漏掉 vitest 的「Errors  3 errors」（未处理的异步错误：测试全过、退出码却是 1，
  # GitHub CI 红了而本地回归是绿的）。现在每一步都看退出码，非 0 就写一行「步骤失败」。
  npm test -w packages/core -- --reporter=default --reporter=json --outputFile.json="$J/core.json" 2>&1 | grep -E "Tests |Errors |FAIL"
  rc=${PIPESTATUS[0]}; [ "$rc" -eq 0 ] || echo "步骤失败（退出码 $rc）：SDK 单元测试"
  npm test -w web -- --reporter=default --reporter=json --outputFile.json="$J/web.json" 2>&1 | grep -E "Tests |Errors |FAIL"
  rc=${PIPESTATUS[0]}; [ "$rc" -eq 0 ] || echo "步骤失败（退出码 $rc）：Web 单元测试"
  ( cd app && npx jest --json --outputFile="$J/app.json" 2>&1 | grep -E "^Tests:|FAIL"; exit "${PIPESTATUS[0]}" )
  rc=$?; [ "$rc" -eq 0 ] || echo "步骤失败（退出码 $rc）：App 单元测试"
  # CI-002 / CI-004：模拟 GitHub CI 的 App job 依赖布局——只装 app 的依赖、没有根 node_modules，
  # 跑几条引用共享 SDK 源码的单测。本机根目录什么都装着，CI-001 那种「CI 上找不到依赖」本地永远碰不到。
  ( C="$W/cisim"; rm -rf "$C"; mkdir -p "$C" \
    && tar --exclude='./app/node_modules' --exclude='./packages/core/node_modules' -C "$W" -cf - ./app ./packages/core ./package.json | tar -xf - -C "$C" \
    && cp -a "$REPO/app/node_modules" "$C/app/node_modules" \
    && cd "$C/app" && timeout 600 npx jest gig.test profiles.test screenBoundary --forceExit 2>&1 | grep -E "^Tests:|Cannot find module"; exit "${PIPESTATUS[0]}" )
  rc=$?; rm -rf "$W/cisim"; [ "$rc" -eq 0 ] || echo "步骤失败（退出码 $rc）：CI 依赖布局下的 App 单测"
  npx eslint packages/core/src web/src app 2>&1 | tail -3
  npx tsc -p web --noEmit 2>&1 | tail -3
  rc=${PIPESTATUS[0]}; [ "$rc" -eq 0 ] || echo "步骤失败（退出码 $rc）：Web 类型检查"
  # CI-005：App 也做类型检查（GitHub CI 的 App job 有这一步，本地以前没有——测试文件里的类型错误本地回归放得过去）
  ( cd app && npx tsc --noEmit 2>&1 | tail -3; exit "${PIPESTATUS[0]}" )
  rc=$?; [ "$rc" -eq 0 ] || echo "步骤失败（退出码 $rc）：App 类型检查"
  ( cd server && python3 -m scripts.check_frontend_counts --dir "$J" core web && python3 -m scripts.check_frontend_counts --dir "$J" app )
  ( cd server && python3 -m scripts.harness check )
  npm run build:web 2>&1 | tail -1
  rc=${PIPESTATUS[0]}; [ "$rc" -eq 0 ] || echo "步骤失败（退出码 $rc）：Web 构建"
  ( cd server && timeout 600 python -m scripts.e2e_web 2>&1 | tail -4 )
} > "$W/fe.txt" )
echo done >> "$W/fe.txt"
cat "$W/be.txt" "$W/fe.txt"
# REG-001（V171 回归误推之后补）：此前这个脚本无论测试红没红都以 0 退出，
# 看输出的人只看了最后几行就推送了一个后端有 3 条失败的提交。现在任何一处失败都以非 0 退出，并在最后一行写明。
if grep -qE "[0-9]+ failed|[0-9]+ error|FAIL|×|error TS|problems|计数不一致|联调失败|步骤失败" "$W/be.txt" "$W/fe.txt" \
   || ! grep -q "harness 检查通过" "$W/fe.txt" || ! grep -q "联调通过" "$W/fe.txt"; then
  echo "回归失败：见上面的输出，不要推送"
  exit 1
fi
echo "回归全绿"
