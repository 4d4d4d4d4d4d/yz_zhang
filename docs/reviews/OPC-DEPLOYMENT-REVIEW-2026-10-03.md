# OPC 平台：代码评估与服务器联调交付

检查日期：2026-10-02—03。目标：独立个体围绕项目自组织、透明协作，减少组织等级和信息壁垒。

## 结论

代码是一套有较完整交易状态机和测试的模块化单体，适合用作 OPC 协作平台的底座。当前产品仍混合零工接单、本地服务、社区内容与企业预算审批，不能直接视为成熟的 OPC 产品，也不具备真实资金商用条件。

已经实际部署 Web、FastAPI API、PostgreSQL 16、Redis 7 与定时 worker；本地 Web 和 App SDK 可以共用服务器数据。App 的 iOS/Android JS 打包成功，但尚未完成真机安装验收，未交付 APK/IPA。

此次部署明确为**内部联调**：`PLATFORM_ENV=test`，模拟支付/实名/短信，服务仅绑定服务器回环地址，通过 SSH 隧道访问。生产启动检查未绕过或削弱。

## 代码与环境位置

- 上游：`https://github.com/4d4d4d4d4d4d/yz_zhang.git`
- 来源分支：`claude/task-platform-spec-u8qdxb`
- 来源提交：`d887da7306ff3037b77bb4189b91326b972a9139`
- 本地目录：`/Users/wen/Documents/ChatGPT/workdesktop/yz_zhang`
- 本地工作分支：`codex/server-integration`；没有向 GitHub 推送。
- 服务器目录：`/opt/opc-platform`
- Compose 项目：`opc-staging`
- 服务器入口：`127.0.0.1:18080`；数据库、Redis、API 没有发布公网端口。
- 密钥：仅在服务器 `deploy/.env.staging.local`，权限 600；不提交 Git。
- 现有宿主机 Nginx 的 80/443 与原 Next.js 服务未修改。

## 如何访问

在本地仓库目录执行并保持终端打开：

```bash
./deploy/connect-staging.sh
```

浏览器打开 `http://127.0.0.1:18080`，这访问的是服务器上的 Web。

演示账户：`13900010001`，密码 `pass123456`；执行者账户为 `13900010003`，同密码。全部为种子测试账户，仅存在于这个私有联调环境。演示内容仍保留原仓库的服务类样例，未把它伪装成已实现的 OPC 产品。

本地开发 Web：

```bash
cp web/.env.example web/.env.local
npm ci
npm run dev -w web -- --host 127.0.0.1
```

打开 `http://127.0.0.1:5173`，`/api` 通过隧道访问同一服务器；数据留在服务器 PostgreSQL。

App：

```bash
cd app
cp .env.example .env.local
npm ci
npx expo start --clear
```

`EXPO_PUBLIC_API_BASE_URL` 不含 `/api/v1`。iOS 模拟器使用 `http://127.0.0.1:18080`；Android 模拟器使用 `http://10.0.2.2:18080`。USB Android 真机可通过 `adb reverse tcp:18080 tcp:18080` 访问电脑隧道。iPhone 真机不能使用电脑的 localhost，仍需手机隧道/VPN或后续 HTTPS 域名。当前机器没有可用的 `xcrun simctl`，因此没有宣称完成设备测试。

服务器服务有 `restart: unless-stopped`，本地隧道与 Vite 则需要在电脑上运行。电脑睡眠或 SSH 断开时重新运行连接脚本即可。

## 实现结构与真实成熟度

| 部分 | 实际实现 | 判断 |
|---|---|---|
| 后端 | FastAPI + SQLAlchemy + Alembic，业务分模块 | 可继续保持单体，不需要先拆微服务 |
| 数据库 | 默认开发 SQLite；生产配置 PostgreSQL；大量模型和迁移 | 数据库并不缺，缺的是可靠生产部署与运维验证 |
| Web | React 18 + Vite + PWA + 管理后台 | 能运行，但入口多且面向“接单交易” |
| App | Expo SDK 51 / React Native 0.74，共享 TS SDK | 页面不少，仍缺设备、商店与依赖升级验收 |
| 合作体 | 贡献提报、另一成员确认、贡献计价计算份额、收入分配快照 | 最接近 OPC 核心，应提升为主入口 |
| 团队 | owner/admin/member、支出审批、月度额度池 | 企业预算组织模型，需与自组织合作体明确区分 |
| 任务履约 | 发布、选人、双签、托管、交付、验收、纠纷、评价 | 状态机可复用；当前资金闭环仅为模拟 |
| AI | 模板分解、可选模型调用、Agent 编排与核验 | 此部署没有 AI 服务密钥，未验收真实模型输出 |
| 通知 | 站内通知、worker、推送网关抽象 | App 的 getPushToken() 返回 null，尚无真实推送 |
| 文件 | 本地图片、上传校验、直传接口抽象 | 已持久化图片；视频直传缺真实对象存储 |
| 外部服务 | payment/sms/kyc/moderation 只有 mock/sandbox/local | 不是“填几个环境变量”即可商用，必须编写并验收真实适配器 |

