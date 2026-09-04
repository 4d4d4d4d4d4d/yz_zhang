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
    ScheduledJob("/admin/jobs/reconcile", 86400, "reconcile",
                 "PAY-006/008 五条资金不变量日终对账，不平即开差错工单并告警。"
                 "**此前它不在调度表里、且要求管理员登录，从未自动执行过**"),
)

BY_LOCK = {j.lock_name: j for j in JOBS}
