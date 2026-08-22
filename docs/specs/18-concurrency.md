# 18 · 并发与生产化硬化（CONC）

> 现状：SQLite 单文件 + 单进程，靠「幂等指纹 + 状态机白名单 + 事务整体回滚 +
> DB 唯一约束」保证正确性。**单进程安全，多副本存在真实竞态**。
> 本 spec 定义把系统做成可多副本部署的最小充分改造。

## 18.A 数据库与连接（P0）

- **CONC-001** 支持 PostgreSQL：`PLATFORM_DATABASE_URL` 切换即可，业务代码零改动。
  SQLite 仅保留给开发与测试。
- **CONC-002** 连接池参数化：`pool_size` / `max_overflow` / `pool_pre_ping` /
  `pool_recycle` 可配；SQLite 分支自动跳过（不支持池参数）。
- **CONC-003** SQLite 开发环境开启 WAL 与 `busy_timeout`，降低本地并发写报错。
- **CONC-004** 方言探测工具 `is_postgres()`：让加锁逻辑在 SQLite 下自动降级为
  无锁（测试仍靠状态机守卫），在 PG 下启用真实行锁。

## 18.B 资金写路径加锁（P0，最关键）

竞态场景：两个进程同时读到 `contract.status == "funded"`，各自通过状态机判断，
各自放款 → 重复放款。应用层判断拦不住，必须落到 DB 层。

- **CONC-010** `lock_contract(db, contract_id)`：`SELECT ... FOR UPDATE` 取合约行锁。
- **CONC-011** `lock_wallet(db, user_id)`：钱包账户行锁；多账户按 `user_id` 升序
  依次加锁，**避免死锁**（转账场景两个账户）。
- **CONC-012** 关键路径接入行锁：`fund` / `release` / `release_milestone` /
  `cancel` / `execute_verdict` / `withdraw` / `decide_withdraw` / `settle_platform`。
- **CONC-013** 乐观锁兜底：`Contract.version` 参与 UPDATE 条件，
  影响行数为 0 → `409 concurrent_modification`（PG 无锁场景与 SQLite 双保险）。

## 18.C 分布式限流（P0）

- **CONC-020** 限流后端抽象：`RateLimiter` 协议 + `MemoryRateLimiter`（现状）
  + `RedisRateLimiter`（新增）。
- **CONC-021** `PLATFORM_REDIS_URL` 存在时自动切 Redis，否则用内存实现；
  Redis 不可用时**降级为内存**并告警，不阻断登录（可用性优先于严格限流）。
- **CONC-022** Redis 实现用 `INCR` + `EXPIRE` 原子窗口计数。

## 18.D 事件总线可替换（P1）

- **CONC-030** 事件派发抽象：`EventBus` 协议 + `InProcessBus`（现状）
  + 预留 `MQBus` 接口（发布到消息队列）。
- **CONC-031** 多副本下进程内事件只在处理请求的副本触发，
  文档明确标注哪些事件是「幂等可重放」的（经验入库、通知），
  哪些必须走 MQ 才安全（后继子任务发布）。

## 18.E 定时任务单实例（P1）

- **CONC-040** job 端点已有令牌鉴权（OPS-011）；新增**执行锁**：
  同一 job 在锁有效期内只允许一个实例执行（DB 行锁实现，PG/SQLite 通用）。
- **CONC-041** `JobLock` 表：job_name 唯一，记录持锁者与到期时间，
  超时自动可抢占（防持锁进程崩溃后永久阻塞）。

## 18.F 并发验证（P0）

- **CONC-050** 并发压测脚本：多线程并发调用同一合约的 `fund`/`accept-delivery`，
  断言**只有一次成功**、资金守恒不变量成立。
- **CONC-051** 乐观锁冲突测试：模拟并发改价，第二个提交拿到 409。
- **CONC-052** job 执行锁测试：并发触发同一 job，只有一个真正执行。

## 验收标准

- 切到 Postgres 后全部测试通过（同一套测试，仅换 DATABASE_URL）；
- 并发压测下资金四不变量恒成立；
- Redis 不可用时系统仍可登录（降级），有告警。
