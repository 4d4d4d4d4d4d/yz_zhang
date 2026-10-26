from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# 03.A 任务状态机
TASK_STATUSES = [
    "draft",  # 草稿
    "published",  # 已发布(招募中)
    "matched",  # 已匹配(合约签署/托管中)
    "in_progress",  # 执行中
    "pending_acceptance",  # 待验收
    "completed",  # 已完成
    "cancelled",  # 已取消
    "disputed",  # 纠纷中
]

# 状态流转白名单（TASK 状态机 P0：非法流转一律拒绝）
# draft→completed 仅用于容器任务（多人任务/被分解母任务）在全部子任务闭环后自动结项
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"published", "cancelled", "completed"},
    "published": {"matched", "cancelled", "completed"},
    "matched": {"in_progress", "cancelled", "disputed"},
    "in_progress": {"pending_acceptance", "cancelled", "disputed"},
    "pending_acceptance": {"completed", "in_progress", "disputed"},
    "disputed": {"completed", "cancelled", "in_progress"},
    "completed": set(),
    "cancelled": set(),
}

TASK_TYPES = ["service", "trade", "project", "event"]  # 服务/交易/项目/事件


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creator_id: Mapped[int] = mapped_column(Integer, index=True)
    executor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # 04 子任务树：parent_id + depends_on(兄弟任务 id 列表, DAG)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)

    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), index=True)  # 类目：保洁/跑腿/开发...
    task_type: Mapped[str] = mapped_column(String(20), default="service")
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    # AGT-030 结构化验收标准。auto 项由**平台**判定，不由执行方自报。
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    # IPC-001 知识产权归属。**无默认值**——发布时必须选一档。
    # 最容易犯的错是「默认归发布方」：对执行方不公平，对含第三方素材的
    # 交付物直接就是错的。
    ip_assignment: Mapped[str] = mapped_column(String(24), default="")
    # OUT-002 浮动对价的**确定上限**。不是比例、不是开放式承诺——
    # 有确定上限的附加对价是价款，随收益浮动的比例是分配，两者性质不同。
    bonus_cents: Mapped[int] = mapped_column(Integer, default=0)

    budget_cents: Mapped[int] = mapped_column(Integer, default=0)
    pricing: Mapped[str] = mapped_column(String(20), default="fixed")  # fixed 一口价 / bidding 竞价
    # CRED-005 执行者保证金（发布者设定，成交时冻结，闭环退还，违约罚没）
    deposit_cents: Mapped[int] = mapped_column(Integer, default=0)
    # TASK-007 多人任务：>1 时发布生成 N 个名额子任务，本任务成为容器
    people_needed: Mapped[int] = mapped_column(Integer, default=1)
    # SCN-107（167 号 spec）连续几天：名额 = 人数 × 天数，每个名额是某一天的一个人
    days: Mapped[int] = mapped_column(Integer, default=1)
    # 母任务：第一天；名额：这一天（北京时间的日期）
    work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # SCN-117（178 号 spec）每天几点到几点（北京时间 HH:MM，不跨夜）；空表示没写
    shift_start: Mapped[str] = mapped_column(String(5), default="")
    shift_end: Mapped[str] = mapped_column(String(5), default="")
    # GEO-021 行程共享（执行者开启后发布者可见最近打卡位置，任务结束即失效）
    trip_share_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # GEO：is_remote 线上任务不限地域；线下任务坐标 + 脱敏地址(公开) + 精确地址(成交后可见)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    city: Mapped[str] = mapped_column(String(50), default="", index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    address_hint: Mapped[str] = mapped_column(String(120), default="")  # 商圈级(GEO-004)
    address_exact: Mapped[str] = mapped_column(String(200), default="")
    # SCN-119（175 号 spec）替别人发单：发单人与服务对象分开。服务对象的称呼与在场联系方式**只给成交双方**
    # （与 address_exact 同一条 GEO-004）；发单前必须确认问过本人（记下时间）；结束 30 天后清掉联系方式
    on_behalf: Mapped[bool] = mapped_column(Boolean, default=False)
    recipient_label: Mapped[str] = mapped_column(String(20), default="")
    onsite_contact: Mapped[str] = mapped_column(String(40), default="")
    recipient_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # SCN-144（214 号 spec）服务对象是未成年人（陪练、看护、接送）：发单人确认是监护人或经监护人同意（记下时间），
    # 选「监护人在场」或「公开场所」；接这类单要持有审核通过的无犯罪记录证明。不存孩子的任何信息
    minor_involved: Mapped[bool] = mapped_column(Boolean, default=False)
    guardian_mode: Mapped[str] = mapped_column(String(20), default="")
    guardian_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # SCN-156（278 号 spec）发单人同意接单人把这一单（前后对比照等）放进作品集的时间；撤回则清空
    showcase_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # SCN-120（176 号 spec）一单多次上门：要上门几次、每次要做的事（清单）。0 / 空表示不按次回报
    visits_planned: Mapped[int] = mapped_column(Integer, default=0)
    visit_checklist: Mapped[list] = mapped_column(JSON, default=list)

    # TASK-008 可见范围：public 公开广场 / circle 仅圈层任务板
    visibility: Mapped[str] = mapped_column(String(12), default="public")
    circle_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # TASK-006 周期任务：none/weekly/monthly，闭环后自动生成下一期
    recurrence: Mapped[str] = mapped_column(String(10), default="none")
    recurred_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # AI-DEC-023（320 号 spec）招募多天没人报名时上次提醒发单人的时间（每 3 天最多提醒一次）
    stale_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_count: Mapped[int] = mapped_column(Integer, default=0)  # 验收驳回次数(TASK-033)
    # NTF-063 自动放款前的最后一次提醒发过没有（75 号 spec）。
    # 交付时那条「请在 N 天内验收」是开始时的闹钟；这一位保证到期前还会响一次，
    # 并且只响一次——跑一百遍 job 也不会给发布方发一百条。
    acceptance_reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class City(Base):
    """GEO-030 城市开通管理：线下任务仅可发布在已开通城市。"""

    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base):
    """OPS-004 任务类目（运营维护）：准入资质与启停。"""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    required_cert: Mapped[str] = mapped_column(String(30), default="")  # ACC-022 准入资质
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # SCN-181（307 号 spec）除 required_cert 外还要的资质（都要有）；空 = 只要 required_cert（与以前一样）
    extra_certs: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    # KB-062b（327 号 spec）这个类目的经验多久算「旧」（天）；空 = 平台默认 365 天
    experience_fresh_days: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Application(Base):
    """MATCH-001 报名/报价。"""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    applicant_id: Mapped[int] = mapped_column(Integer, index=True)
    bid_cents: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/accepted/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProgressLog(Base):
    """TASK-022 进度留痕 + GEO-020 打卡（作为履约与纠纷证据）。"""

    __tablename__ = "progress_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="note")  # note/checkin/delivery
    content: Mapped[str] = mapped_column(Text, default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # MOB-021 图片凭证（上传后的相对 URL 列表）：纠纷时最有力的证据往往是照片
    images: Mapped[list] = mapped_column(JSON, default=list)
    # SCN-120 上门回报（kind=visit）这一次做了清单里的哪几项
    checked: Mapped[list] = mapped_column(JSON, default=list)
    # SCN-124 打卡 / 带位置的上门回报离任务地点多远（米）。坐标在任务结束后清掉（GEO），距离留着当履约证据
    distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # SCN-192（317 号 spec）发单人对这一次上门回报的确认 / 异议（称重读数、做了什么，当场说清）；都空 = 还没表态
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    objection: Mapped[str] = mapped_column(String(300), default="", server_default="")


class Review(Base):
    """TASK-034/CRED-002 双向盲评：双方都提交或超时后才互相可见。"""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    reviewer_id: Mapped[int] = mapped_column(Integer)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    stars: Mapped[int] = mapped_column(Integer)  # 1..5
    tags: Mapped[list] = mapped_column(JSON, default=list)
    comment: Mapped[str] = mapped_column(String(500), default="")
    # CRED-002 真双盲：评分聚合延迟到公开时点结算，防 rating_avg 变化旁道泄露星级
    rating_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Bookmark(Base):
    """TASK-013 任务收藏（业界标配）：同一用户对同一任务唯一。"""

    __tablename__ = "task_bookmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SubtaskShare(Base):
    """AI-DEC-024（321 号 spec）跨子任务产出共享：前一步的交付人把交付说明与预览图开放给后一步的执行者。

    开不开放是交付人的权利，不是流程的便利：默认谁也看不到，交付人点了才开，随时可以收回（revoked_at）。
    开放给的是「后一步这个任务的执行者」这个位置：换了人，新的执行者看得到，交付人在列表里看得见现在是谁。"""

    __tablename__ = "subtask_shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_task_id: Mapped[int] = mapped_column(Integer, index=True)
    to_task_id: Mapped[int] = mapped_column(Integer, index=True)
    granted_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
