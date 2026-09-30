# App（React Native / Expo）— MVP 骨架

复用 `@platform/core` SDK，与 Web 共用同一后端（13 号 spec「两端共享 API」）。

当前为骨架版：登录注册、任务列表（下拉刷新）、快速发布小任务、我的页。
路线图（对应 13-clients.md）：LBS 附近任务地图（GEO-010）、任务详情操作、
扫码打卡（GEO-020~022）、消息推送（NTF-002）、发现内容 Tab（08）。

## 运行

```bash
# 启动后端
cd server && uvicorn app.main:app --port 8000
# 启动 App（真机调试需把 App.tsx 里 BASE_URL 改为局域网 IP）
cd app && npm install && npx expo start
```

`app` **不是根 workspace 成员**，独立安装。这是有意的：并进根 workspaces
会让 Web 的 `npm ci` 也去装整个 react-native，为一个它不碰的端付出好几百 MB。
`@platform/core` 因此用 `file:../packages/core` 链过来
（APPB-001——此前写的是 `"*"`，`npm install` 实测直接 E404）。

## 类型检查

```bash
cd app && npm run typecheck
```

CI 的 `app-typecheck` job 跑的就是这条。`app/` 到 V71 为止只有 esbuild
解析闸门（挡语法错误），补上类型检查后**第一次跑就查出一处真错**：
`Contract.deposit_cents` 不在共享类型里。

## 还没验证的

`npx expo start` 需要连真机或模拟器，CI 与开发容器里都跑不了。
**装得上、类型对，不等于跑得起来**——上架前必须真机实测一轮
（VID-050 / PRLX-040 / APPB-051）。
