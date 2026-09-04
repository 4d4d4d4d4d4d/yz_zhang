# App（React Native / Expo）— MVP 骨架

复用 `@platform/core` SDK，与 Web 共用同一后端（13 号 spec「两端共享 API」）。

当前为骨架版：登录注册、任务列表（下拉刷新）、快速发布小任务、我的页。
路线图（对应 13-clients.md）：LBS 附近任务地图（GEO-010）、任务详情操作、
扫码打卡（GEO-020~022）、消息推送（NTF-002）、发现内容 Tab（08）。

## 运行

```bash
# 仓库根目录
npm install
# 启动后端
cd server && uvicorn app.main:app --port 8000
# 启动 App（真机调试需把 App.tsx 里 BASE_URL 改为局域网 IP）
cd app && npm install && npx expo start
```
