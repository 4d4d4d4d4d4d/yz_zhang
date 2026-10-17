"""埋点漏斗、搜索热词、邀请裂变归因（13.C / SRCH-003 / CNT-022）。"""
import re

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.core.config import settings

from app.core.events import subscribe

from .models import AnalyticsEvent, SearchQuery


def track(db: Session, name: str, user_id=None, ref_type="", ref_id=None) -> None:
    db.add(AnalyticsEvent(name=name, user_id=user_id, ref_type=ref_type, ref_id=ref_id))


# PRIV-060 身份标识类的搜索词**根本不记**——数据最小化在写入时做，
# 而不是存下来再在读取时过滤（存下来的东西迟早会从别的口子出去）。
# 迁移 c1d220260006 里有同样的一份（迁移不 import 应用代码），一致性有测试钉着。
PII_PATTERNS = (
    r"(?<!\d)1[3-9]\d{9}(?!\d)",                 # 手机号
    r"(?<!\d)\d{17}[\dXx](?![\dXx])",            # 18 位身份证号
    r"(?<!\d)\d{15}(?!\d)",                      # 15 位身份证号
    r"[\w.+-]+@[\w-]+\.[\w.-]+",                 # 邮箱
)
_PII = [re.compile(p) for p in PII_PATTERNS]


def looks_like_pii(term: str) -> bool:
    return any(p.search(term) for p in _PII)


def log_search(db: Session, term: str, user_id: int | None = None) -> None:
    """记一次搜索，供热词与联想用。

    **不记的两类**：带身份标识的（手机号、证件号、邮箱）与过不了内容审核的。
    前者是隐私——此前它们被原样存下，再原样公开给任何人；后者是防投毒——
    此前任何人反复搜同一句广告，就能把它推上公开的热词榜。
    """
    from app.modules.task.service import machine_review

    term = term.strip()[:100]
    if not term or looks_like_pii(term) or machine_review(term, db):
        return
    db.add(SearchQuery(term=term, user_id=user_id))


def _public_terms(db: Session, prefix: str, limit: int) -> list[tuple[str, int]]:
    """公开的热词：**至少 N 个不同的人**搜过，且（按当前规则）过得了审核。

    审核在读取时再过一遍：词是很久以前记下的，而审核规则会更新。
    返回的计数是**人数**，不是次数——次数可以被一个人刷出来。
    """
    from app.modules.task.service import machine_review

    users = func.count(distinct(SearchQuery.user_id))
    query = db.query(SearchQuery.term, users.label("u")).filter(SearchQuery.user_id.isnot(None))
    if prefix:
        # autoescape：用户打一个 % 不该匹配到所有词
        query = query.filter(SearchQuery.term.startswith(prefix, autoescape=True))
    rows = (
        query.group_by(SearchQuery.term)
        .having(users >= settings.SEARCH_PUBLIC_MIN_USERS)
        .order_by(users.desc(), SearchQuery.term)
        .limit(limit * 3)
        .all()
    )
    # CONC-067 读完就把连接还回去：下面每个词各一次内容安全调用，不能挂着事务挨个等
    out = [(t, u) for t, u in rows if not looks_like_pii(t) and not machine_review(t, db)]
    return out[:limit]


def trending_terms(db: Session, limit: int = 10) -> list[dict]:
    return [{"term": t, "count": u} for t, u in _public_terms(db, "", limit)]


def suggest_terms(db: Session, prefix: str, limit: int = 8) -> list[str]:
    return [t for t, _ in _public_terms(db, prefix, limit)]


def _count(db: Session, name: str) -> int:
    return db.query(AnalyticsEvent).filter(AnalyticsEvent.name == name).count()


def funnels(db: Session) -> dict:
    """13.C 发布漏斗 + 接单漏斗（P0）。用任务/合约状态直接聚合，稳健于埋点缺失。"""
    from app.modules.contract.models import Contract
    from app.modules.task.models import Application, Task

    total_tasks = db.query(Task).filter(Task.parent_id.is_(None)).count()
    published = db.query(Task).filter(Task.parent_id.is_(None), Task.status != "draft").count()
    matched = (
        db.query(Task)
        .filter(Task.parent_id.is_(None),
                Task.status.in_(["matched", "in_progress", "pending_acceptance",
                                 "completed", "disputed"]))
        .count()
    )
    completed = db.query(Task).filter(Task.parent_id.is_(None), Task.status == "completed").count()

    applications = db.query(Application).count()
    accepted = db.query(Application).filter(Application.status == "accepted").count()
    contracts_done = db.query(Contract).filter(Contract.status == "released").count()

    def rate(a, b):
        return round(a / b, 3) if b else 0.0

    return {
        "publish_funnel": {
            "created": total_tasks,
            "published": published,
            "matched": matched,
            "completed": completed,
            "publish_rate": rate(published, total_tasks),
            "match_rate": rate(matched, published),
            "complete_rate": rate(completed, matched),
        },
        "worker_funnel": {
            "applications": applications,
            "accepted": accepted,
            "settled": contracts_done,
            "accept_rate": rate(accepted, applications),
        },
        "custom_events": {
            e.name: c
            for e, c in db.query(AnalyticsEvent, func.count(AnalyticsEvent.id))
            .group_by(AnalyticsEvent.name)
            .all()
        },
    }


