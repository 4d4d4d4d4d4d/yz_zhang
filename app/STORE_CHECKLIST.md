# MOB-033 应用商店提审清单

> 这些不是「最好有」，是**审核必查项**——缺任何一条会被直接打回。
> 本文件只列平台侧需要准备的东西；开发者账号与证书需由你提供。

## 必须在 App 内可达（不能只在网页版有）

| 项 | 后端能力 | App 侧现状 |
|---|---|---|
| 账号注销入口 | `POST /users/me/deactivate`（ACC-006 脱敏保留） | ✅ 「我的」页，**拦截理由原样显示**（有余额/在途合约时服务端会拦，只显示一个报错等于没说明白） |
| 内容举报入口 | `POST /reports`（已实现） | ✅ 任务详情页，**带 target_type**（只发 reason 的话，运营收到的是一堆不知道在说什么的工单） |
| 拉黑/屏蔽用户 | `POST /users/{id}/block`（已实现） | ✅ 任务详情页，对手方可拉黑 |
| 用户协议与隐私政策 | `legal` 模块文书接口 | ✅ 「我的」页，含版本号与 LAW-032 数据主体权利入口 |
| 权限用途说明 | — | ✅ `app.json` 已配中文说明 |

> V88 之前这四行全是「⚠️ 待接入」。它们在 Web 上早就有了，差的只是
> App 上这几个按钮——而**缺任何一条会被直接打回**。

## 资金出入（V91）

| 项 | 状态 |
|---|---|
| 充值 | ✅ 钱包页 |
| **提现** | ✅ 钱包页（V91 补）。此前 App **只有充值没有提现** |
| **绑定收款账户** | ✅ 钱包页（V91 补）。提现的前置条件，此前**全仓没有任何界面能满足它**——Web 的提现按钮每次点击都回 400 |
| 账单流水 | ✅ 钱包页（V91 补） |

> 一个**能收钱、不能退钱**的 App 不只是体验问题：审核方会当成典型的
> 资金风险项。这一条比那四项必查项还硬。

## 提审材料

- 测试账号（含已实名、有余额、有进行中任务的账号各一个）
- 演示视频：完整跑一遍发布 → 接单 → 托管 → 验收
- 「涉及资金/交易」需在审核备注中说明资金由持牌机构托管（VND-010 接入后）

## 深链（MOB-032）

- 自定义 scheme：`taskplat://tasks/{id}`
- Universal Link / App Links：`https://<域名>/tasks/{id}`
  - iOS 需在域名根部署 `.well-known/apple-app-site-association`
  - Android 需部署 `.well-known/assetlinks.json`
  - 未安装 App 时自动落到 Web 版同一页面（Web 路由已是 `/tasks/:id`，天然对齐）

## 构建

```bash
cd app
npx eas build --platform android --profile production
npx eas build --platform ios --profile production
```

⚠️ 需要 Expo 账号 + Apple Developer / Google Play 开发者账号，平台侧无法代劳。
