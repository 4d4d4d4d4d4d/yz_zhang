# 全系统体检：现在真的能跑到什么程度

> 这一篇回答四个问题：**前端连得上后端吗**、**数据库怎么搭**、
> **经验数据怎么清洗累积**、**跑起来有什么问题**。
>
> 全部结论都来自**这一轮真实运行的输出**，不是读代码得出的判断。
> 每一节末尾给出复现命令——半年后数字变了，重跑一遍就知道。
>
> 体检日期：2026-09-30，版本 `0.99.0`，迁移 head `c7e1f2a90b34`

## 0. 一句话结论

主链路（注册 → 发布 → 成交 → 双签 → 托管 → 验收 → 分账 → 提现）
**在真实 HTTP、真实浏览器、真实数据库上跑通了**，资金五不变量成立，
22 个定时任务全部可执行。**但一分真钱都还不能收**——`PLATFORM_ENV=prod`
时代码会拒绝启动，缺 10 项对接（见第 5 节）。这是刻意的硬拦截，不是缺陷。

体检本身发现并修掉了 3 个真问题，其中 1 个会让生产迁移出事（第 4 节）。

---

## 1. 前端连得上后端吗

**结论：连得上，这一轮第一次有证据。**

此前的证据是不够的，而且不够的方式很具体：这个仓有 **84 条 web 测试，
每一条都把 `fetch` 换掉了**。它们能证明「按钮按下去会调这个方法」，
证明不了「前端与后端真的能对接」。而 `scripts/smoke.py` 打的是真实 HTTP，
但它是 `urllib` 打上去的——**它证明后端好，不证明前端连得上后端**。
两条闭环各证一半，中间正好留了一条缝。

所以补了第三条闭环（82 号 spec）：真 Chromium × `vite build` 产物 ×
真服务端，同源反向代理（与生产的 Nginx 同源一致，而不是为测试放宽 CORS）。

本轮输出：

```
真浏览器 × 真服务端：
  ✓ 登录页打得开
  ✓ 注册走通并拿到 token  eyJzdWIiOiAx…
  ✓ 科技感底色生效  rgb(7, 10, 17)
  ✓ 视差 hero 渲染
  ✓ 钱包页读到真实余额
  ✓ 通知开关读到服务端的必达清单
  ✓ 发任务走通（含 V77 的必填归属）  1
  ✓ 刚发的任务出现在广场  E2E 保洁 42685
  ✓ 自助开工单并出现在我的工单里
  ✓ 没有 5xx / 422
  · 其他 4xx（可能是正常的「没有这条记录」）：["404 …/api/v1/tasks/1/dispute"]
联调通过：构建产物与真服务端能对接。
```

那条 404 是**设计如此**：DSPC-010 规定「该任务没有纠纷」就回 404，
前端据此画「暂无纠纷」。第一版脚本把它报成缺陷——**我的检查错了，
不是应用错了**。判据因此收敛成「5xx 与 422 算缺陷，其他 4xx 只打印」：
一个假报警多的闸门会被人关掉。

覆盖范围是有账的（`tests/test_e2e_coverage.py`）：从 `App.tsx` 路由表
自动扫页面，未走到的必须写明理由，理由里不许出现「还没做 / 待补 / TODO」
——那是欠账，归 `72-status-ledger.md`，不是豁免理由。

**还没有的**：App 端没有真机联调（要模拟器，CI 成本量级不同）；
联调是单用户脚本，站内信/纠纷/核验要多方，起不来第二个角色。

```bash
npm run build:web && (cd server && python -m scripts.e2e_web)
```

---

## 2. 后端数据库怎么搭

### 2.1 唯一一条生产建表路径是 Alembic

`create_all` 在 `PLATFORM_ENV=prod` 时**直接抛异常**（`app/core/db.py`），
因为多副本同时 `create_all` 会互相踩。开发态才用它。

### 2.2 本轮从零建库的实测

```
迁移条数        32
单一 head       c7e1f2a90b34         （没有分叉，链完整）
upgrade head    退出码 0
建出            88 张表、189 个索引
downgrade base  退出码 0，只剩 alembic_version（可逆）
再 upgrade head 88 张表（可重复）
```

