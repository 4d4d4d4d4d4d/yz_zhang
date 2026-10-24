"""JOB-001 定时任务的**唯一事实来源**（32 号 spec）。

此前 job 的路径与周期手抄在 `scripts/cron.py` 里，和端点定义分处两地。
结果对了一次就发现三处不一致：

- `/admin/jobs/reconcile`（资金对账，最高优先级告警）**不在调度表里**，
  而且它的鉴权是 `require_admin`——调度器根本调不动。这门生意最重要的
  那道安全网从来没有被架起来过。
- cron 调的是 `/jobs/expire-unsigned`，真实路径是
  `/contracts/jobs/expire-unsigned`。一直在打 404，超期合约的保证金
  一直冻着没解。
- `/jobz` 遍历 `JobLock` 表，**从未跑过的 job 根本没有行**，
  于是在监控里干脆不存在——专门用来发现「job 静默不跑」的监控，
  对最严重的那种静默完全免疫。

手抄的清单一定会漂移，区别只是什么时候被发现。所以现在只有这一份，
并且有测试从 FastAPI 路由表自动发现 job 端点与它双向核对（JOB-002）。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledJob:
    """一个定时任务。

    `path` 不含 API 前缀；`lock_name` 必须与端点上 `job_slot()` 的参数一致，
    否则 `/jobz` 会把同一个 job 认成两个。
    """

    path: str
    period_seconds: int
    lock_name: str
    purpose: str


# 周期的取值理由写在每条后面——不写的话，下一个人只能靠猜要不要改
JOBS: tuple[ScheduledJob, ...] = (
    ScheduledJob("/tasks/jobs/auto-accept", 300, "auto_accept",
                 "TASK-031 验收超时自动通过（拖着不验收＝变相欠薪）"),
    ScheduledJob("/tasks/jobs/expire-tasks", 600, "expire_tasks",
                 "TASK-030 过期任务自动下架"),
    ScheduledJob("/tasks/jobs/settle-reviews", 3600, "settle_reviews",
                 "CRED-002 双盲评价窗口到期结算"),
    ScheduledJob("/tasks/jobs/deadline-alerts", 3600, "deadline_alerts",
                 "TASK-032 临期提醒"),
    ScheduledJob("/contracts/jobs/expire-unsigned", 3600, "expire_unsigned",
                 "SC-012 超期未双签作废并**解冻执行者保证金**——"
                 "此前 cron 写的路径少了 /contracts 前缀，这个 job 从未跑过"),
    ScheduledJob("/disputes/jobs/escalate-overdue", 3600, "escalate_overdue",
                 "DSP-009 超 SLA 未结案的纠纷升级人审"),
    ScheduledJob("/openapi/jobs/purge-usage", 86400, "api_usage_purge",
                 "API-055 Key 用量记录只留 90 天（用量页最多看 90 天），一天清一次就够"),
    ScheduledJob("/openapi/jobs/remind-quota-requests", 3600, "quota_request_reminders",
                 "API-058 待批超过 48 小时的提额申请催运营（每笔一天一次）——接入方配额用完就 429，"
                 "申请躺着没人看等于业务停着（247 号 spec）"),
    ScheduledJob("/openapi/jobs/deliver-webhooks", 60, "deliver_webhooks",
                 "HOOK-002 Webhook 投递与指数退避重试；连续失败自动停用并通知拥有者"),
    ScheduledJob("/verify/jobs/expire-orders", 3600, "expire_verifications",
                 "VER-041 核验单超时未接单自动退款（已接单的不自动退——"
                 "钱退了人还在干是更糟的状态，那种走人工）"),
    ScheduledJob("/disputes/jobs/remind-response", 3600, "remind_response",
                 "DSPR-020 答辩期将届满而被诉方仍未陈述时提醒——"
                 "只在开案时响一次的闹钟，和没有闹钟差别不大"),
    ScheduledJob("/missions/jobs/tick-all", 300, "mission_tick_all",
                 "ORC 编排循环推进"),
    ScheduledJob("/tasks/jobs/purge-locations", 86400, "purge_locations",
                 "GEO 已结束任务的打卡坐标清理"),
    ScheduledJob("/anchors/jobs/notarize", 86400, "notarize",
                 "LAW-011 存证锚定：一天一次足够，区间越大回执越少也越便宜"),
    ScheduledJob("/events/jobs/drain", 120, "event_drain",
                 "EVT-021 事件补做：跑得勤一点，用户少收一条通知的窗口就短一点"),
    ScheduledJob("/events/jobs/purge", 86400, "event_purge",
                 "EVT-004 发件箱保留期清理"),
    ScheduledJob("/events/jobs/purge-security", 86400, "security_purge",
                 "SECEV-006 安全事件保留期清理"),
    ScheduledJob("/finance/jobs/remit-tax", 86400, "remit_tax",
                 "TAX-013 代扣税款缴库，与申报周期对齐"),
    ScheduledJob("/finance/jobs/remind-tax-remits", 3600, "tax_remit_reminders",
                 "PAY-042f 缴库草稿等确认超过 3 天催财务（每笔一天一次）"),
    ScheduledJob("/admin/jobs/remind-holiday-import", 86400, "holiday_import_reminders",
                 "ESCA-074 11 月到次年 1 月下一年放假安排没录时每周提醒主管导入"),
    ScheduledJob("/packs/jobs/remind-expiring", 86400, "pack_expiry_reminders",
                 "SCN-163 场景包知识 30 天内到期时直接提醒写包的运营（每个包一周一次）"),
    ScheduledJob("/knowledge/jobs/reindex", 3600, "kb_reindex",
                 "KB-011 向量索引增量重建：只补没有向量或模型已换的行"),
    ScheduledJob("/knowledge/jobs/cluster", 3600, "kb_cluster",
                 "KB-070 新经验归进子类：串行跑（并发更新同一子类的质心是静默错误的温床），"
                 "没标定阈值的大类原样等着，标定后下一轮重试"),
    ScheduledJob("/analytics/jobs/render-alerts", 3600, "render_alerts",
                 "APP-097 页面坏的人多了提醒运营：一小时一次足够——窗口是 24 小时、同一页只提醒一次，"
                 "跑得再勤也只是早几十分钟知道"),
    ScheduledJob("/influence/jobs/snapshot", 86400, "influence_snapshot",
                 "INF-106 影响力快照：Merkle 根锚定进存证哈希链；到期的类目担保释放"),
    ScheduledJob("/gig/jobs/purge-expired", 3600, "gig_purge",
                 "GIG-101 过期的「现在有空」连同粗化位置一起删：位置不留着过夜（读的时候也会顺手删）"),
    ScheduledJob("/gig/jobs/route-push", 600, "gig_route_push",
                 "SCN-140 常用路线到点前推顺路的名额：出发前一小时内推一次，十分钟一轮足够早"),
    ScheduledJob("/workbench/jobs/run-routines", 60, "wb_routines",
                 "PWB-007 个人工作台的例行任务与到点提醒：用户设的是「9:00」，跑得慢一分钟就晚一分钟"),
    ScheduledJob("/tasks/jobs/remind-acceptance", 3600, "remind_acceptance",
                 "NTF-063 自动放款前的最后一次提醒——交付时那条是开始时的闹钟，"
                 "而 N 天后钱就放出去了，放款不可逆"),
    ScheduledJob("/teams/jobs/remind-approvals", 3600, "team_approval_reminders",
                 "TEAM-063 支出审批催办与超时关闭——此前躺三个月也不会有人"
                 "被提醒第二次，而发起人等的是一件不会到来的事"),
    ScheduledJob("/wallet/jobs/remind-second-approval", 3600, "withdraw_second_reminders",
                 "PAY-044 人审提现催办与超时退回——V99 的双人确认加了一个新卡点，"
                 "卡点没有兜底就是新的「钱能进不能出」"),
    ScheduledJob("/admin/jobs/remind-review-queues", 3600, "review_queue_reminders",
                 "QUEUE-011/012 人审队列积压催办——队列里躺着的东西不会主动发声，"
                 "而运营是「想起来才去看」；超过 SLA 时提交方也会收到一次告知"),
    ScheduledJob("/admin/jobs/anchor-audit-head", 86400, "audit_head_anchor",
                 "ADMIN-063 审计链头每天写进存证链——只有链本身，数据库管理员可以整条重算；"
                 "锚点在存证链上（再由公证背书），重算过的链对不上锚点（156 号 spec）"),
    ScheduledJob("/admin/jobs/send-scheduled-announcements", 300, "scheduled_announcements",
                 "NTF-064 定时公告到点发出——不跑的话「定时」就是一个永远不会到来的时间（151 号 spec）"),
    ScheduledJob("/admin/jobs/remind-legal-reviews", 86400, "legal_reviews",
                 "LAW-062 法律条目复核提醒——法规会改，过了复核日期问答就停用这一条；到期前 30 天、到期当天"
                 "各叫一次合规，不跑的话条目会悄悄停用而没人知道（169 号 spec）"),
    ScheduledJob("/admin/jobs/escalate-tickets", 3600, "ticket_escalations",
                 "ESCA-051 工单超时逐级升级——汇总通知发给全体管理员等于谁都没被点名；"
                 "到时限叫醒接手的客服，到升级线叫醒主管并告诉提单人（150 号 spec）"),
    ScheduledJob("/wallet/jobs/resolve-payouts", 600, "payout_resolve",
                 "CONC-067 出款两阶段之后，银行结果不明的出款单停在 sending：钱冻结着、"
                 "用户在等。按同一个单号重试（不会打两次），十分钟一次"),
    ScheduledJob("/wallet/jobs/purge-idempotency", 86400, "idempotency_purge",
                 "FIN-071 幂等记录过期清理——过期判断在读的时候已生效，"
                 "这个 job 只让表不无限增长，一天一次足够"),
    ScheduledJob("/admin/jobs/reconcile", 86400, "reconcile",
                 "PAY-006/008 五条资金不变量日终对账，不平即开差错工单并告警。"
                 "**此前它不在调度表里、且要求管理员登录，从未自动执行过**"),
)

BY_LOCK = {j.lock_name: j for j in JOBS}