主要依据：`server/app/vendors/registry.py`、`server/app/modules/coop/{models,service,router}.py`、`server/app/modules/team/models.py`、`app/App.tsx`、`app/app.json`、`web/src/App.tsx`。

## 本次发现并修复的问题

1. **生产服务必然撞上禁止自动建表的异常。** `create_app()` 原来无条件调用 `init_db()`，而后者在 prod 主动抛异常。现在生产仅检查 Alembic 状态，未迁移或版本不符则拒绝启动；开发保持原流程。扩展了现有部署测试验证成功与失败路径。
2. **PostgreSQL 首次迁移失败。** 资质迁移使用 `json != '[]'`，PostgreSQL JSON 类型不支持该比较；改为读取非空值，在 Python 循环自然跳过空数组。
3. **布尔迁移方言错误。** `allow_agents = 0` 改为跨 SQLite/PostgreSQL 可用的 `FALSE`。
4. **App 接口地址写死 localhost。** 改成 Expo 公开环境变量，补两端配置样例和接入说明。
5. **App 单测通过但实际打包失败。** Metro 禁止层级依赖查找，导致 React Native 自身嵌套安装的 virtualized-lists 找不到。恢复嵌套解析，并固定 React 来源避免 Web/App 混用；双端 JS 导出已通过，加入 CI。
6. **上传目录没有持久化且挂载后不可写。** 增加 uploads 卷与明确路径，镜像预建 appuser 所有的目录；修复此次新卷权限。真实上传已成功。
7. **生产 Compose 漏传配置。** 补税务、OAuth、captcha、协议版本、推送、存储与上传路径等已有配置；仍须按真实供应商实现继续补充专属参数。
8. **前端镜像构建未使用锁文件。** 改为复制 package-lock 并执行 npm ci。
9. 增加私有部署配置、SSH 连接与备份脚本、Web 联调提示、敏感配置忽略规则。

## 验证证据与边界

| 检查 | 结果 |
|---|---|
| 后端 pytest 全量 | 1,195 passed，189.28 秒；本地 SQLite 测试 |
| 共享 SDK | 56 passed |
| Web | 84 passed；TypeScript、Vite 构建、全仓 lint 通过 |
| App | 21 passed；TypeScript 通过 |
| App 实际打包 | iOS/Android 均导出 Hermes 包；不是商店安装包 |
| 服务器迁移 | PostgreSQL 从空库迁移到 head 成功 |
| 服务器就绪 | db=ok，ratelimit=redis，migration=ok |
| 服务器 HTTP 冒烟 | 注册到验收分账全闭环通过；200 元模拟任务执行方到账 184 元、8% 平台佣金 |
| 本地与服务器数据 | 用真实共享 SDK 分别请求 5173 与 18080，同一 accountId=3、taskIds=[4,3,2] |
| 图片上传 | 真实上传返回 URL，文件存在持久卷；随后验证重建后可读 |
| 浏览器 | 服务器 Web 显示演示任务；演示账户真实登录成功 |
| 运维 | 新增数据库与上传备份脚本；恢复演练结果另见交付记录 |

没有做完整渗透测试、生产压测、真实支付商验签/退款/清算验证，也未运行全量 PostgreSQL 业务测试。模拟供应商通过不代表真实供应商通过。

依赖审计（本次 npm audit --omit=dev）：Web 工作区 0；App 安装依赖树 32 项，其中 1 critical、12 high、18 moderate、1 low。critical 涉及 tar 解包链。Expo 的 dependencies 同时包含 CLI 工具，不能将这 32 项直接等同于手机运行时可利用漏洞；必须分析可达性并升级。没有执行 `npm audit fix --force`，因为其建议包含不合理的 Expo 降级，可能破坏现有兼容性。

## OPC 产品应该先改什么

建议主导航改为“机会 / 协作空间 / 伙伴 / 消息 / 我的”，把社区和视频降为作品与知识内容，不占独立一级入口。桌面以协作工作台为主，移动端聚焦待办、讨论、确认与交付。