`downgrade` 真的能回到底，这件事有实际价值：上线当天迁移失败时，
**有退路和没退路是两种不同的事故**。

### 2.3 两种引擎，两条都要验

| | 开发 / CI 快轮 | 生产 |
|---|---|---|
| 引擎 | SQLite | Postgres 16 |
| 建表 | `alembic upgrade head` | 同 |
| ALTER | `op.batch_alter_table`（建新表→拷数据→改名） | 原生 ALTER |

SQLite 不支持大多数 `ALTER`，所以改列一律走 `batch_alter_table`。
CI 的 `migration-drift` job **两个引擎各跑一遍** `alembic upgrade head &&
alembic check`——只跑 SQLite 会放行一整类在生产迁移当场失败的问题。

### 2.4 搭一套出来

```bash
# 开发（SQLite，零依赖）
cd server && python -m alembic upgrade head && python -m uvicorn app.main:app

# 生产（Postgres）
export PLATFORM_DATABASE_URL=postgresql+psycopg://user:pw@host:5432/platform
cd server && python -m alembic upgrade head
```

就绪探针会自己报迁移状态，**不需要人去 ssh 上去看版本号**：

```json
{"ready": true, "env": "sandbox",
 "checks": {"db": "ok", "ratelimit": "memory", "migration": "ok"}}
```

`migration` 为 `mismatch` 时 `ready` 为 false，滚动发布会因此停住——
这正是要的：**代码比库新的那个副本不该接流量**。

备份与恢复演练见 `OPERATIONS.md`，CI 里有 `restore-drill` job 在跑。

---

## 3. 经验数据怎么清洗累积

**结论：这一轮之前是「不清洗」，而代码注释里写着在清洗。**

两条经验管线：`task.completed` → `KnowledgeCard`（类目/城市/价格/工期），
人工核验结论 → `VerificationLesson` → `lessons_prompt()` → **agent 系统提示词**。
两处都写着「脱敏」。探针拿一个真实形状的标题跑完闭环：

```
落库的 title: 给王芳家搬钢琴 朝阳区幸福小区3号楼502 联系13800138000
  含手机号 True  含姓名 True  含门牌号 True
别的用户读经验卡: 200        别人能读到含手机号的卡: True
拼出来的系统提示词: 含手机号 True、含姓名 True、含地址 True
```

也就是说一个客户的电话与门牌号，**(a) 通过经验卡端点给了别的用户，
(b) 通过提示词给了第三方模型**。《个人信息保护法》第六条（最小必要）
与第十九条（目的限制）在这里直接命中：为「撮合与履约」收集的信息，
被用到了「提示另一单的 AI」上。

现在的做法（83 号 spec，三条原则）：

1. **最可靠的脱敏是不采集**。经验卡的用途是「按类目与城市看价格与工期」，
   用户打的标题对这个用途没有必要，所以不再存它，改存 `类目·城市`。
2. **数字整段抹掉**，不用日志那种 `138****8000` 掩码——经验数据的去处是
   别的用户与第三方模型，**末四位加城市常常已经足够定位到人**。
   同理**行政区留着、小区与门牌抹掉**：区是经验里有用的部分，一户人家不是。
3. **写入点做，读出点再做一遍**。多一道防线的成本是一次正则，
   漏出去的成本是一条个人信息。

**累积**这一侧修了一个会歪结论的问题：`lessons_prompt` 原来逐条拼，
同一个核验人对同类任务写同一句结论（很常见）拼出来就是三条一样的经验，
**模型会把它当成「这是最重要的一条」**。现在按内容去重。

**守不住的部分，明确写出来**：核验人自己打的字里出现第三方姓名
（「客户李强投诉」）去不掉——平台不知道「李强」是谁。这条边界写成了
一条测试，理由是**不能让下一个人以为这里已经完全匿名化了**：
那种误解比漏本身更危险，它会让人放心地把这段文本送到更多地方去。

存量数据有一次性脚本，逐条打印改动（动用户数据的脚本不留痕是最不该有的）：

```bash
cd server && python -m scripts.scrub_experience --dry-run   # 先看会改什么
cd server && python -m scripts.scrub_experience             # 真的改
```

