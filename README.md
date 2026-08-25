# 协作任务平台（Task Platform）

AI 驱动的任务协作与本地服务平台 Monorepo：任务发布 → AI 分解 → 智能推荐 →
合约托管 → 执行验收 → 结算评价 → 经验入库的完整闭环。

> Spec 驱动开发：先写 [docs/specs/](docs/specs/README.md)（15 个模块功能拆分），
> 再按 spec 逐模块实现并配测试，追溯矩阵见 [16-traceability.md](docs/specs/16-traceability.md)。

## 目录结构

```
docs/specs/       # 功能拆分 spec（01~15）+ 追溯矩阵（16）+ 编排循环（17）
                  # + 生产化 spec：并发（18）供应商（19）部署（20）移动端/PWA（21）增长运营（22）
                  # + 合规化 spec：抗攻击（23）AI 编排增强（24）资金合规（25）法律效力（26）
docs/OPERATIONS.md # 部署 / 并发 / 安全 / 运营增长手册（含明确缺口清单）
server/           # 后端：FastAPI 模块化单体（Python 3.11+）
  app/core/       #   配置/DB/安全/事件总线/依赖/并发锁/可观测/边界防护
  app/vendors/    #   外部供应商抽象层（支付/短信/eKYC/内容审核，缺省 Mock）
  app/modules/    #   account task matching contract wallet decompose knowledge files growth finance
                  #   im dispute notification support content circle legal admin search anchor risk analytics orchestrator
  tests/          #   401 个测试（端到端闭环+状态机穷举+资金守恒 fuzz+各交叉路径守恒+平台佣金实收对账+收款账户绑定+任务过期下架+广场/我的任务/我的报名分页+通知中心+cron 端点鉴权+幂等指纹+登录限流+签署/纠纷 SLA+真双盲评分+任务编辑防调包+接单上限/开关+提现风控+对账告警+密码/换绑/设备安全+防重放+越权+存证链防篡改+管理员审计+封禁影响面+口碑页双盲防旁路+封禁挂单下架+IM未读位点+纠纷答辩期+编排循环护栏+并发放款/托管/提现真并发+乐观锁防丢失更新+job单实例锁+健康就绪探针+限流降级+支付回调验签/重放/金额不符+供应商幂等熔断+验证码只存哈希+证件号脱敏防一人多号+生产启动自检+迁移与模型不漂移+日志脱敏+指标基数+job健康反查排期+图片上传魔数/超限/穿越/外链拒绝+补贴资金守恒/一单一券/仅一级分销/活动预算硬顶）
packages/core/    # 共享 TS SDK（Web/App 复用，23 tests，含操作可见性矩阵）
web/              # Web 前端：React + Vite + PWA（17 tests，含管理后台/移动端约束/优惠页）
app/              # App：React Native / Expo 骨架
deploy/           # 生产部署：prod compose + 自检启动 + 备份/恢复脚本
tools/            # 与平台无关的历史小工具（file-organizer）
```

## 快速开始（Docker，一键全栈）

```bash
docker compose up --build          # 开发栈（SQLite 单副本）
# Web: http://localhost:8080  /  API 文档: http://localhost:8000/docs

cp deploy/.env.example deploy/.env && ./deploy/up.sh   # 生产栈（Postgres+Redis+多副本）
```

生产栈起栈前会做配置自检（弱密钥、CORS 为 `*`、供应商仍是 mock 一律拒绝启动），
详见 [docs/OPERATIONS.md](docs/OPERATIONS.md) 第四节。

CI：`.github/workflows/ci.yml` 在每次 push/PR 自动跑后端 pytest、前端 vitest+构建、服务启动冒烟。

## 快速开始（本地开发）

```bash
# 后端（Python 3.11+）
cd server
pip install -r requirements.txt
python -m pytest tests/ -q        # 跑测试
uvicorn app.main:app --port 8000  # 启动 API（文档：/docs）

# 前端（Node 20+，仓库根目录）
npm install
npm test          # core + web 全部测试
npm run dev:web   # http://localhost:5173（代理 /api 到 8000）
```

## 体验主闭环（Web）

1. 注册两个账号（验证码固定 `123456`），在「我的」完成实名认证（模拟）。
2. 账号 A 充值（钱包页，模拟支付）→ 发布任务；项目型任务会触发 **AI 分解**，
   可编辑子任务预算后确认，无前置依赖的子任务自动发布。
3. 账号 B 设置技能标签 → 在广场报名；A 在任务详情查看 **AI 推荐人选** 并选人。
4. 双方**签署智能合约** → A 托管资金 → B 执行（进度/打卡）→ 提交验收。
5. A 验收通过自动放款（平台抽佣 8%）→ 双向互评 → 信用分更新 →
   经验卡入库，下次发布同类任务可查「参考价」。
6. 出问题可「发起纠纷」：资金冻结 → 和解或仲裁 → 裁决自动执行分账。

## 技术要点

- **状态机**：任务/合约状态流转白名单约束，非法流转 409。
- **事件总线**：进程内领域事件（`task.completed`、`contract.funded`…）驱动
  经验入库、后继子任务发布、会话创建、通知，生产可平滑替换为 MQ。
- **资金**：整数分记账、只增流水、三态账本（可用/托管/冻结）、E2E 资金守恒断言。
- **LLM 网关**：`decompose/llm.py` 抽象接口 + 模板实现 + 真实 `AnthropicLLM`
  （claude-opus-4-8，adaptive thinking，JSON Schema 结构化输出）。设 `ANTHROPIC_API_KEY`
  即启用真实分解，失败自动降级模板；缺省与 CI 走模板引擎，接入不动业务代码。
- **演示数据**：`cd server && python -m scripts.seed_demo` 一键生成可交互样例
  （用户/任务/闭环/圈层/动态；密码 `pass123456`）。
- **可解释推荐**：技能/信用/距离/评价加权，返回推荐理由。
