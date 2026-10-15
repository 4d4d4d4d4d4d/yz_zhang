# 149 审计日志防篡改：哈希链与自检

> 状态：本批实现（V177）。编号 ADMIN-062。
> 来源：143 号「没做的」——合规调取时要能证明日志没被改过；BACKLOG V177。
> 只增不减：审计日志的列表、筛选、导出、写入调用点（`record_audit`）都不变；只是每条多了两列，多了一张链头表和一个自检接口。
> 写明的行为变化：审计必须经由 `record_audit` 写入；直接往 `admin_audits` 插的行没有哈希，自检会把它当作断点指出来。

## 0. 要解决的问题

- 审计日志（OPS-012）的承诺是「不可抵赖」。在 V177 之前它只是一张普通表：有库权限的人改一条说明、删一条「谁批了那笔三万块」，事后没有任何办法知道。
- 监管或审计师调取时，我们拿得出导出文件（143 号），但拿不出「这份文件没被动过」的证据。

## 1. 业界怎么做（带来源链接）

- **哈希链（hash chain）**：每条日志的哈希包含上一条的哈希，改或删任何一条都会让其后的链对不上。这是安全日志防篡改的标准做法，见 Schneier & Kelsey, *Secure Audit Logs to Support Computer Forensics*（ACM TISSEC 1999，<https://www.schneier.com/academic/archives/1999/05/secure_audit_logs_to.html>）。
- **链头 / 检查点**：单纯的链发现不了「删掉最后几条」，所以要单独记最新一条的编号与哈希（Crosby & Wallach, *Efficient Data Structures for Tamper-Evident Logging*，USENIX Security 2009，<https://www.usenix.org/legacy/event/sec09/tech/full_papers/crosby.pdf>）。
- **外部锚定**：库管理员可以把整条链重算，所以成熟做法会把链头哈希定期写到外部（时间戳服务、存证链）。本批没做，见第 7 节。
- 国内要求：《网络安全法》第二十一条要求留存网络日志不少于六个月；等保 2.0（GB/T 22239-2019）安全审计条款要求「对审计记录进行保护……避免受到未预期的删除、修改或覆盖」。

## 2. 数据（迁移 `c1d220260027`，SQLite 与 Postgres 都验过）

| 表 | 字段 |
|---|---|
| `admin_audits`（加列） | `prev_hash`（上一条的哈希）、`hash`（本条哈希，有索引）；旧记录默认空串 |
| `audit_chain_head`（新表，只有一行） | `last_audit_id`、`last_hash`、`count` |

哈希 = sha256(上一条哈希 | 管理员编号 | 动作 | 对象类型 | 对象编号 | 说明 | 时间的 ISO 串)。

## 3. 规则与接口

| 编号 | 内容 |
|---|---|
| ADMIN-062-1 | `record_audit` 改为经 `audit_chain.append` 写入：锁住链头（`SELECT … FOR UPDATE`，并发写也排成一条链）、算哈希、写入、更新链头，同一个事务 |
| ADMIN-062-2 | `GET /admin/audit-log/verify`（合规角色）：从链上第一条走到链头，返回 `ok`、走过的条数、链头编号与哈希、不在链上的旧记录条数、最多 20 处断点（编号 + 人话原因） |
| ADMIN-062-3 | 能指出的四种断点：内容被改（本条重算对不上）、中间被删或替换（上一条哈希对不上）、末尾被删（链头对不上）、绕过接口插入（链中间出现没有哈希的行） |
| ADMIN-062-4 | V177 之前的旧记录在链开始之前，不算断点，单独计数（`legacy_unchained`） |
| ADMIN-062-5 | 自检本身也进审计（`verify_audit_log`，写明完整还是有断点、检查了多少条），并且在链上 |

## 4. 两端

- **Web 管理后台「管理员审计日志」**：新增「校验完整性」按钮。完整时说「链上 N 条逐条对得上，最新一条是 #X」，并单列旧记录条数；有断点时说「日志可能被改过或删过，请保留现场，交合规负责人和数据库管理员核查」，逐条列出编号与原因。
- **App**：管理后台只在 Web，不涉及。

## 5. 隐私、授权与边界

- 自检只读审计表，返回的是编号与原因，不返回说明全文以外的个人信息。
- 只有合规角色能调（141 号角色总表已登记）；超级管理员按规则也能调。
- 这是**内部防篡改**：能发现「改了没重算」，发现不了「有库权限的人把整条链重算」。后者要靠外部锚定（第 7 节）。

## 6. 闸门与红验

7 处变异全部变红（`scratchpad/mut177.py`）：

| 闸门 | 红验 |
|---|---|
| 哈希覆盖说明字段 | 从哈希里去掉说明和后面的字段 → `test_hash_covers_every_field`、`test_editing_a_row_is_detected` 红 |
| 中间删除可发现 | 去掉「上一条哈希」比较 → `test_deleting_a_middle_row_is_detected` 红 |
| 末尾删除可发现 | 去掉链头比较 → `test_deleting_the_tail_is_detected_by_the_head` 红 |
| 绕过接口插入可发现 | 链中间无哈希行也当旧记录 → `test_a_row_inserted_around_the_interface_is_detected` 红 |
| 每条接上一条 | 写入时不取链头 → `test_each_row_links_to_the_previous_one` 红 |
| 只给合规 | 放宽到财务 → `test_verify_endpoint_is_compliance_only…` 红 |
| 自检进审计 | 去掉 → 同上红 |
| Web 说清结论与怎么办 | `web/src/AuditChain.test.tsx` |
| 原有行为 | `test_admin_lists.py`、`test_admin_audit.py`、`test_admin_roles.py` 照旧通过 |

## 7. 没做的

- **ADMIN-063 链头外部锚定**：每天把链头哈希写进存证链（V152 已有链上快照能力）或可信时间戳服务，这样连「整条重算」也能发现。 → **已做**（V182，156 号 spec）。
- **ADMIN-064 旧记录补链**：V177 之前的旧记录现在只计数不校验；可以一次性按编号顺序补成链的前缀（要有人确认那一刻的库是可信的）。
