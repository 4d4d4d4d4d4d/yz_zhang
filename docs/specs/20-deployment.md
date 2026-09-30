# 20 · 部署、可观测与运维（DEP）

> 现状：`docker compose up --build` 一键起开发栈（SQLite + 单副本 + 无监控）。
> 本 spec 定义**生产级一键部署**：Postgres + 多副本 + 单实例定时任务 +
> 健康检查 + 指标 + 备份 + 一条命令完成。

## 20.A 一键部署（P0）

- **DEP-001** `deploy/docker-compose.prod.yml`：db(Postgres) / redis / api(可扩副本) /
  worker(定时任务，单实例) / web(Nginx) / 反向代理。
- **DEP-002** `deploy/.env.example` 列全部必填变量并注明「必须修改」项；
  `deploy/up.sh` 做前置校验（弱密钥、默认 JOB_TOKEN、mock 支付）后再启动。
- **DEP-003** 镜像构建多阶段，非 root 运行，只读根文件系统（数据卷除外）。
- **DEP-004** 启动顺序靠健康检查依赖，不靠 sleep。

## 20.B 健康检查与就绪（P0）

- **DEP-010** `GET /healthz`：进程存活，永远快速返回（不查 DB）。
- **DEP-011** `GET /readyz`：DB 可写、Redis 可达（若启用）、迁移版本匹配；
  任一不满足返回 503，编排系统据此不导流量。
- **DEP-012** `GET /version`：git sha、构建时间、环境名。

## 20.C 数据库迁移（P0）

- **DEP-020** 引入 Alembic：`alembic upgrade head` 为唯一建表路径，
  生产**禁用** `create_all`（仅测试/开发保留）。
- **DEP-021** 迁移在 api 启动前由一次性 init 容器执行，避免多副本并发建表。
- **DEP-022** 迁移版本写入 `/readyz`，代码与库版本不一致时不就绪。

## 20.D 备份与恢复（P0）

- **DEP-030** `deploy/backup.sh`：`pg_dump` 定时全量 + 保留策略；
  存证链 head 一并快照（可对外公示、便于篡改验证）。
- **DEP-031** `deploy/restore.sh` 并在文档中记录**演练过的**恢复步骤与 RTO/RPO 目标。
- **DEP-032** 恢复后一致性校验：跑资金四不变量对账 + 存证链校验，两者都过才算恢复成功。

## 20.E 可观测（P1）

- **DEP-040** 结构化 JSON 日志：request_id、user_id、path、状态码、耗时；
  **禁止**记录 token/密码/证件号/验证码。
- **DEP-041** `request_id` 中间件：入站生成或透传，随响应头返回，贯穿日志。
- **DEP-042** `GET /metrics`（Prometheus 文本格式）：请求量/延迟分位/错误率、
  资金关键计数（托管中金额、待提现、纠纷未决数）。
- **DEP-043** 告警清单：对账不平、存证链断裂、job 超时未执行、
  提现失败率突增、5xx 突增。

## 20.F 定时任务编排（P0）

- **DEP-050** worker 容器统一驱动全部 job 端点（过期下架、自动验收、SLA 升级、
  编排 tick、对账、锚定），带 `X-Job-Token`。
- **DEP-051** 每个 job 记录上次成功时间，`/readyz` 之外单独暴露 job 健康；
  超过预期周期 2 倍未成功即告警（配合 CONC-040 执行锁）。

## 20.G 验证（P0）

- **DEP-060** 冒烟脚本：起栈 → `/readyz` 通过 → 注册→发布→托管→放款闭环 →
  对账通过 → 关栈。CI 可跑。
- **DEP-061** 备份恢复演练脚本：备份 → 清库 → 恢复 → 不变量校验通过。
- **DEP-062** 配置校验测试：弱密钥/默认 token/mock 支付在 prod 下被拒绝启动。

## 验收标准

- 一条命令（`deploy/up.sh`）从零到可用，无需手工建表；
- api 可水平扩到 N 副本而 job 不重复执行；
- 演练过的恢复流程，恢复后不变量成立。
