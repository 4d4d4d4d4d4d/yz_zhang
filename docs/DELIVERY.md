# 交付总览（Final Delivery Overview）

> 截至 2026-08-22：MVP + V1~V47 全批次完成。
> 后端 **349 tests** + 前端 **40 tests**（core 23 + web 17）全绿。
> 本文档是对 [docs/specs/](specs/README.md)（功能拆分）与
> [16-traceability.md](specs/16-traceability.md)（逐条追溯）的收口汇总。

## 一、交付物清单

| 层 | 位置 | 内容 |
|---|---|---|
| Spec | `docs/specs/01~15` | 15 个模块功能点拆分（P0/P1/P2 分级） |
| Spec | `docs/specs/17~22` | 编排循环 / 并发 / 供应商 / 部署 / 移动端 / 增长运营 |
| 追溯 | `docs/specs/16` | Spec → 实现 → 测试 逐批次追溯矩阵（MVP + V1~V46） |
| 后端 | `server/` | FastAPI 模块化单体，20 个业务模块 + core（事件总线/幂等/限流/锁/可观测）+ vendors（供应商抽象层） |
| SDK | `packages/core/` | 共享 TS 客户端（Web/App 复用全部 API） |
| Web | `web/` | React + Vite + PWA：广场/发布/详情/合约/钱包/圈层/动态/优惠/管理后台 |
| App | `app/` | React Native / Expo 骨架（复用 SDK）+ 提审清单 |
| 迁移 | `server/migrations/` | Alembic（生产唯一建表路径，CI 校验无漂移） |
| 部署 | `deploy/` | 生产 compose（PG+Redis+多副本）+ 自检启动 + 备份/恢复 |
| 交付 | 根目录 | Docker Compose 一键全栈 + GitHub Actions CI（含闭环冒烟） |
| 演示 | `server/scripts/seed_demo.py` | 一键生成可交互样例数据 |

## 二、已钉死的核心契约（全部有测试）

**业务闭环**：发布 → AI 分解（预算守恒）→ 推荐（可解释）→ 报名/邀约 →
合约生成 → 双签 → 托管 → 执行留痕/打卡 → 交付 → 验收/自动验收 → 放款抽佣 →
互评 → 信用 → 经验入库 → 参考价。

**安全与资金不变量**：
- 状态机白名单穷举：非法流转全拒（`test_state_machine`）
- 资金三不变量（全局守恒/托管有据/冻结有据），随机生命周期 fuzz（`test_money_property`）
- 防重放：重复接受/托管/交付/验收/里程碑全拒且零副作用（`test_concurrency_guards`）
- 变更单守恒：加价补托管/减价退款/多轮随机改价（`test_change_order_money`）
- 分期×纠纷交叉：部分放款后只分剩余、冻结期禁放款（`test_milestone_dispute_cross`）
- 多人任务名额预算守恒 + 自动验收边界（`test_multiperson_autoaccept`）
- 存证哈希链防篡改：自洽伪造/删行/脱链全被定位（`test_anchor_chain`）
- 幂等（Idempotency-Key）、限流、资源级越权拒绝（`test_hardening`）

**迭代中修复的产品级缺陷**（测试先行暴露）：
存证链重复注册膨胀、刷单阈值差一、多人任务余数蒸发（每单丢分钱）、
dispute 响应缺复核基数字段、圈层创建者角色丢失等。

## 三、外部依赖对接清单（唯一剩余项）

以下能力抽象层已就位（**接入只改环境变量，不动业务代码**），
需供应商/云服务账号才能上线。生产环境若 P0 能力仍是模拟实现，
`startup_check` 会**拒绝启动**并打印缺失清单（VND-042）：

| 能力 | 现状 | 对接点 |
|---|---|---|
| 真实 LLM 分解 | 已接 AnthropicLLM，缺省模板降级 | 设 `ANTHROPIC_API_KEY` 即启用 |
| 短信/eKYC 实名 | `SmsProvider`/`KycProvider` 抽象 + Mock | 设 `PLATFORM_SMS_PROVIDER` / `PLATFORM_KYC_PROVIDER` |
| 持牌支付/提现/开票 | `PaymentProvider` 抽象 + 两阶段订单 + 回调验签 | 设 `PLATFORM_PAYMENT_PROVIDER` |
| 视频转码/CDN | 图片上传已走 `StorageProvider`，视频元数据与发布流已备 | 设 `PLATFORM_STORAGE_PROVIDER` |
| RTC 音视频 | IM 文本/图片已备 | `im` 模块会话扩展 |
| 区块链锚定 | 本地哈希链已备（head 可对外公示） | `anchor` 模块定期上链 job |
| 内容安全审核 | 本地敏感词机审 | `machine_review` 替换为供应商 API |

## 四、如何验证

```bash
docker compose up --build              # 开发栈 Web: :8080 / API 文档: :8000/docs
cd server && python -m pytest -q       # 333 passed
npm test                               # core 23 + web 17 passed
cd server && python -m scripts.smoke   # 对已启动实例跑真实闭环并核对分账
cd server && python -m scripts.seed_demo  # 演示数据（密码 pass123456）

cp deploy/.env.example deploy/.env && ./deploy/up.sh   # 生产栈（自检 → 迁移 → 起栈）
```

## 五、生产化补齐（V42~V46）

| 批次 | 解决的问题 |
|---|---|
| V42 CONC | 多副本资金安全：行锁 + 乐观锁 + 状态机三层；Redis 限流；job 单实例锁 |
| V43 VND | 支付/短信/eKYC/内容审核统一 Provider 抽象；充值改两阶段；回调验签与重放防护 |
| V44 DEP | Alembic 成为生产唯一建表路径；探针/指标/结构化日志（脱敏）；备份恢复演练脚本 |
| V45 MOB | 响应式 + 底部 Tab + PWA（API 不缓存）；拍照取证与对象存储抽象 |
| V46 GRW | 优惠券/邀请/活动/新人任务/供需健康度，补贴全部纳入资金四不变量 |
| V47 SEC | 账号+IP 双维度限流、全局写兜底、失败自动封禁、TLS 与安全响应头 |

**剩下的都不是代码问题**：HTTPS 证书与域名、供应商签约与密钥、
法律与合规意见、应用商店开发者账号。