# ---------- CNT-022 邀请裂变：首单闭环 → 奖励邀请人 ----------
REFERRAL_BONUS = 5  # 信用分奖励


def _on_task_completed(db: Session, payload: dict) -> None:
    from app.modules.account import service as credit
    from app.modules.account.models import User
    from app.modules.task.models import Task

    task = db.get(Task, payload["task_id"])
    if not task or not task.executor_id:
        return
    executor = db.get(User, task.executor_id)
    if not executor or not executor.referred_by or executor.referral_rewarded:
        return
    # 被邀请人完成首单 → 邀请人得信用奖励 + 现金奖励（GRW-012，每人一次）
    inviter = db.get(User, executor.referred_by)
    if inviter:
        credit.adjust_credit(db, inviter.id, REFERRAL_BONUS)
    from app.modules.growth import service as growth

    # 现金奖励由 growth 负责：仅一级、反作弊命中转人工、平台账户出资
    growth.grant_referral(db, executor)


def register_event_handlers() -> None:
    subscribe("task.completed", _on_task_completed, retry=True)


# ---------- APP-094 页面渲染出错的上报（184 号 spec） ----------
# 两端的错误边界接住一页 / 一屏的渲染错误后报一条：只有平台、页面（归一化的路径或屏名）、错误类型，
# 不带错误内容、不带页面数据（那里面可能有个人信息，SEC-065）。同一人同一页同类错误一分钟内只记一次。
RENDER_PREFIX = "render_failed"
_PAGE = re.compile(r"^[a-z0-9/:_-]{1,20}$")
_KIND = re.compile(r"^[A-Za-z]{1,30}$")
RENDER_DEDUP_SECONDS = 60
# 没登录的上报全站每分钟最多记这么多条：页面名可以随便编，不设顶就能把表灌满
RENDER_ANON_PER_MINUTE = 100


def report_render_error(db: Session, user_id, platform: str, page: str, kind: str) -> bool:
    from datetime import timedelta

    from app.modules.account.models import utcnow

    # 路径里的数字一律换成 :id——id、手机号、订单号都不进库（客户端也会这样归一，服务端再兜一次）
    page = re.sub(r"\d+", ":id", page or "")
    page = page if _PAGE.fullmatch(page) else "other"
    kind = kind if _KIND.fullmatch(kind or "") else "Error"
    name = f"{RENDER_PREFIX}:{platform}:{kind}"
    since = utcnow() - timedelta(seconds=RENDER_DEDUP_SECONDS)
    q = db.query(AnalyticsEvent.id).filter(AnalyticsEvent.name == name, AnalyticsEvent.ref_type == page,
                                           AnalyticsEvent.created_at >= since)
    q = q.filter(AnalyticsEvent.user_id == user_id) if user_id is not None else q.filter(AnalyticsEvent.user_id.is_(None))
    if q.first():
        return False
    if user_id is None and db.query(func.count(AnalyticsEvent.id)).filter(
            AnalyticsEvent.name.like(f"{RENDER_PREFIX}:%"), AnalyticsEvent.user_id.is_(None),
            AnalyticsEvent.created_at >= since).scalar() >= RENDER_ANON_PER_MINUTE:
        return False
    track(db, name, user_id, page)
    return True


def render_errors(db: Session, days: int) -> list[dict]:
    """近 N 天哪一页常坏：按平台 × 页面 × 错误类型数次数、不同的人数、最近一次（只给运营看聚合）。"""
    from datetime import timedelta

    from app.core.timefmt import iso
    from app.modules.account.models import utcnow

    since = utcnow() - timedelta(days=days)
    rows = (db.query(AnalyticsEvent.name, AnalyticsEvent.ref_type, func.count(AnalyticsEvent.id),
                     func.count(distinct(AnalyticsEvent.user_id)), func.max(AnalyticsEvent.created_at))
            .filter(AnalyticsEvent.name.like(f"{RENDER_PREFIX}:%"), AnalyticsEvent.created_at >= since)
            .group_by(AnalyticsEvent.name, AnalyticsEvent.ref_type).all())
    out = []
    for name, page, n, people, last in rows:
        _, platform, kind = name.split(":", 2)
        out.append({"platform": platform, "page": page, "kind": kind, "count": n, "people": people, "last_at": iso(last)})
    return sorted(out, key=lambda r: (-r["count"], r["platform"], r["page"]))
