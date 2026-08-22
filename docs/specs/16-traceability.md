# 16 · Spec → 实现 → 测试 追溯矩阵

> 状态：MVP + V1~V42 全批次完成（2026-08-22）。
> 后端 268 tests + 前端 29 tests 全绿。真实 LLM 分解已接入（有 Key 即用，缺省降级）。
> 剩余项均依赖外部供应商/云服务，见文末。

## 已实现（V48 批次：AI 编排闭环——从「数状态」到「看成果」）

> 模块 spec：[24-ai-orchestration.md](24-ai-orchestration.md)（已按代码检视结论重写）

本批次的四项修改都来自对 `orchestrator/service.py` 的逐行复查，
每一项对应一个让循环**闭不上**的具体缺陷：

| Spec 功能点 | 检视发现的缺陷 → 实现 | 测试 |
|---|---|---|
| **AIO-024/025/026 预算语义拆分（先修地基）** | `_dispatch_step` 在**发布任务时**就 `spent_cents += budget` 且流单后**从不退还**——字段注释写「已承诺」，行为却是「累计尝试」。两个语义混在一起的后果是取消的任务永久占着额度，首轮全部流单后 agent 就被一堆**已经不存在的占用**饿死。拆成 `committed_cents`（占用，取消即释放）与 `spent_cents`（实付，完成放款才计）。护栏改为 `spent + committed + 本步 <= cap`——**已付出去的钱不可逆，必须占额度**，否则「完成→评审不达标→重发」会让实际支出翻倍 | `test_orchestrator.py::test_cancelled_step_releases_budget_and_remedy_dispatches`（取消后能继续）、`::test_real_overspend_still_blocks`（真超支仍挂起） |
| **AIO-001/002/003 验收要点显式化** | `acceptance_criteria` 字段**存了但从不使用**，执行者不知道怎样算做完 → 规划为每步产出验收要点，写入任务描述并随合约条款留痕；模板引擎路径同样有要点，不依赖 Key | `test_orchestrator_review.py::test_acceptance_criteria_reach_the_worker` |
| **AIO-010/011/013 成果评审网关** | `evaluate()` 只数 `task.status == "completed"`——交一句「做完了」和交合格产出**没有区别** → `ReviewGateway` 抽象；`RuleReview` **基于可观测事实真打分**（留痕条数、图片凭证、打卡、交付说明、驳回次数），不是占位符；`ModelReview` 走 JSON Schema 强约束，异常降级；`StepReview` 留痕（模型、提示词版本、脱敏输入摘要、耗时） | 同上（`test_rule_review_distinguishes_evidence_quality` 证明有凭证的交付得分更高、`test_review_is_recorded_with_provenance`、`test_model_review_falls_back_on_bad_output`） |
| **AIO-012 模型永远不能单独动钱（第一性约束）** | `pass` 只作建议，放款仍由发布方确认；`revise`/`fail` 生成整改要点与人工复核，**零资金动作**。模型会错，而资金操作不可逆——AI 只做「谁该看一眼」的分诊 | 同上（`test_review_verdict_never_moves_money`：判 fail 时双方钱包与合约状态逐字段不变） |
| **AIO-020/047 质量闸门** | 达标条件从「全部完成」改为「全部完成**且**均分过线」，低分步转整改而非直接算完成；新增 `quality_pct` | 同上（`test_low_quality_does_not_count_as_success`、`test_quality_pct_reported`） |
| **AIO-021 修复步带整改要点** | `_make_remedy_steps` 是**同规格重发**（`args=dict(s.args)`）——同样的标题、预算、技能要求再发一次，凭什么这次会成功 → 把上一轮 `missing` 写进任务描述；连续两轮不达标则**上浮预算重新招募** | 同上（`test_remedy_carries_fixup_notes`、`test_repeated_failure_boosts_budget`） |
| **AIO-022 修复步幂等改用外键** | 原先靠标题字符串匹配 `title == f"[修复] {s.title}"`，脆且多轮后标题变成 `[修复] [修复] [修复] X` → 改用 `parent_step_id`，标题保持稳定，轮次由 `attempt` 表达 | 同上（`test_remedy_is_idempotent_by_parent_fk`） |
| **AIO-023/049 迭代时间线** | `MissionEvent` 记录每轮「做了什么 / 现在怎样 / 下一步」——**agent 必须可解释，否则没人敢授权它自动花钱** | 同上（`test_timeline_is_human_readable`） |
| **AIO-034/043 模型调用配额** | Mission 级上限，达上限降级规则评审，不静默烧 API 账单 | 同上（`test_model_call_quota_degrades_to_rule`） |
| **AIO-033/044 送模型脱敏** | 证据只取结构化事实、不取聊天记录；留痕摘要复用日志同一套 `redact` | 同上 |
| **闭环验收** | 「首轮全部流单 → 整改 → 真正 succeeded」——此前会因预算被虚耗卡在 `blocked` | `test_full_loop_recovers_from_first_round_failure` |
| SDK 同步：`committed_cents`/`quality_pct`/`timeline`/`stepReviews` | `packages/core/src/{client,types}.ts` | web 构建通过 |

## 已实现（V47 批次：抗攻击硬化——从「按账号限流」到「换号也挡得住」）

