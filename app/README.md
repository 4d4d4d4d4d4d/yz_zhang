# App（React Native / Expo）— MVP 骨架

复用 `@platform/core` SDK，与 Web 共用同一后端（13 号 spec「两端共享 API」）。

当前已有登录、任务详情与履约、钱包、通知、合作体和团队等界面。
地图体验、真实推送与商店发布仍需补齐；功能范围以源码与测试结果为准。

## 运行

```bash
# 启动后端
cd server && uvicorn app.main:app --port 8000
# 启动 App（通过 .env.local 配置 EXPO_PUBLIC_API_BASE_URL）
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

## 连接此次服务器联调环境（2026-10-03）

仓库根运行 `./deploy/connect-staging.sh` 并保持终端打开。
复制 `app/.env.example` 为 `app/.env.local`，设置 `EXPO_PUBLIC_API_BASE_URL`：

- iOS 模拟器：`http://127.0.0.1:18080`
- Android 模拟器：`http://10.0.2.2:18080`
- Android USB 真机：先 `adb reverse tcp:18080 tcp:18080`，使用 `http://127.0.0.1:18080`。
- iPhone 真机：上述电脑回环地址不可直接访问；需手机 VPN/SSH 隧道或后续 HTTPS 域名。

`npx expo start --clear` 会读取配置，无需修改 App.tsx。
接口地址包含协议和主机，不包含 `/api/v1`（SDK 会自动添加）。
公开环境变量会打入客户端，不可放服务端密钥。

已验证类型检查、21 项 Jest 测试以及 iOS/Android 的 `expo export`。
导出的 Hermes/JS 包不是 APK/IPA；没有做真机安装、权限和通知验收。
现有 SDK 51、示例 bundle ID、示例域名与未接入的推送令牌仍须处理。
