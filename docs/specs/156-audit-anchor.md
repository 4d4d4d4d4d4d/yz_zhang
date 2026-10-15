# 156 审计链头外部锚定

> 状态：本批实现（V182）。编号 ADMIN-063。
> 来源：149 号「没做的」ADMIN-063「链头外部锚定，这样连整条重算也能发现」；BACKLOG V182。
> 只增不减：审计哈希链的写入与自检规则（149 号）不变；自检结果多三个字段；存证链与公证 job 不变，只多一类存证事件。

## 0. 要解决的问题

- 149 号的哈希链能发现「改了一条没重算」「删了中间或末尾」「绕过接口插入」，但发现不了：**有库权限的人改了一条，再把整条链和链头都重算**——重算后的链完全自洽。
- 要防这一条，链头必须在别处留一份：别人改不到、或改了能被第三方看出来的地方。

## 1. 业界怎么做

- **定期把日志链头锚定到外部**：Crosby & Wallach 的防篡改日志要求定期把承诺（commitment）发布给审计方（<https://www.usenix.org/legacy/event/sec09/tech/full_papers/crosby.pdf>）；Certificate Transparency 用签名的树头（STH）做同样的事（RFC 6962，<https://www.rfc-editor.org/rfc/rfc6962>）。
- **司法存证 / 可信时间戳**：国内电子数据存证平台与可信时间戳（GB/T 20520）提供第三方背书。

## 2. 数据

不加表。锚点是存证链（`anchor_entries`）里的一类事件 `admin_audit.head`：`{head_audit_id, head_hash, count, at}`；存证链本身由既有的公证 job（`/anchors/jobs/notarize`）把链头交给存证机构，配置了真实存证机构时回执 `backed=true`。

## 3. 规则与接口

| 编号 | 内容 |
|---|---|
| ADMIN-063-1 | `POST /admin/jobs/anchor-audit-head`（调度表每天一次，`audit_head_anchor`）：把审计链头（最新一条的编号、哈希、条数、时间）写进存证链；链头没变就不重复写 |
| ADMIN-063-2 | 审计自检（`GET /admin/audit-log/verify`）逐个核对锚点：锚定的那一条现在的哈希必须等于锚定时的哈希，否则「链被整体重算过」；那一条不在了，也指出来 |
| ADMIN-063-3 | 自检结果多 `anchors_checked`、`last_anchor_audit_id`、`last_anchored_at` |

## 4. 两端

- **Web 管理后台「管理员审计日志 → 校验完整性」**：完整时多一句「存证锚点 N 个都对得上，最近一次锚定到 #X（时间）」或「还没有存证锚点（每天自动锚定一次）」；锚点对不上时出现在断点列表里。
- **App**：管理后台只在 Web，不涉及。

## 5. 隐私与边界

- 锚点只含编号、哈希、条数与时间，不含审计内容。
- 锚点能证明「锚定那一刻之前的链没被重算」；锚定之后到下一次锚定之间的改动，仍靠 149 号的逐条自检。存证链本身若被重算，要靠公证回执（`backed=true` 时）发现——缺省的本地公证不背书，回执里如实写明。

## 6. 闸门与红验

6 处变异全部变红（`scratchpad/mut182.py`）：

| 闸门 | 红验 |
|---|---|
| 链头没变不重复写 | 去掉 → `test_anchor_writes_the_head…` 红 |
| 整条重算被锚点发现 | 去掉哈希比对 → `test_recomputing_the_whole_chain…` 红 |
| 锚定的那一条被删被发现 | 去掉 → `test_deleting_the_anchored_row…` 红 |
| 锚点事件类型 | 写成别的事件 → 第一条红 |
| 锚点存的是链头哈希 | 存空 → 第一条红 |
| 进调度表 | 路径改坏 → `test_job_endpoint_is_scheduled…` 红 |
| Web 显示 | `web/src/AuditChain.test.tsx`（扩展了锚点那一句） |

## 7. 没做的

- **ADMIN-065 锚定频率可配**：现在每天一次；高风险时期可能想每小时。