- **机会卡片**：目标成果、所缺能力、当前成员、预计投入、里程碑、报酬/贡献规则、招募状态。当前首页基本只有标题、类目、预算与状态，不足以判断长期合作是否适合。
- **协作空间**：目标、任务依赖、交付物、决策记录、贡献账、知识文档共享一个上下文，避免通知、聊天、合约、团队散在不同页面。
- **贡献规则先约定**：现有机制允许另一成员确认计价，尚不足以解决串谋互认、计价分歧、份额稀释和退出争议。规则应版本化，并明确哪些变更要哪些成员确认。
- **决策可追溯**：提案、讨论、异议、确认人与生效时间可见。扁平协作仍需要最小权限、隐私边界和明确责任；不应让“所有人都有管理员权限”代替治理。
- **收益分配要有共同授权**：目前分配接口以合作体成员身份为入口，没有多成员共同确认这一层；应增加项目约定的确认门槛、预算和异常处理。
- **信誉来自证据**：展示验收记录、合作角色、作品与争议处理结果，区分个人履约信誉、团队记录和 AI 产出。不要仅依赖单一信用分。
- **AI 成为协作助理**：整理讨论、提出任务拆分、提示依赖与遗漏、总结可复用知识；涉及预算、对外承诺、收益分配和敏感文档访问仍按成员授权执行。

验收首个 OPC 场景应是：三个独立个体发起项目 → 约定目标与贡献规则 → 分解里程碑 → 记录公开决策 → 提交与核验成果 → 确认贡献和分配 → 导出项目知识。先把这一条做顺，再扩张社区与内容生态。

## 商用缺口与建议顺序

| 优先级 | 工作 | 完成标准 |
|---|---|---|
| P0 | 明确经营地区、主体与首期商业模式 | 明确是协作 SaaS、撮合佣金还是其他模式；再由专业顾问确认协议、隐私、税务与支付责任，不能照抄仓库的概括性法律结论 |
| P0 | App 依赖升级与真实设备测试 | 分阶段升级 Expo/RN，重新构建、扫码/相机/定位/通知/断网/恢复登录实测通过 |
| P0 | 真正的身份与支付适配 | 根据首期范围对接短信/OAuth/实名/支付等，真实回调验签、幂等、退款、对账与异常补偿通过；未完成前仅测试数据 |
| P0 | OPC 权限与治理 | 项目规则版本化、贡献异议、共同授权、退出与知识产权约定可执行 |
| P1 | 域名与 HTTPS | Web/App 相同 API、移动深链、PWA、环境隔离与证书更新可用 |
| P1 | 数据运维 | PostgreSQL 独立权限、异机备份、恢复演练、容量监控；按恢复目标评估 WAL/PITR |
| P1 | 对象存储与通知 | S3 兼容存储/私有访问/配额，图片视频审核与生命周期；真机推送及投递失败补偿 |
| P1 | 安全与观测 | 密钥管理、依赖固定、独立安全审查、错误跟踪、指标告警、任务失败/死信可处理 |
| P1 | App 发布 | 替换 com.example 包名与示例域名、签名、开发者账户、隐私与删除账户流程、发布流水线 |
| P2 | UI 与增长 | 先提高组队、交付、复用效率，再加入推荐、动画与社区增长 |

服务器只有约 961MiB 内存、24GB 系统盘且已经有业务。当前容器实测合计约 173MiB，只证明低负载可联调，不是容量保证。建议商业试点从独立 2 vCPU / 4GB 内存与更大磁盘的环境起步，再根据并发、附件、后台任务和压测结果调整；不建议在现机器运行本地大模型或 Blender 渲染。

## Blender 与界面设计

Blender 适合做品牌三维视觉、节点网络动画和宣传素材；它本身不能修复前端信息架构或协作流程。此阶段建议先完成高保真页面与真实操作，再按需加入少量预渲染素材。交付、确认、分账页面优先清晰、稳定、易读。没有安装 Blender，也没有将 3D 效果强加到当前界面。

参考：[Blender 官方功能](https://www.blender.org/features/)、[Expo 环境变量](https://docs.expo.dev/guides/environment-variables/)、[Expo SDK 升级流程](https://docs.expo.dev/workflow/upgrading-expo-sdk-walkthrough/)、[PostgreSQL 16 PITR](https://www.postgresql.org/docs/16/continuous-archiving.html)。

## 备份恢复实测记录

已生成 `deploy/backups/20261002T161129Z.dump` 和同时间的 `.uploads.tar.gz`。备份期间仅停止本平台 API/worker，完成后恢复并检查就绪；没有停止宿主机已有网站。

数据库恢复到独立的 `opc_restore_check_20261003`，没有覆盖当前联调库。使用仓库原有 `scripts.consistency_check` 校验：6 个账户对账通过、10 条存证链有效。上传文件解包后与运行卷 SHA-256 一致；容器重建后原图片仍返回 HTTP 200。

同时把这一次数据库与上传备份复制到本地 `deploy/backups/`（Git 忽略）。这是手工备份及恢复演练，没有配置定期备份、保留策略、异地自动复制或灾备告警。

测试与审计原始输出位于本目录的 `evidence/`；服务器上保留 `deploy/smoke-result.log`、`deploy/seed-result.log`、`deploy/backup-result.log`。历史脚本输出中“真实交易”仅指真实 HTTP/数据库事务，本环境没有转移任何真实资金。