**刻意不做成定时任务**：那会让人以为「脏数据会被自动处理」，
从而放心地继续写脏数据——真正该拦的是写入点，那里已经有闸门了。

**还没有的**：没有时效（一年前的价格与上周同权重）、没有质量过滤
（随手写的「不行」也会进提示词）、经验卡没有去重、脱敏后向量索引
没有重算。四条都在 72 号台账里，各自缺的都是一个产品判断而非一次重构。

---

## 4. 跑起来有什么问题

这一节是体检的本体：**真的跑，看它出什么**。

### 4.1 启动与运行

```
uvicorn 启动          干净，日志里 WARNING / ERROR / Traceback 共 0 条
/readyz               {"ready": true, db: ok, ratelimit: memory, migration: ok}
/version              0.99.0, env=sandbox, sandbox=true, ledger_backend=internal
/metrics              26 条指标
/jobz                 22 个 job 在册
```

`ratelimit: memory` 不是错误但**是单机语义**：多副本下每个副本各算一份配额。
生产要配 Redis，`OPERATIONS.md` 里有。`sandbox=true` 与
`ledger_backend=internal` 是显式标注，避免有人误以为这是真实资金。

### 4.2 22 个定时任务逐个真跑

不是看它们注册了，是 POST 一遍看返回：

```
✓ auto_accept 200 {"auto_accepted":0}      ✓ event_drain 200 {...}
✓ expire_tasks 200 {"expired":0}           ✓ event_purge 200 {...}
✓ settle_reviews 200 {"settled":0}         ✓ security_purge 200 {...}
✓ deadline_alerts 200 {"alerted":0}        ✓ remit_tax 200 {...}
✓ expire_unsigned 200 {"expired":0}        ✓ kb_reindex 200 {"reindexed":5}
✓ escalate_overdue 200 {"escalated":0}     ✓ remind_acceptance 200 {...}
✓ deliver_webhooks 200 {...}               ✓ team_approval_reminders 200 {...}
✓ expire_verifications 200 {"expired":0}   ✓ withdraw_second_reminders 200 {...}
✓ remind_response 200 {...}                ✓ review_queue_reminders 200 {...}
✓ mission_tick_all 200 {"ticked":0}        ✓ reconcile 200 {"ok":true,...}
✓ purge_locations 200 {...}                ✓ notarize 200 {...}
跑通 22 / 失败 0
跑完 /jobz：never_run 0，有 last_error 的 0 个
```

空库上多数返回 0 是对的。要紧的是**没有一个 500**——
job「静默不跑」或「一跑就炸」比业务 bug 更危险，因为没有人在看。
`/metrics` 里 `platform_jobs_never_run` 与 `platform_jobs_stale`
就是给监控盯这件事的。

### 4.3 两条闭环脚本

```
scripts/smoke.py        20 步全绿，执行方到账 18400 == 18400（扣 8% 佣金），
                        闭环后 platform_escrow_cents 归零
scripts/sandbox_check.py 28 项全绿，含资金五不变量、代扣税款、第三方存证背书
```

### 4.4 体检查出的三个真问题（已修）

**(a) 迁移与模型漂移，会让生产迁移出事。**

`alembic check` 报 `queue_sla_notices.created_at`：模型声明
`Mapped[datetime]`（非 Optional，即 NOT NULL），V103 的迁移写了
`nullable=True`。这张表是**只增不改**的告知记录，一行没有时间等于
这条告知无法按「多久以前告知过」筛，而队列催办（QUEUE-012）正是靠它
判断「这件已经告知过了」。补迁移 `c7e1f2a90b34`，先回填再收紧——
**已经发出去的告知不能因为迁移消失，否则用户会被重复催一遍**。

**(b) 更要紧的是：为什么三个批次都没人发现。**

`test_migrations_match_models` 的 docstring 写着「迁移建出的**表结构**
必须与 ORM 模型一致」，而它实际只比**表名与列名的集合**——
nullable 与类型它看不见。CI 的 `alembic check` 当时是红的，但没人看 CI。

