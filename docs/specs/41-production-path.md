# 41 一键部署与全链路验收（DEP-07x / PGSQL）

## 0. 这一批修的是什么

上一次我给出的状态汇报里，把上线阻断项分成四类，并说第一类（牌照/签约）
代码解决不了。这批发现：**第一类里混着一条纯代码问题，而且它让整条
「一键部署」路径从来没有真正跑起来过。**

### PGSQL-001 requirements.txt 里没有 Postgres 驱动

```
deploy/docker-compose.prod.yml:
  PLATFORM_DATABASE_URL: postgresql+psycopg://...   ← psycopg 3 方言
server/Dockerfile:
  RUN pip install --no-cache-dir -r requirements.txt
server/requirements.txt:
  （没有 psycopg / psycopg2 / 任何 Postgres 驱动）
```

实测：

```
ModuleNotFoundError: No module named 'psycopg'
```

而 `startup_check()` 在生产**明确拒绝 SQLite**，所以没有退路：
`./deploy/up.sh` 起出来的 api 容器必然启动失败。
文档里写得明明白白的那条生产部署路径，**一次都没有成功过**。

为什么一直没被发现：CI 的 boot-smoke 用 SQLite、migration-drift 用 SQLite、
sandbox_check 用 SQLite、全部 597 个测试用 SQLite。
**没有任何一处碰过生产真正要跑的那个引擎。**

### PGSQL-002 迁移在 Postgres 上漂移，而 SQLite 看不出来

补上驱动、接上真实 Postgres 之后，`alembic check` 立刻报：

```
New upgrade operations detected:
  modify_nullable uploaded_files.moderation_labels
  modify_nullable uploaded_files.created_at
```

两条迁移把列写成了 `nullable=True`，而模型是非 Optional 的 `Mapped[...]`＝NOT NULL。
**SQLite 的 `alembic check` 对列可空性差异是瞎的**，所以 CI 一直是绿的。

这不是小事：迁移与模型不一致意味着**生产迁移会在某次 ALTER 上当场失败**，
或者建出一张与 ORM 假设不符的表。

### PGSQL-003 测试套件里有 13 份 SQLite-only 的裸 SQL

```python
conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"))
```

`is_admin = 1` 只有 SQLite 接受；Postgres 直接
`column "is_admin" is of type boolean but expression is of type integer`。
同一行抄了 13 遍，**整套测试只能在 SQLite 上跑**，而生产跑 Postgres。

### DEP-070 「一键部署」以什么为成功

原来的 `up.sh` 以「容器起来 + /readyz 通过」为成功。
但这一路踩的坑——验证码没有钥匙孔、被告席没有麦克风、缺 Postgres 驱动——
**全都是「起来了但不能用」**。`/readyz` 只说得上数据库连得上。

所以一键部署必须以**全链路验收通过**为成功，不通过就明确失败并拒绝交付。

## 1. 条目

- **PGSQL-010** `requirements.txt` 加 `psycopg[binary]>=3.1`，并注明这不是可选项。
- **PGSQL-011** 修正两条迁移的 nullable；`moderation_labels` 用
  「可空加列 → 回填 → batch_alter 收紧」的三步，兼容 SQLite（无 ALTER COLUMN）
  与 Postgres。
- **PGSQL-012** CI 的 `migration-drift` 起真实 Postgres service，
  **两个引擎都跑** `alembic upgrade head && alembic check`。
- **PGSQL-013** 新 CI job `postgres-acceptance`：真实 Postgres 上跑迁移 → 起服务
  → 全链路验收 → `pg_dump` 恢复演练。
- **PGSQL-014** 测试里 13 份裸 SQL 收敛为 `conftest.promote_admin()` /
  `ban_user_row()`，走 ORM，引擎无关。
- **DEP-070** `deploy/oneclick.sh`：local / staging / prod 三档，起栈 → 等就绪
  → **跑 `scripts/acceptance.py`** → 不过则以失败退出。
- **ACC-E2E** `server/scripts/acceptance.py`：47 项全链路验收，覆盖部署就绪、
  账号实名、主交易闭环（含佣金与代扣核算）、纠纷开案到答辩、提现风控、
  上传能力 URL、越权边界、调度与告警指标、五条资金不变量、注销闸门。
- **DRILL-061（关闭）** 恢复演练补上 Postgres 路径，用与
  `backup.sh`/`restore.sh` **相同的命令与参数**（`pg_dump --clean --if-exists`
  + `DROP SCHEMA public CASCADE` + `psql -v ON_ERROR_STOP=1`）。

## 2. 实测

本环境装有 PostgreSQL 16.13，因此以下全部是**真跑过**的，不是推演：

| 项 | 结果 |
|---|---|
| Postgres 上 `alembic upgrade head` | 69 张表建成 |
| Postgres 上 `alembic check` | 无漂移（修正后） |
| Postgres 上 `scripts/smoke` | 20 项全过 |
| Postgres 上 `scripts/acceptance` | **47 项全过** |
| Postgres 上 `scripts/restore_drill` | 删 schema 后原样恢复，五不变量成立 |
| SQLite 全量回归 | 597 passed |

## 3. 已知缺口

- **DEP-071 `oneclick.sh` 的容器路径未实测。** 本环境没有 docker daemon，
  所以脚本的 compose 分支只做了语法检查与逻辑走查，
  `--verify-only` 与本地 Python 分支是实跑过的。首次在真实服务器上执行时
  请用 `--mode staging` 先试。
- **DEP-072 全量测试仍只在 SQLite 上跑。** 本批验证了核心路径在 Postgres 上
  可用（32 项抽样 + 47 项验收），但 597 个测试逐一在 Postgres 上跑一遍会显著
  拉长 CI。折中是 `postgres-acceptance` job 覆盖真实链路。
