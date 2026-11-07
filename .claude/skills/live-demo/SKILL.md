---
name: live-demo
description: Prove a feature is real — start the real backend (uvicorn, sandbox env, temp DB) and the built web bundle behind a same-origin proxy, seed data through real HTTP, drive Chromium with Playwright, and screenshot the pages. Use when the user doubts features are real or after a user-facing batch.
---

# 真后端 + 构建产物 + 真浏览器

1. `npm run build:web`（验的是构建产物，不是 dev server）。
2. 用 `server/scripts/e2e_web.py` 里的 `_serve_dist()` 起静态服务加 `/api` 反代；用 `PLATFORM_ENV=sandbox`、临时 SQLite 起 `uvicorn app.main:app --port 8123`。
3. 用 `scripts/smoke.py` 的 `req()` 通过真 HTTP 造数据（注册、实名、充值带幂等键、发任务……）。
4. Playwright 用 `/opt/pw-browsers/chromium-*/chrome-linux/chrome`，把 token 写进 `localStorage` 后逐页 `screenshot(full_page=True)`。
5. 截图逐张看：错位、看不清、英文类目名、默认值带错都算缺陷，记进 BACKLOG 或当批修掉。
6. 结果用 SendUserFile 发给用户，并说清哪些是真功能、哪些是沙箱 / 模拟（支付、存管、实名、短信、电子签名需要持牌机构）。