这是「承诺了却没有东西在检查」这个形状的**第八次**（V96 的「在管理后台做」、
V99 的「必须换人」、V101 的 `can_invoice`、V103 的 `SUPPORT_SLA_HOURS`、
V106 的 eslint 豁免、V108 的两处脱敏 docstring）。所以这次不是只修那一列，
而是**把检查补到与承诺一样宽**：新增
`test_migrations_match_column_properties`，用 alembic 自己的
`compare_metadata`（`alembic check` 背后那个），而不是手写属性比对——
手写的第二份实现必然抄漏。

附带一条自检（`test_dep022_drift_scanner_can_actually_see_drift`）：
人造一处 nullable 漂移喂给同一个比对函数，它必须报出来。
**扫不到等于全绿，是最糟的一种绿**，而这一条防的正是被修掉的那种测试。

**(c) 两个会让工具变得没人用的小问题。**

- `scripts/e2e_web.py` 把库文件写在 `server/e2e_<时间戳>.db`，跑几轮
  就在仓里留下八个未跟踪文件。**一个会把垃圾留在工作区的脚本，
  下一个人会不敢跑它。** 改到临时目录并在 `finally` 里删。
- `scripts/smoke.py` 连不上目标时抛原始 `URLError`，运维看到的是
  二十行 urllib 栈——**从那堆栈里分不出「服务没起来」和「这个脚本坏了」**。
  改成一句话加退出码 2。

### 4.5 没查的

- **压测与并发**：没有跑负载。并发正确性有测试（`test_conc_hardening.py`
  盯资金总额不漂移），但「1000 QPS 下什么先倒」没有数据。
- **Postgres 的漂移与验收**：本地没有 Postgres，靠 CI 的
  `migration-drift` 与 `postgres-acceptance` 两个 job。
- **真实供应商**：全部是 mock/sandbox，这正是第 5 节拦住上线的原因。

---

## 5. 还有什么拦着上线

`PLATFORM_ENV=prod` 下跑一遍配置自检，**本轮实测被拒绝启动**，
缺 10 项（13 条红线里的 10 条）：

```
- P0 能力仍是非生产实现：payment(mock), sms(mock), kyc(mock),
  moderation(local), oauth(mock)
- SIGNATURE_PROVIDER=platform 不构成《电子签名法》的可靠电子签名
- NOTARY_PROVIDER=local 没有真实司法采信力
- LEDGER_BACKEND 仍为 internal：涉嫌资金池与二清，请接持牌机构存管后设 custody
- TAX_MODE=none：平台向自然人支付报酬即为扣缴义务人
- JWT_SECRET / JOB_TOKEN 仍是默认值
- 生产不得使用 SQLite
- CORS_ORIGINS 不得为 *
- TRUSTED_PROXY_HOPS 未设置：按 IP 的限流与封禁会全部失效
```

**这些不是待办事项列表，是硬拦截**：把上线前必须完成的对接变成
启动失败，而不是一行只有开发者看得见的日志。手续依赖顺序、审批周期、
等批复期间能做什么，全在 `GO-LIVE.md`。

自查（不用真起服务）：

```bash
cd server && PLATFORM_ENV=prod python -c "
from app.vendors.registry import startup_check
try: startup_check(); print('可以上线')
except Exception as e: print(e)"
```

---

## 6. 一次跑完整套体检

```bash
# 数据库：从零建库 + 可逆性 + 漂移
cd server
export PLATFORM_DATABASE_URL=sqlite:////tmp/check.db
python -m alembic upgrade head && python -m alembic check
python -m alembic downgrade base && python -m alembic upgrade head

# 起服务
export PLATFORM_ENV=sandbox PLATFORM_JOB_TOKEN=dev-job-token-change-me
python -m uvicorn app.main:app --port 8000 &
curl -s localhost:8000/readyz

# 三条闭环
python -m scripts.smoke
python -m scripts.sandbox_check
(cd .. && npm run build:web) && python -m scripts.e2e_web

# 回归
python -m pytest -q                      # 后端
cd .. && npm run lint && npm test         # web + App + SDK

# 上线红线
PLATFORM_ENV=prod python -c "from app.vendors.registry import startup_check; startup_check()"
```