> 新增模块 spec：[23-network-security.md](23-network-security.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| SEC-011 **客户端 IP 解析（本批次最关键的一小段代码）**：常见错误是取 `X-Forwarded-For` 第一个 IP——那是客户端可伪造的，攻击者每次带一个不同的假 IP 就能让按 IP 的限流与封禁彻底失效。改为只信任反代注入的**最后一跳**（`TRUSTED_PROXY_HOPS`），XFF 比预期短则退回 socket 对端 | `core/clientip.py` | `tests/test_security_hardening.py`（伪造 XFF 绕不过；取右侧跳不取左侧） |
| SEC-011 **账号 + IP 双维度限流**：原实现只按手机号限，攻击者每次换号计数器永远是 1，批量注册完全不受影响。所有认证类端点（注册/登录/短信码/改密/换绑/重置）改走 `guard()`，任一维度超限即拒 | `core/guard.py::guard`、`account/router.py` | 同上（换号不换 IP 被拦；同号高频仍被拦） |
| SEC-012 **全局写限流兜底**：此前限流是「在每个敏感端点手写一行 check()」，只有 7 处，新端点默认裸奔。改为中间件按 IP 限所有写操作——**新端点默认受保护**；读请求与探针不受影响 | `core/guard.py::WriteRateLimitMiddleware` | 同上（未单独加限流的端点也被兜住；GET 不误杀） |
| SEC-020/023 认证失败自动封禁：窗口内失败达阈值临时封禁 IP，封禁期内正确密码也拒；**成功登录清零计数**（偶发手滑不该累积成封禁）；管理端安全看板与**人工解封**（误封公司出口 IP 会挡住一整栋楼） | `core/guard.py::{note_auth_failure,ban_remaining,unban}`、`admin/router.py` | 同上 |
| SEC-002 安全响应头：nosniff / frame DENY / CSP（`frame-ancestors 'none'`）/ Referrer-Policy / Permissions-Policy；**HSTS 只在 prod 下发**（开发环境发了会把本地浏览器锁死在 HTTPS） | `core/headers.py` | 同上 |
| SEC-003 生产关闭 API 文档：`/docs`、`/redoc`、`/openapi.json` 在 `ENV=prod` 且未显式开启时不挂载——把全部端点与模型结构送给攻击者是没必要的慷慨 | `main.py` | 同上（dev 下仍可访问） |
| SEC-033 上传响应加固：读取端点补 `nosniff` + `Content-Disposition` + `CSP: default-src 'none'; sandbox`，即便有人构造出「既是合法图片又是合法脚本」的文件也无法在本源执行 | `files/router.py` | 同上 |
| SEC-001/004/010/013 生产 Nginx：强制 TLS（≥1.2、HSTS、OCSP stapling）、三档 IP 令牌桶（普通/写/认证，认证类最严）、资金类端点单独收紧、`limit_conn` 与超时防慢速攻击、`/metrics` `/jobz` 仅内网、SW 不缓存 | `deploy/{nginx.prod.conf,proxy_common.conf,docker-compose.prod.yml}` | 配置随栈交付；应用侧行为由上述用例覆盖 |
| SEC-030/053 生产自检扩展：CORS 为 `*`、暴露 API 文档、`TRUSTED_PROXY_HOPS` 未设（反代后取不到真实 IP，限流全失效）→ **拒绝启动**；`up.sh` 增加缺 TLS 证书的拦截 | `vendors/registry.py::startup_check`、`deploy/up.sh` | 同上 |

## 已实现（V46 批次：增长、运营与市场——把运营手册落成功能）

> 新增模块 spec：[22-growth-ops.md](22-growth-ops.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| GRW-001/005 券模板：定额/比例二选一，**比例券必须带封顶**（没封顶的比例券遇大额单会烧光预算）；发放/核销/成本报表；可暂停发放且不追溯作废已领权益 | `growth/{models,service}.py`、`growth/router.py::{create_coupon,coupon_report,pause_coupon}` | `tests/test_growth.py` |
| GRW-002 领取与核销：一人限领、一单一券（`UniqueConstraint(contract_id)` DB 层兜底）、满减门槛、类目限制、有效期；**合约取消 → 券退回可再用且补贴款退回平台** | `growth/service.py::{claim,redeem,release_on_cancel}` + `contract/service.py::_release_coupon` | 同上 |
| GRW-003 **补贴资金口径（本批次最关键）**：补贴不凭空产生，一律「平台账户 → 用户可用余额」走既有账本（`subsidy_out/in` 科目）；平台余额不足即核销失败绝不透支；新增补贴池注资 `platform_topup`（冷启动时平台还没佣金收入）。**同步扩展资金第 4 不变量**为「平台可用 == Σ佣金 + Σ注资 - Σ结算 + Σ补贴净额 + Σ调整净额」——不改口径的话每发一张券日终对账就误报一次 | `wallet/service.py::{transfer(kind=),fund_platform}`、`risk/service.py::reconcile` | 同上（每个用例结尾都断言四不变量成立） |
| GRW-004 反刷：未实名不得领券（否则批量注册即可薅）、限量与限领 | `growth/service.py::claim` | 同上 |
| GRW-010~014 邀请裂变：**完成首单才发现金奖励**（注册即奖是刷号的邀请函）；一人一次（`invitee_id` 唯一）；反作弊（同收款账户 / 同实名 / 互为邀请 → blocked 转人工不发钱）；邀请战绩页 | `growth/service.py::{grant_referral,_fraud_reason,referral_stats}`、`analytics/service.py` | 同上 |
| GRW-060 合规红线：**奖励仅一级**，邀请人的邀请人不获任何奖励（代码层面就不去追溯上级）；战绩接口显式返回 `levels: 1` | 同上 | 同上（A→B→C 三层，C 成单时 A 得 0） |
| GRW-020 新人任务清单（完善资料/实名/技能/首发/首报/首单）与进度 | `growth/service.py::newcomer_progress` | 同上 |
| GRW-022/023 供需健康度：按城市×类目统计发布数/接单人数/成单率，标出 `supply`（有需求没人接）与 `demand`（有人没活干）两类缺口；发布页供给不足提示 | `growth/service.py::{market_health,supply_hint_text}` | 同上 |
| GRW-030 活动预算硬顶：`spent_cents` 随核销累加，超顶自动停投——没有硬顶的补贴活动是运营事故的标准形态 | `growth/models.py::Campaign` + `service._check_campaign` | 同上（预算 30 元、券 20 元 → 第二张即被拒） |
| GRW-052 北极星指标：成单数与成单 GMV；次级看新用户首单转化与纠纷率 | `growth/service.py::north_star` | 同上 |
| Web 优惠页（新人任务进度 / 领券 / 我的券 / 邀请战绩，含「仅一级」规则说明）+ SDK 同步 | `web/src/pages/Rewards.tsx`、`packages/core/src/{client,types}.ts` | web 构建通过 |

## 已实现（V45 批次：移动端与 PWA——让手机用户真的能用）

> 新增模块 spec：[21-mobile-pwa.md](21-mobile-pwa.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| MOB-001/003/004 响应式（≤640 手机 / ≤1024 平板 / >1024 桌面）：列表转竖排卡片、表单与按钮满宽、表格横向滚动（**绝不让 body 出横向滚动条**）、触控目标 ≥44px、输入框 ≥16px（防 iOS 聚焦缩放）、`viewport-fit=cover` + `env(safe-area-inset-*)` 适配刘海与手势条 | `web/src/styles.css`、`web/index.html` | `web/src/mobile.test.tsx` |
| MOB-002 底部 Tab 导航（广场/发布/消息/我的），手机显示桌面隐藏；消息 Tab 未读红点复用 IM-010 全局未读接口，未读数拿不到不影响导航可用 | `web/src/TabBar.tsx`、`App.tsx` | 同上（四入口渲染、红点数字） |
| MOB-010 `manifest.webmanifest`：standalone、主题色、**maskable 图标**（少了它安卓自适应图标会被裁掉一圈）、快捷方式；apple-touch-icon 与 iOS meta | `web/public/{manifest.webmanifest,icon.svg,icon-maskable.svg}` | 同上 |
| MOB-011/012 Service Worker：外壳预缓存 + stale-while-revalidate；**`/api/` 一律不缓存不兜底**——任务状态/合约状态/钱包余额读到陈旧值会让用户基于错误信息决定付钱，宁可报错不可撒谎；断网落离线页 | `web/public/{sw.js,offline.html}` | 同上（预缓存清单不含 API、离线页在册） |
| MOB-013/014 新版本提示（`SKIP_WAITING` + 刷新，避免旧外壳打新接口）；安装引导可关闭且**记住选择**，隐私模式下 localStorage 抛异常也安静降级 | `web/src/pwa.ts`、`App.tsx` | 同上 |
| MOB-020 定位「附近任务」（既有能力，拒绝授权时降级为全部任务） | `web/src/pages/Square.tsx` | 既有用例 |
| MOB-021 拍照/相册取证：客户端压缩（长边 1280 / JPEG 0.8）后上传——**压缩是必需而非优化**，手机直出 3~8MB 既超服务端上限也让弱网执行者传不上去，而凭证传不上去等于没有证据；进度留痕可附图，纠纷时作为证据 | `web/src/PhotoPicker.tsx`、`pages/TaskDetail.tsx`、`task/{models,router}.py` | `server/tests/test_uploads.py` |
| VND-031 存储供应商抽象 + 上传端点：类型白名单 + 大小上限 + **魔数校验**（只信 Content-Type 等于让上传方自证清白）+ 内容寻址去重 + 登录与限流（否则等于开了免费图床）+ 读取端点禁路径穿越；进度图只接受本平台相对路径（外链不可信且泄露用户 IP） | `app/vendors/storage.py`、`app/modules/files/router.py` | 同上（12 例，多数是拒绝路径） |
| MOB-031/032/033 Expo 配置：bundle id、scheme `taskplat`、Universal Link / App Links、相机与相册权限的中文用途说明；提审清单列出账号注销/举报/拉黑/协议四个**审核必查项**及其后端接口 | `app/app.json`、`app/STORE_CHECKLIST.md` | — （发版需开发者账号） |
| SDK 同步：`uploadImage`、`addProgress` 支持 images | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V44 批次：生产部署、迁移与可观测）

> 新增模块 spec：[20-deployment.md](20-deployment.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| DEP-001/002/003 生产栈 compose（Postgres + Redis + 可扩副本 api + **固定单副本 worker** + Nginx）；`deploy/.env.example` 标注全部「必须修改」项；`deploy/up.sh` **先自检再启动**（弱密钥/默认 token/CORS 为 `*`/四个 mock 供应商全部拦下）；镜像非 root 运行 | `deploy/{docker-compose.prod.yml,.env.example,up.sh}`、`server/Dockerfile` | 自检逻辑与 `startup_check` 同源，见 VND-042 用例 |
| DEP-010/011/012 探针：`/healthz` 存活（不查依赖）、`/readyz` 就绪（DB + 限流后端 + **迁移版本**，不满足 503）、`/version` 构建信息 | `main.py` | `tests/test_deployment.py` |
| DEP-020/021/022 **Alembic 成为生产唯一建表路径**：`init_db` 在 `ENV=prod` 下直接拒绝 `create_all`（多副本并发建表会互相踩）；迁移由一次性 `migrate` 容器执行；库版本与代码 head 不一致则 `/readyz` 不就绪 | `migrations/`、`alembic.ini`、`core/db.py::{init_db,migration_status}` | 同上 + **迁移与模型不漂移**用例（两条建表路径的表/列集合必须一致）+ CI `alembic check` |
| DEP-030/031/032 备份与恢复：`backup.sh`（pg_dump + **存证链 head 单独快照**——只备份库的话，被篡改后再备份就没有独立证据了）；`restore.sh` 导入后**强制跑资金四不变量 + 存证链校验**，不过就明确报失败，不给「大概好了」的错觉 | `deploy/{backup.sh,restore.sh}` | 校验逻辑复用既有 `reconcile` / `verify_chain` 用例 |
| DEP-040/041 结构化 JSON 日志 + `request_id` 贯穿（入站生成或**透传**，随响应头返回）；日志**脱敏**手机号/证件号/银行卡——出事时不能因为日志本身再泄一次 | `core/observability.py` | 同上（三类敏感串各一例、formatter 带 request_id） |
| DEP-042 `/metrics` Prometheus：请求量/延迟直方图 + **资金关键计数**（托管中、待提现、未结纠纷）；用路由模板而非真实路径，避免任务 id 打爆指标基数；与 cron 同一把令牌保护，不对公网裸奔 | 同上 + `main.py` | 同上（含基数用例、鉴权用例） |
| DEP-050/051 worker 驱动全部 job（周期按「延迟一个周期的业务代价」定）；`JobLock.last_success_at` 记录 job 健康，`/jobz` 暴露——job「静默不跑」比报错更危险 | `scripts/cron.py`、`core/locks.py::{_note_job_result,job_health}` | 同上 + **反查路由表**用例：新增 job 端点却忘了排期直接测试失败 |
| DEP-060 冒烟脚本：对已启动实例跑真实 HTTP 主闭环（注册→实名→充值→发布→报名→选人→双签→托管→交付→验收→核对分账→**托管清零**），CI 中执行 | `scripts/smoke.py`、`.github/workflows/ci.yml` | CI 作业 `boot-smoke` |

## 已实现（V43 批次：外部供应商接入抽象层——把「模拟」换成「可换」）

> 新增模块 spec：[19-vendor-integration.md](19-vendor-integration.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| VND-001/041/042 注册表 `get_provider(kind)` + 后台健康面板 `/admin/vendors`（当前实现/是否模拟/熔断/近 24h 成功率）+ **生产启动自检**：`PLATFORM_ENV=prod` 下 P0 能力仍是模拟实现、弱密钥、SQLite 一律拒绝启动（把上线前必须完成的对接变成硬拦截，而不是没人看的日志） | `app/vendors/registry.py`、`admin/router.py`、`main.py` | `tests/test_vendor_integration.py` |
| VND-002 错误收敛 `VendorError(code, message, retryable)` → 502（可重试）/ 400（明确拒绝），**不泄露供应商原始报文** | `vendors/base.py` | 同上 |
| VND-003 调用留痕 `VendorCall`（kind/provider/operation/幂等键/**脱敏摘要**/状态/耗时/外部单号）——对账与客诉排查的唯一依据 | `vendors/models.py::VendorCall` | 同上（手机号与验证码不进摘要） |
| VND-004 幂等：会花钱/会发送的操作带幂等键，重复调用回放首次结果，**不再打供应商** | `vendors/base.py::call` | 同上（三次调用只打一次） |
| VND-005 熔断：连续失败达阈值进入冷却，冷却期快速失败 | 同上 | 同上 |
| VND-010/011 **充值改两阶段**（修复真实支付下的致命结构）：此前「调用即加余额」意味着接真实通道后用户下单不付款也能拿到钱 → `PaymentOrder` pending → 供应商确认 → 才入账。模拟通道即时确认，开发体验与既有测试不变 | `vendors/{payment,payment_service}.py`、`wallet/router.py` | 同上（订单落库、外部单号可对账） |
| VND-012 回调验签 + 回调幂等 + 金额校验：伪造签名一律拒绝（不看金额不查订单）；同一订单重放只入账一次；回调金额与订单不符标记 `mismatch` 挂起人工，且**标记落在独立事务**里（否则会跟着 400 一起回滚，运营再也看不到） | `vendors/payment_service.py::{handle_callback,confirm_topup,_flag_mismatch}` | 同上（三条独立用例） |
| VND-013 提现打款走 `create_payout` 并落 `payout_ref`；供应商失败整体回滚——宁可提现失败重来，也不能「账扣了钱没打出去」 | `wallet/service.py::_send_payout` | 既有提现用例 |
| VND-020/021 短信：`/auth/send-code` 端点（限流同级，防被当短信轰炸机）；验证码服务端生成、**只存哈希**（手机号加盐）、有效期 10 分钟、尝试次数上限 5 次；模拟通道回显 `dev_code`，真实通道永不回显 | `vendors/{sms,sms_service}.py`、`account/router.py` | 同上（哈希不含明文、限流生效） |
| VND-022/023 实名走 `KycProvider`；**证件号不落明文**，只存不可逆摘要 + 掩码串；同一证件号不得绑定多账号（一人多号是补贴套利第一步） | `vendors/kyc.py`、`account/{models,router}.py` | 同上（摘要脱敏、重复证件号 409） |
| VND-030 内容机审改走 `ModerationProvider`（本地词表为缺省实现，行为不变）；本地实现看不了图/视频时明确返回 `review` 转人工，而不是假装通过 | `vendors/moderation.py`、`task/service.py::machine_review` | 同上（违禁词仍被拦） |
| SDK 同步：`sendSmsCode`、`topup` 返回两阶段结果类型 | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V42 批次：并发与生产化硬化——从「单进程正确」到「多副本正确」）

> 新增模块 spec：[18-concurrency.md](18-concurrency.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CONC-001/002 Postgres 支持与连接池参数化（`pool_size`/`max_overflow`/`pool_recycle`/`pool_pre_ping`），SQLite 分支自动跳过池参数；切库只改 `PLATFORM_DATABASE_URL`，业务代码零改动 | `core/db.py::_make_engine` + `core/config.py` | 全量既有测试（同一套代码跑 SQLite） |
| CONC-003 SQLite WAL + `busy_timeout` + 外键约束 PRAGMA：本地并发写不再直接报 `database is locked` | `core/db.py` connect 事件 | 并发用例（多线程打同一端点不报锁错） |
| CONC-004 方言探测 `supports_row_lock()`：Postgres/MySQL 启用真实行锁，SQLite 自动降级 | `core/db.py` | 同上 |
| CONC-010/011/012 **资金写路径行锁**（最关键缺口）：多副本下两进程可同时读到 `funded` 各自放款 → `lock_contract`/`lock_wallets` 取 `SELECT ... FOR UPDATE`；多钱包按 `user_id` **升序**加锁杜绝死锁；接入 fund/release/release_milestone/cancel/execute_verdict/accept_change/withdraw/decide_withdraw/settle_platform/transfer | `core/locks.py` + `contract/service.py` + `wallet/service.py` | `tests/test_conc_hardening.py`（并发验收只放款一次、并发托管只扣一次、并发提现不透支） |
| CONC-013 **乐观锁兜底**：`Contract.lock_version` / `WalletAccount.lock_version` 走 SQLAlchemy `version_id_col`，并发 UPDATE 第二个提交 `StaleDataError`；API 边界统一翻译为 `409 concurrent_modification` 而非 500。与业务版本号 `Contract.version`（条款版本，对外展示）**刻意分离** | `contract/models.py`、`wallet/models.py`、`main.py` 异常处理器 | 同上（丢失更新被拒、409 语义） |
| CONC-020/021/022 分布式限流：`RateLimiter` 协议 + `MemoryRateLimiter`（现状）+ `RedisRateLimiter`（`INCR`+`EXPIRE` 原子窗口）；配 `PLATFORM_REDIS_URL` 自动切换；**Redis 故障连续达阈值即冷却降级为内存**并在探针中可见——限流是防滥用手段，不该拖垮登录 | `core/ratelimit.py` | 同上（降级后仍真限流，不是无脑放行） |
| CONC-040/041 定时任务单实例锁：`JobLock` 表（job_name 主键=天然唯一约束）+ `job_slot()` FastAPI 依赖，**执行完即释放**（串行调用永远可用），崩溃时靠 `expires_at` TTL 抢占，不会永久停摆；接入全部 8 个 cron 端点 | `core/models_infra.py`、`core/locks.py`、各模块 `jobs/*` 路由 | 同上（持有/释放/TTL 抢占/端点并发最多一个 200） |
| DEP-010/011/012 健康探针：`/healthz` 存活（不查依赖）、`/readyz` 就绪（DB 可读写 + 限流后端状态，不满足 503） | `main.py` | 同上 |

## 已实现（V41 批次：编排循环 Agent Harness——发任务给人 = 工具调用）

> 新增模块 spec：[17-orchestrator.md](17-orchestrator.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| ORC-001/002 Mission/MissionStep 与一次 tick：plan（复用 AI 分解网关）→ observe（读任务真实状态为 observation）→ evaluate（完成度）→ dispatch（真实发布任务 = 调用「人」这个工具）→ 停机判定 | `orchestrator/{models,service,router}.py` | `tests/test_orchestrator.py` |
| ORC-003 编排状态机白名单（planning/running/blocked/succeeded/failed/cancelled），非法流转 409 | `service.transition` + `MISSION_TRANSITIONS` | 同上（结束后不可再 tick） |
| ORC-004 护栏（第一性要求）：预算硬上限超出即 `blocked` 挂起、规划预留金 `ORC_PLAN_RESERVE_BPS`（默认 30%）留给重试、迭代上限触顶 `failed`、人工停机并下架未成交挂单、所有权隔离、心跳 job 需令牌 | 同上 + `config.ORC_PLAN_RESERVE_BPS` | 同上（预算越界挂起、迭代上限放弃、cancel 下架、403 隔离） |
| ORC-005 失败步 → 自动生成修复步再分发（幂等去重）；原步标记 `superseded` 不计入分母，否则一次失败会让编排永远无法 100% | `service._make_remedy_steps` + `evaluate` | 同上（修复步完成后 succeeded） |
| SDK 同步：createMission/myMissions/getMission/tickMission/cancelMission + Mission 类型 | `packages/core/src/{client,types}.ts` | web 构建通过 |

## 已实现（V40 批次：纠纷答辩举证——两造兼听）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| DSP-005 答辩/举证（**修复程序正义硬伤**）：开纠纷仅有发起方 reason + 系统快照，被诉方全程无发声渠道，仲裁员据一面之词即裁决分钱 → 新增 `DisputeStatement` 陈述表（只增）、`POST/GET /disputes/{id}/statements`（当事人可附证据，对方收通知，结案后禁言，仅当事人+管理员可见） | `dispute/models.py::DisputeStatement` + `dispute/router.py` | `tests/test_dispute_statements.py` |
| DSP-005 两造兼听守卫：被诉方未答辩且答辩期（`DISPUTE_RESPONSE_HOURS`，默认 48h）未过 → 裁决被拒（`response_window_open`）；逾期未答辩可缺席裁决，防一方不出面拖死流程 | `dispute/router.py::_respondent_had_voice` + `issue_verdict` | 同上（含缺席裁决路径）；7 个既有裁决测试同步补答辩前置 |

## 已实现（V39 批次：IM 已读位点——未读数与红点）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| IM-010 聊天已读位点（**补聊天标配缺口**）：IM 此前零已读状态，用户无从知道哪个会话有新消息 → 新增 `ConversationRead` 已读位点表；会话列表附 `unread_count` 与最后一条消息预览、有未读优先排序；`/conversations/unread-count` 全局红点；`/conversations/{id}/read` 标记已读（复用参与者鉴权，自己发的消息不计未读） | `im/models.py::ConversationRead` + `im/router.py` | `tests/test_im_unread.py` |
| SDK 同步：conversations 富返回 / imUnreadCount / markConversationRead | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V38 批次：被封发布者挂单下架）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| OPS-013 续：封禁下架未成交挂单（**补 V36 遗漏面**）：V36 处理了在途合约，但被封方**已发布未成交**的任务仍留在广场，工人报名后永远等不到选人 → 封禁时自动取消其 draft/published 任务、关闭并通知全部待处理报名者；影响面预览与审计 detail 含挂单数 | `admin/router.py::_ban_impact/ban_user` | `tests/test_banned_creator_listings.py` |
| OPS-013 防御性过滤：广场排除被封/已注销发布者的任务；报名时校验发布方状态（`creator_unavailable`） | `task/router.py::list_tasks/apply` | 同上（含历史遗留数据场景） |

## 已实现（V37 批次：用户口碑页——评价消费端）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CRED-006 用户收到的评价（**修复信任断链**）：双盲评价的评语/标签此前「只写不读」——公开主页仅 rating_avg 聚合，选人时看不到「为什么是这个分」→ 新增 `/users/{id}/reviews`：收到的评价列表 + 标签计数聚合 + 分页；**严格复用双盲揭晓规则**（盲窗内评价一律不返回），杜绝从用户维度旁路偷看 | `task/router.py::user_reviews` | `tests/test_user_reviews.py`（含盲窗不泄露、窗口到期单边揭晓、标签聚合、分页） |
| SDK 同步：userReviews | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V36 批次：封禁影响面——爆炸半径可见 + 对手方自救）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| OPS-013 封禁影响面（**修复盲拍开关**）：封禁原为静默 flag 翻转，管理员看不到在途合约/涉险托管，对手方也无人告知——被封方无法交付/验收，对方托管资金被无限期困住 → 新增 `/admin/users/{id}/ban-impact` 无副作用预览（在途合约、涉险托管、钱包三态）；封禁响应带影响面并写入审计 detail；**自动通知全部在途对手方**提示取消或发起纠纷 | `admin/router.py::_ban_impact/ban_impact/ban_user` | `tests/test_ban_impact.py`（含对手方取消后托管归零 + 守恒断言） |
| SDK 同步：banImpact | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V35 批次：管理员操作审计——合规留痕）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| OPS-012 管理员操作审计（**补合规缺口**）：~20 个高权限端点原无任何操作留痕，无法回答「哪个管理员何时对谁封禁/裁决/放款」→ 新增 `AdminAudit` 只增审计表 + `record_audit` 助手，接入封禁/解封/纠纷裁决/申诉复核/平台结算/大额提现审批；`/admin/audit-log` 可按动作筛选、分页，管理员限定 | `admin/models.py::AdminAudit` + `admin/router.py::record_audit/audit_log` + 各高权限端点 | `tests/test_admin_audit.py` |
| SDK 同步：adminAuditLog | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V34 批次：验收驳回上限——防无限返工欠薪）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-033 验收驳回上限（**修复工人保护缺口**）：reject_count 原只记录不约束，发布方可无限「驳回返工」变相欠薪 → 达上限（默认 3 次）后禁止再单方驳回，须验收或走纠纷仲裁；每次驳回通知执行者原因与剩余次数 | `task/router.py::reject_delivery` + `MAX_REJECT_ROUNDS` | `tests/test_reject_limit.py` |

## 已实现（V33 批次：任务详情视角上下文）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-017 详情「我与此任务的关系」（**修复体验缺口**）：worker 报名后详情仍显示报名按钮、点了才 409 → GET /tasks/{id} 附 my_application_status / bookmarked；发布者附 applications_count | `task/router.py::get_task` | `tests/test_task_detail_context.py` |
| SDK 同步：Task 类型补视角字段 | `packages/core/src/types.ts` | web 构建通过 |

## 已实现（V32 批次：通知中心——未读徽章 + 全部已读 + 分页）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| NTF-005 未读徽章计数 + 一键全部已读（应用红点标准能力，此前缺失）：`/notifications/unread-count`、`/notifications/read-all`；通知列表补 offset 分页 | `notification/router.py` | `tests/test_notification_center.py` |
| SDK 同步：unreadCount/markAllRead | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V31 批次：我的报名/投标）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| MATCH-010 我的报名（**补配套缺口**）：`/tasks/mine?role=working` 只含已成交单，等待选人的报名无处可查 → 新增 `/users/me/applications`：列出本人投出的报名及所报任务当前状态，可按报名状态筛选、offset 分页、用户隔离 | `task/router.py::my_applications` | `tests/test_my_applications.py` |
| SDK 同步：myApplications | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V30 批次：我的任务中心）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-016 我的任务中心（**补能力缺口**）：广场只展示 published+public，用户无法列出自己的草稿/执行中/已完成任务、也看不到自己执行的单 → 新增 `/tasks/mine`：posted（我发布）/working（我执行）/all，可按状态筛选，offset 分页，用户隔离 | `task/router.py::my_tasks` | `tests/test_my_tasks.py` |
| SDK 同步：myTasks | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V29 批次：任务广场分页）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-003 广场分页（**补能力缺口**）：原只有 limit（≤100）+ 硬性 500 上限、无 offset，超窗旧任务永远翻不到 → 补 DB 层 offset/limit 分页（非地理路径直接 DB 分页，不再拉全表切片）；地理检索按距离排序后分页 | `task/router.py::list_tasks` | `tests/test_task_pagination.py`（页间不重不漏、limit 上限、offset 越界、地理分页） |

## 已实现（V28 批次：密码登录防暴力破解）

| Spec 安全项 | 实现 | 测试 |
|---|---|---|
| ACC-002 密码登录限流（**修复真实漏洞**）：注册/短信登录早有限流，密码登录 `/auth/login` 却完全不限，可对已知手机号无限撞库 → 补同号 60s 内 5 次尝试上限，按手机号隔离 | `account/router.py::login` + `core/ratelimit` | `tests/test_login_ratelimit.py` |

## 已实现（V27 批次：幂等键请求指纹——修复串味/吞单）

| Spec 安全项 | 实现 | 测试 |
|---|---|---|
| 14.6/05.B 幂等键请求指纹（参照 Stripe，**修复两处真实缺陷**）：① 同 key 复用不同金额原返回旧结果（吞单）；② 同 key 跨操作（topup vs withdraw）原按 (user,key) 命中会串味 → 记录 scope+参数指纹，指纹不符 409 `idempotency_key_conflict`；完全相同请求仍正常重放 | `core/idempotency.py::replay_or_run` + `fingerprint` 列 + wallet 路由传参 | `tests/test_idempotency_fingerprint.py` |

## 已实现（V26 批次：内部定时任务鉴权——修复未授权访问漏洞）

| Spec 安全项 | 实现 | 测试 |
|---|---|---|
| OPS-011 cron 端点鉴权（**修复真实漏洞**）：7 个 job（自动放款/合约作废/任务下架/纠纷升级/评分结算/位置清理/逾期预警）原为无鉴权公开接口，任何人可触发改动资金与状态；改为强制携带共享密钥 `X-Job-Token`（生产改强随机） | `core/deps.py::require_job_auth` + `settings.JOB_TOKEN` + 全部 job 端点 | `tests/test_job_auth.py`（穷举 7 端点：无 token/错 token 403，正确放行；用户身份不能绕过） |

## 已实现（V25 批次：过期任务自动下架）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-015 过期任务自动下架（**补执行缺口**：deadline 发布时校验、发布后从不执行 → 僵尸挂单永占广场）：published 且过截止时间未成交 → 转 cancelled，通知发布者与全部待处理报名者；已成交/无 deadline 不受影响；幂等 | `task/router.py::run_expire_tasks` (`/tasks/jobs/expire-tasks`) | `tests/test_task_expiry.py` |
| SDK 同步：expireTasks | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V24 批次：收款账户绑定——提现前置）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| PAY-005 收款账户绑定（**补齐能力缺口**：原提现无收款目标，凭空到账）：绑卡/支付宝、账号脱敏展示、可改绑 | `wallet/router.py::bind/get_payout_account` + `PayoutAccount` 模型 | `tests/test_payout_account.py` |
| PAY-005 提现前置守卫：未绑收款账户不可提现（`no_payout_account`） | `wallet/service.py::withdraw` | 同上 + test_wallet |
| PAY-005 收款人实名一致校验（防代提/洗钱）：holder_name 须等于实名 | `wallet/router.py::bind_payout_account` | 同上 |
| SDK 同步：getPayoutAccount/bindPayoutAccount | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V23 批次：平台佣金收入实收口径 + 结算 + 对账不变量）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| SC-009 佣金收入口径修复（**真实缺陷**）：metrics.fee_income 原按 Σ(released×费率) 估算，漏计纠纷/取消场景佣金且有逐笔取整漂移；改为以平台账户实收（fee 流水）为唯一事实来源 | `wallet/service.py::platform_finance` + `admin/metrics` | `tests/test_platform_finance.py` |
| OPS-010 平台收入总览 + 结算：累计佣金/已结算/可结算余额；结算划出（模拟对公），超额拒绝 | `admin/router.py::platform_finance/settle` + `wallet::settle_platform` | 同上 |
| PAY-006 对账新增第 4 条不变量：平台账户可用 == Σ佣金 - Σ平台结算；全局守恒出账口径纳入平台结算 | `risk/service.py::reconcile` | 同上（结算后守恒仍成立） |
| SDK 同步：platformFinance/settlePlatform | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V22 批次：任务编辑防调包 + 截止时间校验）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-014 任务编辑（**补齐能力缺口**：原发布后完全不可编辑）+ 防调包保护：draft 自由改；已发布且有人报名后实质条款受保护（预算只上不下、技能锁定），非实质字段始终可改，实质变更通知报名者 | `task/router.py::edit_task` | `tests/test_task_edit.py` |
| TASK-014 截止时间校验：发布时 deadline 必须晚于当前（防过期任务上架） | `task/service.py::validate_publishable` | 同上 |
| SDK 同步：editTask | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V21 批次：批判性扫描——真双盲评分/变更单文书/换绑手机/平台公告）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CRED-002 真双盲评分（**修复旁道泄露**）：原评分提交即更新对方 rating_avg/信用分，对方看主页分数变化可反推星级并窗口内报复；改为评分聚合延迟到公开时点（双评完/窗口到期）结算，加 `settle-reviews` 兜底 job | `task/router.py::create_review/list_reviews/_settle_reviews` + `Review.rating_applied` | `tests/test_v21_critical.py` |
| SC-007 变更单条款附录（**修复文书矛盾**）：改价后 terms 仍是原金额，导出合约与实际不符；改为以带事由的变更附录追加，导出文书体现新金额 | `contract/service.py::accept_change` | 同上 |
| ACC-008 换绑手机：新号验证码 + 旧密码双重校验，新号查重，限流防刷 | `account/router.py::change_phone` | 同上 |
| OPS-009 平台公告广播：向全体/仅实名活跃用户群发站内通知，非管理员拒绝 | `admin/router.py::broadcast_announcement` | 同上 |
| SDK 同步：changePhone/broadcastAnnouncement | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V20 批次：批判性扫描——收藏/接单开关/新设备提醒/对账告警闭环）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-013 任务收藏（幂等添加/列表/移除） | `task/router.py` bookmark 路由 + `Bookmark` 模型 | `tests/test_v20_ops_features.py` |
| ACC-014 接单开关（业界「上线/下线」）：关闭后不进推荐、不可被邀约；主动报名不受限 | `User.accepting_orders` + 推荐召回过滤 + 邀约守卫 | 同上 |
| ACC-007 新设备登录提醒：陌生 UA 登录触发站内通知，已知设备静默 | `account/router.py::_issue_token` | 同上 |
| PAY-008 对账告警闭环：不变量校验失败自动开差错工单 + 通知全体管理员（原来只返回结果没人看） | `admin/router.py::run_reconcile` | 同上 |
| SDK 同步：bookmark/unbookmark/myBookmarks | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V19 批次：批判性扫描——提现风控 + 密码管理 + 报名撤回）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| PAY-007 提现风控（业界惯例）：单日限额硬拒（含待审计入）；大额冻结进人审队列，批准划出/驳回解冻；对账冻结口径扩展（保证金+待审提现） | `wallet/service.py::withdraw/decide_withdraw` + `WithdrawRequest` 模型 + 管理端路由 + `risk.reconcile` 口径 | `tests/test_withdraw_risk.py` |
| ACC-004 密码管理：改密验旧密码、忘记密码短信重置，均吊销全部旧会话（防盗号后旧 token 续命）+ 重置限流防爆破 | `account/router.py::change_password/reset_password` | `tests/test_password_and_apply_withdraw.py` |
| TASK-012 报名撤回：pending 可撤、撤后可重报；**修复：撤回的报名仍可被发布者成交（替人签约）**——成交守卫补 `application_closed` | `task/router.py::withdraw_application` + accept 守卫 | 同上 |
| SDK 同步：withdraw 富返回/withdrawRequests/decideWithdraw/changePassword/resetPassword/withdrawApplication | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V18 批次：纠纷 SLA + 申诉窗口，见提交记录）

## 已实现（V17 批次：双盲互评完整落地 + 并发接单上限）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CRED-002 双盲互评（Upwork 惯例）：修复路人泄露——盲窗内评价对第三方也隐藏（否则换号偷看即破防）；新增 14 天评价窗口，到期单方评价自动公开且不可补评（防看到差评后报复） | `task/router.py::list_reviews/create_review` + `REVIEW_WINDOW_DAYS` | `tests/test_blind_review.py` |
| TASK-011 执行者并发接单上限（零工平台惯例，防过度接单违约）：在途单达上限后报名/选人/接受邀约均拒；完成释放额度；上限以成交时点复核 | `task/service.py::check_executor_capacity` + 三个入口守卫 + `MAX_ACTIVE_TASKS` | `tests/test_executor_capacity.py` |

## 已实现（V16 批次：签署有效期 + App 闭环补齐 + 操作矩阵下沉 SDK）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| SC-012 签署有效期（业界 offer 有效期惯例）：成交后 N 天未双签自动作废，释放冻结保证金，防资金卡死 | `contract/router.py::run_expire_unsigned` + `SIGN_EXPIRE_DAYS` 配置 | `tests/test_contract_expiry.py`（含半签超期作废、新鲜/已托管不动、幂等、守恒） |
| 03/05 操作可见性矩阵单一事实来源（Web/App 共用防漂移） | `packages/core/src/actions.ts::taskActions` 纯函数 | `packages/core/src/actions.test.ts`（9 例：角色×状态全覆盖） |
| 13 App 端闭环补齐：报名列表+选人成交+双签+托管+驳回+纠纷+取消（原断档：App 单端走不完闭环） | `app/App.tsx` TaskDetailScreen 由 taskActions 驱动 + 合约卡片（金额/费率/保证金/签署进度） | 逻辑在 SDK 层测试；web 构建通过 |

## 已实现（V14 批次：多人任务预算守恒 + 自动验收边界）

| Spec 不变量 | 测试 | 说明 |
|---|---|---|
| TASK-007 名额拆分预算守恒 | `tests/test_multiperson_autoaccept.py` | 修复：整除余数原被静默丢弃（10000/3 每单蒸发 1 分）→ 余数并入末位名额，Σ名额 == 母任务预算 |
| TASK-007 多名额全周期资金守恒 | 同上 | 各名额分别成交放款，放款额/抽佣与名额预算逐分对应，reconcile 恒成立 |
| TASK-031 自动验收时间边界 | 同上 | 恰好越过 cutoff 的放款、差 1 小时的不动；唯一「无人点击也动钱」路径的守恒断言 |
| TASK-031 job 重跑幂等 | 同上 | 无新到期单时零动作、余额不变 |

## 已实现（V13 批次：分期×纠纷交叉路径守恒）

| Spec 资金不变量 | 测试 | 说明 |
|---|---|---|
| SC-004×DSP-007 部分放款后裁决只分剩余托管 | `tests/test_milestone_dispute_cross.py` | 首期已放款不可追回/不重复计算，裁决基数=剩余托管，钱包金额精确断言 |
| DSP-008 复核基数对外可见 | dispute `_dump` 补 `split_base_cents` | 修复：响应缺字段（申诉复核需展示裁决基数） |
| SC-008 冻结期一切放款被拒 | 同上测试 | 纠纷冻结中里程碑验收 `contract_frozen`、整体取消被拒，资金零变动 |
| DSP-004 和解分账守恒（含保证金） | 同上测试 | 部分放款后和解只分剩余，保证金解冻回可用，reconcile 恒成立 |

## 已实现（V12 批次：变更单资金守恒）

| Spec 资金不变量 | 测试 | 说明 |
|---|---|---|
| SC-007 加价补托管守恒 | `tests/test_change_order_money.py` | funded 态加价→补足差额托管，escrow/available 精确变动，reconcile 恒成立，放款额随新金额 |
| SC-007 减价退款守恒 | 同上 | 减价→差额退回可用余额，放款额随新金额，全程账实一致 |
| SC-007 变更单守卫 | 同上 | 提案方不能自接（not_counterparty）、已有 pending 不可再提（change_pending）、重复接受被拒（change_closed，无二次补托管） |
| SC-007 多轮随机改价守恒 | 同上 | seed 化 8 单×1~3 轮上下浮动改价后放款，每步 reconcile 断言零泄漏 |

## 已实现（V11 批次：存证哈希链防篡改深度校验）

| Spec 安全不变量 | 测试 | 说明 |
|---|---|---|
| SC-011 逐行哈希绕过防护 | `tests/test_anchor_chain.py` | 同步改 payload+payload_hash 骗过逐行校验 → 仍被 chain_hash 抓出 |
| SC-011 多米诺链接（改一行须重写整条后继链） | 同上 | 某行三重哈希全部自洽伪造 → 下一行 prev 链接断裂，定位到 seq+1 |
| SC-011 删除/重排篡改 | 同上 | 删除中间存证 → 后继 prev 断裂；创世锚点脱链 → 首条即断裂 |
| SC-011 链头可公示锚定 | 同上 | 未篡改链 verify.head == 末条 chain_hash（对外锚定基准） |

## 已实现（V10 批次：并发/重复提交防重放硬化）

| Spec 安全不变量 | 测试 | 说明 |
|---|---|---|
| 14.6 一任务一合约（重复接受报名/并发接单不产生第二份合约） | `tests/test_concurrency_guards.py` | 重复接受同一/不同报名均被 `not_recruiting` 拒绝；DB 层 `contracts.task_id UNIQUE` 为最后防线 |
| 05.B 托管资金只扣一次（重复 fund） | 同上 | 第二次 fund 命中 `not_fundable`，托管额恒等于合约金额 |
| 03.A 交付幂等（重复 deliver） | 同上 | 二次交付被状态机 `invalid_transition` 拒绝 |
| 05.B 放款不重复（重复验收/重复里程碑验收） | 同上 | 二次验收命中 `not_releasable`/`invalid_milestone_state`，执行者余额不二次增加；get_db 异常整体回滚保证零副作用 |
| MATCH 报名去重（重复报名） | 同上 | 第二次报名 `already_applied`，仅一条报名记录 |

## 已实现（V9 批次：核心不变量测试硬化）

| Spec 不变量 | 测试 | 说明 |
|---|---|---|
| 03.A 任务状态机 P0（必须严格约束流转） | `tests/test_state_machine.py` | 白名单穷举：每个非法 (from,to) 必拒且错误码为 invalid_transition；终态无出边；状态引用合法；无自环 |
| 05.B/PAY-006 资金守恒（全局守恒/托管有据/冻结有据） | `tests/test_money_property.py` | 随机化 20 条生命周期（验收/取消/仲裁/申诉/多里程碑），每步后 reconcile 断言账实一致 |

## 已实现（V8 批次：工程硬化——非功能需求落地）

| Spec 非功能项 | 实现 | 测试 |
|---|---|---|
| 14.6/05.B 资金操作强制幂等（Idempotency-Key，充值/提现） | `core/idempotency.py` + wallet 路由 | `tests/test_hardening.py` |
| ACC-001 注册/短信登录 60s 防刷限流 | `core/ratelimit.py` + account 路由 | 同上 |
| 14.6 资源级鉴权（越权访问拒绝）回归 | 各模块既有检查 + 集中越权测试 | 同上（跨用户/管理端） |

## 已实现（V7 批次：增长与分析闭环）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| 13.C 埋点事件上报 + 发布漏斗/接单漏斗看板（P0） | `analytics/service.py::funnels` + `router.py` | `tests/test_growth_analytics.py` |
| CNT-022 邀请裂变：邀请码归因 + 首单闭环奖励邀请人（每人一次） | `analytics/service.py::_on_task_completed` + 账户注册 | 同上 |
| SRCH-003 搜索词记录 + 热词榜 + 前缀联想 | `analytics/service.py::trending_terms/suggest_terms` | 同上 |

## 已实现（V6 批次：真实 LLM 网关 + 供需看板 + 演示数据）

| 项 | 实现 | 测试 |
|---|---|---|
| 04.E 真实 LLM 网关 AnthropicLLM（claude-opus-4-8 + adaptive thinking + JSON Schema 结构化输出） | `server/app/modules/decompose/llm.py` | `tests/test_llm_gateway.py`（mock SDK） |
| 04.E 降级路径（无 Key/超时/输出不合规 → 自动回落模板引擎，预算守恒兜底） | `llm.py::AnthropicLLM.decompose` | 同上（三条降级/校验用例） |
| KB-024 类目供需看板（在招需求/闭环数/GMV/供给/供需比） | `knowledge/router.py::category_demand` | 同上 |
| 演示数据脚本（一键生成可交互样例：用户/任务/闭环/圈层/动态） | `server/scripts/seed_demo.py` | 运行验证 |

> LLM 网关设计：`ANTHROPIC_API_KEY` 存在即启用真实模型；缺省与 CI 环境走
> `TemplateLLM`，测试用 `unittest.mock` 打桩 SDK，全程离线可跑。接入真实模型
> 不改任何业务代码——`get_gateway()` 抽象层已就位。

## 已实现（V5 批次：前端覆盖补齐 + 工程化交付）

| 项 | 实现 | 验证 |
|---|---|---|
| Web 发布向导（模板填充/AI 可行性提示/多人/保证金/城市与类目下拉/受限类目提示） | `web/src/pages/Publish.tsx` | 前端测试 + tsc/vite build |
| Web 服务设置（定价/可接单时间/隐私开关）与设备管理/注销 | `web/src/pages/Profile.tsx` | 同上 |
| Web 合约凭证下载 + 经验帖入口 | `web/src/pages/TaskDetail.tsx` | 同上 |
| SDK V3/V4 全量接口（澄清/模板/城市/会话/注销/导出/报价卡/圈层面板） | `packages/core/src/client.ts` | SDK 单测 |
| Docker 交付（server 镜像 + web nginx 镜像 + compose 一键全栈） | `server/Dockerfile`, `web/Dockerfile`, `docker-compose.yml` | YAML 校验 |
| CI 流水线（后端 pytest / 前端 vitest+build / 启动冒烟，PR 自动跑） | `.github/workflows/ci.yml` | PR #5 |

## 已实现（V4 批次）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| RISK-003 反欺诈（同对手方 7 天 3 单→不计信用+进人审队列） | `risk/service.py` + `task/router.py::_complete_task` | `tests/test_v4_features.py` |
| PAY-006 对账（守恒/托管有据/冻结有据三不变量，篡改可检出） | `risk/service.py::reconcile` + `/admin/jobs/reconcile` | 同上 |
| MATCH-003 订阅推送频控（每人每日 5 条） | `matching/events.py` | 同上 |
| CIR-010 同圈信任加成 + 推荐理由标识 | `matching/service.py` | 同上 |
| CIR-009 圈层数据面板（成员/帖子/成交/GMV，管理员） | `circle/router.py::circle_stats` | 同上 |
| IM-009 结构化报价卡消息 | `im/router.py::send_quote_card` | 同上 |
| ACC-030 隐私设置（非公开档案仅信任摘要） | `account/` | 同上 |
| ACC-013 服务定价与可接单时间（名片页承接下单） | `account/` | 同上 |
| KB-003 闭环任务一键生成经验帖（case 卡挂类目与来源） | `content/router.py::create_experience_post` | 同上 |
| KB-013 估价新鲜度（仅统计近 180 天，过期淘汰） | `knowledge/service.py::price_reference` | 同上 |
| TASK-003 任务模板库（模板+检查清单+参考价） | `task/service.py::TASK_TEMPLATES` | 同上 |
| GEO-030 城市开通管理（线下任务城市门禁） | `task/models.py::City` + `admin/router.py` | 同上 |
| SC-010 合约文本与结算凭证导出（含流水与存证哈希） | `contract/router.py::export_contract` | 同上 |

## 已实现（V3 批次）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| ACC-005 登录会话/设备管理（列出/踢出，token 绑定会话可吊销） | `account/models.py::LoginSession` + `core/deps.py` | `tests/test_v3_features.py` |
| ACC-006 账号注销（未结算合约/纠纷/余额阻断，脱敏保留） | `account/router.py::deactivate_account` | 同上 |
| TASK-007 多人任务（N 名额子任务，独立合约，母任务自动结项） | `task/router.py::create_task` + `decompose/service.py` | 同上 |
| AI-DEC-001/002 对话式澄清 + 预算可行性预判（对照知识库中位价） | `decompose/router.py::clarify` | 同上 |
| AI-DEC-025 母任务结项报告（成本/工期/交付清单） | `decompose/router.py::final_report` | 同上 |
| OPS-004 类目管理（种子+CRUD+启停校验+资质挂载） | `task/models.py::Category` + `admin/router.py` | 同上 |
| MATCH-008 匹配权重后台可配（实时生效，和为 1 校验） | `matching/models.py::MatchingConfig` + `admin/router.py` | 同上 |
| NTF-003 通知偏好（分类开关，funds 必达不可关） | `support/models.py::NotificationPref` + `notification/` | 同上 |
| CS-013 工单（AI 转人工自动建单→处理→通知） | `support/models.py::Ticket` + `admin/router.py` | 同上 |
| DSP-008 申诉复核（一次，差额纠正性划转终局） | `dispute/router.py::appeal/appeal_verdict` | 同上 |
| CRED-003 信用等级权益（S/A/B/C → 费率 6%/7%/8%） | `account/service.py::credit_level` + 合约生成 | 同上 |
| GEO-021 行程共享（执行者开关，任务结束失效） | `task/router.py::trip-share` | 同上 |
| GEO-023 紧急求助（留痕+通知对方） | `task/router.py::sos` | 同上 |
| GEO-024 位置保留策略（结束 30 天清除精确坐标） | `task/router.py::purge_locations` | 同上 |

## 已实现（V2 批次）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CRED-005 保证金（成交冻结/闭环退还/违约罚没） | `wallet/service.py` + `contract/service.py::_settle_deposit` | `tests/test_v2_features.py` |
| ACC-022 职业资质 + 受限类目准入 | `account/router.py` + `task/service.py::check_category_qualification` | 同上 |
| LAW-003 律师市场（法律咨询类目 = 持证律师接单） | 同上（复用任务流） | 同上 |
| SC-011 存证哈希链（append-only、防篡改可验证） | `anchor/`（合约签署/托管/放款/裁决自动入链） | 同上（含篡改检测） |
| ACC-033 黑名单（禁私聊/禁报名/推荐排除，双向） | `account/models.py::Block` + im/task/matching 检查点 | 同上 |
| IM-004 消息撤回（2 分钟窗口，审计副本保留） | `im/router.py::recall_message` | 同上 |
| AI-DEC-023 子任务违约自动重新招募 | `decompose/resilience.py` | 同上 |
| AI-DEC-022 逾期预警 job | `decompose/resilience.py::deadline_alerts` | 同上 |

## 已实现（V1 收尾批次）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| SRCH-001 统一搜索（任务/用户/内容/圈层分组） | `server/app/modules/search/router.py` | `tests/test_v1_extras.py` |
| TASK-006 周期任务（闭环自动续期+通知） | `task/events.py` + `Task.recurrence` | 同上 |
| LAW-002 文书生成（催告函/和解协议，自动填充） | `legal/router.py::generate_document` | 同上 |
| ACC-031 个人数据导出（PIPL/GDPR） | `account/router.py::export_my_data` | 同上 |
| OPS 管理后台 Web UI（指标/举报处置/封禁） | `web/src/pages/Admin.tsx` | `web/src/Admin.test.tsx` |
| MATCH-007 竞价发布与报价比选 UI | `web/src/pages/{Publish,TaskDetail}.tsx` | 构建 + SDK 单测 |
| APP-005/006 App 五 Tab + 任务详情操作/钱包/通知 | `app/App.tsx` | 骨架（Expo 运行时验证） |

## 已实现（V1 增量，2026-07-03）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CNT-001/003 动态与博客（可见性/标签） | `server/app/modules/content/` | `tests/test_content_circle.py` |
| CNT-005 内容挂载服务入口 | `content/models.py::linked_category` | 同上 |
| CNT-006 内容/评论机审 | `content/router.py`（复用 RISK-001 词表） | 同上 |
| CNT-010/011 关注流/最新流 | `content/router.py::feed` | 同上 |
| CNT-020/021 点赞评论/关注粉丝 | `content/router.py` | 同上 |
| CIR-001 三类圈层+自带群聊 | `circle/` | 同上 |
| CIR-002 按技能/城市推荐圈层 | `circle/router.py::discover` | 同上 |
| CIR-003 加入审核+信用门槛 | `circle/router.py::join/approve` | 同上 |
| CIR-004/005 圈层内容流/任务板（仅成员） | `circle/router.py` + Task.visibility | 同上 |
| CIR-006/007 群聊成员同步/移出管理 | `circle/router.py` | 同上 |
| TASK-008 任务可见范围（公开/圈层） | `task/models.py` + router | 同上 |
| SC-004 多里程碑分期交付/放款 | `contract/service.py::define/deliver/release_milestone` | `tests/test_contract_v1.py` |
| SC-007/TASK-025 变更单双签改价（多退少补、版本+1） | `contract/service.py::propose/accept_change` | 同上 |
| 取消/裁决按剩余托管额计算 | `contract/service.py::cancel/execute_verdict` | 同上 |
| MATCH-004 定向邀约（接受即成交） | `matching/router.py` | `tests/test_admin_legal_matching.py` |
| TASK-042 类目+城市订阅→发布通知 | `matching/models.py` + `matching/events.py` | 同上 |
| LAW-001 法律信息 AI（免责声明/高风险拒答） | `legal/router.py` | 同上 |
| LAW-005 证据包导出（SHA256 防篡改） | `legal/router.py::evidence_export` | 同上 |
| RISK-006/007 举报→审核队列→处置（下架/封禁） | `admin/` + `core/deps.py` 封禁拦截 | 同上 |
| OPS-002 用户管理（封禁/解封） | `admin/router.py` | 同上 |
| OPS-007 指标看板（闭环率北极星/GMV/佣金/纠纷） | `admin/router.py::metrics` | 同上 |
| Web 社区/圈层页 + 里程碑操作 + 邀约 + 订阅 | `web/src/pages/{Community,Circles}.tsx` 等 | `web/src/App.test.tsx` + SDK 单测 |

## 已实现（MVP）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| ACC-001/002 注册登录（短信码/密码） | `server/app/modules/account/router.py` | `tests/test_account.py` |
| ACC-010/011 资料与技能标签 | 同上 | 同上 |
| ACC-020 实名认证（模拟 eKYC）+ 接单/提现准入 | `account/router.py` + `core/deps.py::require_verified` | `test_account.py`, `test_wallet.py`, `test_task_flow.py` |
| CRED-001/002/004 信用分/双向盲评/违约惩罚 | `account/service.py` | `test_task_flow.py`, `test_im_dispute_support.py` |
| CRED-006 公开信用名片（脱敏） | `account/router.py::public_profile` | `test_account.py` |
| TASK-001/004/005 发布/机审/编辑约束 | `task/router.py`, `task/service.py` | `test_task_flow.py` |
| 任务状态机（03.A，非法流转拒绝） | `task/models.py::TRANSITIONS` + `service.transition` | `test_task_flow.py::test_state_machine_*` |
| TASK-020~024 成交/详情/进度/会话/交付 | `task/router.py` | `test_task_flow.py`, `test_e2e_closed_loop.py` |
| TASK-026 取消规则 | `contract/service.py::cancel` + `CANCEL_RULES` | `test_task_flow.py::test_task026_cancel_rules` |
| TASK-030/031/033 验收/超时自动验收/驳回 | `task/router.py` | `test_task_flow.py` |
| TASK-036 母任务进度聚合 | `decompose/service.py::tree_progress` | `test_decompose_knowledge.py` |
| TASK-040/041 广场/搜索/筛选 | `task/router.py::list_tasks` | `test_task_flow.py` |
| MATCH-001 报名报价 | `task/router.py` | `test_task_flow.py` |
| MATCH-002 AI 推荐（可解释加权打分） | `matching/service.py` | `test_task_flow.py::test_match002_*` |
| MATCH-009 冷启动兜底 | `matching/service.py`（中性分+新人理由） | 同上 |
| AI-DEC-001~015 分解（模板 LLM/编辑/校验/直通） | `decompose/llm.py`, `decompose/service.py` | `test_decompose_knowledge.py` |
| AI-DEC-020 依赖顺序自动发布 | `decompose/service.py::_on_task_completed` | `test_decompose_knowledge.py`, `test_e2e_closed_loop.py` |
| AI-DEC-021 驾驶舱数据 | `decompose/router.py::tree` | 同上 |
| AI-DEC-030 预算拆分守恒/超支拒绝 | `decompose/service.py::validate_items` | `test_decompose_knowledge.py` |
| SC-001~003 合约生成/双签/托管 | `contract/service.py` | `test_task_flow.py`, `test_e2e_closed_loop.py` |
| SC-005/009 验收放款/抽佣分账 | `contract/service.py::release` + `wallet/service.py` | 同上（含资金守恒审计） |
| SC-006 违约规则引擎 | `contract/service.py::cancel` | `test_task_flow.py` |
| SC-008 纠纷冻结与裁决执行 | `contract/service.py::freeze/execute_verdict` | `test_im_dispute_support.py` |
| SC-020~022 钱包三态/提现/流水 | `wallet/` | `test_wallet.py` |
| KB-001/002 闭环经验卡（事件驱动、脱敏） | `knowledge/service.py::_on_task_completed` | `test_decompose_knowledge.py` |
| KB-005 FAQ 种子 | `knowledge/service.py::SEED_FAQS` | `test_im_dispute_support.py` |
| KB-020/021 模板检索/估价分布 | `knowledge/service.py` | `test_decompose_knowledge.py` |
| GEO-004 位置脱敏（成交后可见精确地址） | `task/router.py::dump_task` | `test_task_flow.py` |
| GEO-010/011/015 附近任务/距离筛选/距离参与打分 | `task/router.py::list_tasks`, `matching/service.py` | `test_task_flow.py` |
| GEO-020 到场打卡（误差校验） | `task/router.py::checkin` | `test_task_flow.py` |
| IM-001/002 单聊/任务会话自动创建 | `im/` | `test_im_dispute_support.py` |
| IM-005 陌生人频控 | `im/service.py::check_stranger_limit` | 同上 |
| IM-006 防跳单风控标记 | `im/service.py::RISK_PATTERNS` | 同上 |
| DSP-001~004 发起/冻结/证据链/和解 | `dispute/router.py` | 同上 |
| DSP-006/007 仲裁裁决自动执行+信用惩罚 | `dispute/router.py::issue_verdict` | 同上 |
| NTF-001/004 事件驱动站内信 | `notification/` | 同上 |
| CS-002/003/006 FAQ 问答/账户上下文/转人工 | `support/router.py` | 同上 |
| 主闭环 E2E（01 spec 第 3 节全链路） | 全模块 | `test_e2e_closed_loop.py` |
| Web 端核心页面（13 spec WEB-001/002/003/007） | `web/src/pages/*` | `web/src/App.test.tsx` |
| 共享 SDK（13 spec 两端共享 API） | `packages/core/src/client.ts` | `packages/core/src/client.test.ts` |
| App 骨架（13 spec APP-001/003/005 精简） | `app/App.tsx` | 骨架（未接入测试，见差距） |

## 有意简化（MVP 降级实现，spec 目标不变）

| 项 | 现状 | 演进 |
|---|---|---|
| 短信验证码 | 固定码 123456 | 接短信服务商 |
| eKYC | 提交即通过 | 接身份核验+人脸 |
| 支付托管 | 平台内账本模拟 | 持牌机构担保交易/分账（12.A 红线） |
| LLM 分解 | 模板驱动 `TemplateLLM` | 经 `LLMGateway` 接真实模型，JSON Schema 校验已就位 |
| 客服问答 | FAQ 关键词检索 | RAG（向量检索 + LLM 生成） |
| 内容机审 | 违禁词表 | 第三方内容安全 |
| IM | REST 轮询 | WebSocket/云 IM（`MessageProvider` 抽象） |
| 定时任务 | 暴露为可调用 job 接口 | 调度器（cron/celery） |

## 未实现（均依赖外部供应商/云服务，代码侧接口已就位）

- 短视频上传转码与沉浸流（CNT-002/014）— 转码/CDN/内容安全云服务
- 个性化推荐流排序模型（CNT-011 完整版）— 需线上行为数据积累
- 存证链上锚定（SC-011 阶段三）— 哈希链已实现，差公链/联盟链写入
- 音视频通话（IM-007）— RTC 云服务
- 企业认证与发票（ACC-021/PAY-008）— 工商核验与税务接口
- App 深化：地图撒点、扫码打卡、离线推送通道（后端 API 均已就绪）
- 真实供应商接入：短信/eKYC/持牌支付托管/LLM/内容安全（抽象层已就位，接入不动业务代码）
