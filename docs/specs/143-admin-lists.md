
# 143 后台审计日志与提现复核台：筛选、总数、导出；导出时间写明时区

> 状态：本批实现（V171）。编号 ADMIN-061、PAY-043、TZ-068（审计日志导出部分）。
> 来源：台账 ADMIN-061「审计日志无分页/筛选/导出」、PAY-043「提现复核台无分页与筛选」、TZ-068「导出的 CSV/PDF 时间无时区标注」；BACKLOG V171。
> 只增不减：两个列表接口的响应体仍是数组、原有参数与默认行为不变（不带新参数时发出的请求与返回一字不差）；总条数放在响应头 `X-Total-Count`；旧 SDK 方法保留。

## 0. 要解决的问题

- 审计日志只能按「动作」过滤、一次 50 条、不知道一共多少条：要回答「上个月谁改过管理员角色」「谁批了那笔三万块」只能一页页翻；监管或内审要调取时只能截图。
- 提现复核台按申请先后排，没有筛选：风控岗想先看命中风控的、金额最大的，做不到；队列有多长也不知道。
- 已有的导出（一人公司底稿）时间列没有时区；审计日志导出如果照抄就会让人把 UTC 当成北京时间，差 8 小时。

## 1. 业界怎么做（带来源链接）

- **列表总数放响应头**：`X-Total-Count` 是常见约定（例如 json-server、多种 REST 框架的分页实现），不改变响应体形状，旧客户端不受影响；GitHub REST API 用 `Link` 头做分页（<https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api>）。
- **审计日志可检索、可导出、访问本身留痕**：NIST SP 800-92《Guide to Computer Security Log Management》要求日志可按时间、主体、事件类型检索，并保护日志的访问（<https://csrc.nist.gov/pubs/sp/800/92/final>）；这里导出动作本身也写进审计。
- **时间带时区**：ISO 8601 与 RFC 3339 都要求明确偏移；导出给人看的表格按业务所在时区换算并在表头写明。

## 2. 数据

无新表、无迁移。

## 3. 接口

| 编号 | 内容 |
|---|---|
| ADMIN-061a | `GET /admin/audit-log` 多 `admin_id`、`target_type`、`target_id`、`since`、`until`（带偏移的按 UTC 换算）、`q`（说明里包含）；响应头 `X-Total-Count` |
| ADMIN-061b | `GET /admin/audit-log/export`：同一套筛选，CSV（北京时间、表头写明「北京时间 UTC+8」、带管理员昵称），最多 1 万行，超出写明 `truncated` 与 `total`；**导出本身进审计**（行数与条件）；合规角色 |
| PAY-043 | `GET /wallet/withdraw-requests` 多 `user_id`、`min_amount_cents`、`flagged_only`（只看命中风控的）、`sort=oldest|largest`；响应头 `X-Total-Count`；财务角色 |
| TZ-068（部分） | `timefmt.export_time` 与 `EXPORT_TZ_LABEL`：导出用的唯一时间口径 |
| SDK | `adminAuditLogPage`、`exportAuditLog`、`withdrawRequestsPage`（读 `X-Total-Count`，老服务端没有这个头时 `total` 为 null）；`adminAuditLog`、`withdrawRequests` 兼容保留 |

## 4. 两端

- **Web 管理后台**：审计日志一块有动作、管理员编号、对象类型与编号、开始 / 结束日期（按北京时间整天）、说明包含；显示「第 N / M 页 · 共 X 条」与翻页；「导出 CSV」下载文件并说明时区、是否截断、导出已记入审计。
- 提现复核台：金额下限、只看命中风控的、先看金额大的；两个队列（待初审 / 待二次确认）各自的总数，超出本页时提示缩小条件。
- **App**：管理后台只在 Web，不涉及。

## 5. 隐私、授权与边界

- 审计日志与导出仅合规角色；提现复核仅财务角色（141 号）。
- 导出不含任何用户个人信息以外的新字段：审计说明本来就在后台可见。

## 6. 闸门与红验

11 处变异全部变红（`scratchpad/mut171.py`）：

| 闸门 | 红验 |
|---|---|
| 按管理员、时间段筛选 | 各去一处 → `test_audit_log_filters_and_total` 红 |
| 总条数 | 去掉响应头 → 同上红；SDK 不读头 → `AdminLists.test.tsx` 红 |
| 导出进审计、写明截断 | 各去一处 → `test_audit_export_labels_the_timezone…` 红 |
| 导出时间换成北京时间 | 不换算 → `test_export_time_is_beijing_time` 红 |
| 提现：只看命中风控、金额下限、先看大的 | 各去一处 → `test_withdraw_queue_filters_sort_and_total` 红 |
| 界面日期按北京时间整天 | 改成 UTC → `AdminLists.test.tsx` 红 |
| 原有行为 | `WithdrawReview.test.tsx`、`AdminOversight.test.tsx` 等原有用例一字未改照旧通过 |
| 登记 | 角色总表、后台入口表、SDK 分诊（旧方法写进兼容保留）、响应形状 `AuditLogExport` |

## 7. 没做的

- **TZ-069 其余导出的时区标注**：一人公司底稿（`/opc/export`）只有日期列，不受影响；合约导出、证据包里的时间仍是 ISO UTC（带 `Z`，机器可读但人看容易误读），逐个改成「北京时间 + 表头写明」排进待办。
- **ADMIN-062 审计日志的防篡改**：现在是普通表；做成哈希链或写入存证链（与影响力快照同一套）要先定保留期限。 → **已做**（V177，149 号 spec）。
- **PAY-047 提现复核台的批量操作**（原记作 PAY-044，与 75 号撞号，V215 改号）：大额提现要逐笔看，批量放行有风险，不做；批量驳回要先定话术口径。
