"""PWB 个人工作台的计算部分（116 号 spec）：进度、概览、例行任务排期与运行、助手拆清单。"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.modules.account.models import utcnow

from .models import WbItem, WbMemory, WbProject, WbRoutine, WbRoutineRun

TZ = ZoneInfo("Asia/Shanghai")
OPEN = ("todo", "doing", "blocked")
STATUS_NAMES = {"todo": "待办", "doing": "进行中", "blocked": "卡住", "done": "完成", "dropped": "放弃"}
# 关联平台任务时按平台状态换算进度：只读，平台那边是事实来源
PLATFORM_PROGRESS = {"draft": 0, "published": 0, "matched": 25, "in_progress": 50, "pending_acceptance": 80,
                     "disputed": 50, "completed": 100, "cancelled": 0}
PLATFORM_STATUS_NAMES = {"draft": "草稿", "published": "招募中", "matched": "已成交", "in_progress": "进行中",
                         "pending_acceptance": "待验收", "disputed": "纠纷中", "completed": "已完成", "cancelled": "已取消"}
STALE_DAYS = 7
MAX_FAILURES = 3
LIMITS = {"projects": 50, "items": 2000, "children": 50, "logs": 500, "memories": 20, "routines": 20}
GENERIC_STEPS = [
    ("明确目标与完成标准", "写下做到什么程度算完成"),
    ("准备所需资料与工具", "列出要用到的东西，缺的先补齐"),
    ("动手完成主体部分", "按计划推进，遇到卡点记进进展"),
    ("检查与收尾", "对照完成标准逐项核对，整理结果"),
]


def to_utc(dt: datetime | None) -> datetime | None:
    """入口：带时区的换成 UTC；朴素值视为 UTC（与全站 `iso()` 出口对称）。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def local(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(TZ)


def _back(dt_local: datetime) -> datetime:
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ 进度（PWB-003）
class ListCtx:
    """一页任务要的附加信息一次取齐（115 号闸门：查询次数不随条数增长）。"""

    def __init__(self, db: Session, items: list[WbItem]):
        ids = [i.id for i in items]
        self.children: dict[int, tuple[int, int]] = {}
        if ids:
            rows = (db.query(WbItem.parent_id, func.count(WbItem.id),
                             func.sum(case((WbItem.status == "done", 1), else_=0)))
                    .filter(WbItem.parent_id.in_(ids), WbItem.status != "dropped")
                    .group_by(WbItem.parent_id).all())
            self.children = {pid: (int(total), int(done or 0)) for pid, total, done in rows}
        linked = {i.linked_task_id for i in items if i.linked_task_id}
        self.tasks: dict[int, tuple[str, str]] = {}
        if linked:
            from app.modules.task.models import Task

            self.tasks = {t.id: (t.status, t.title) for t in
                          db.query(Task.id, Task.status, Task.title).filter(Task.id.in_(linked))}


def progress_of(item: WbItem, ctx: ListCtx) -> tuple[int, str]:
    total, done = ctx.children.get(item.id, (0, 0))
    if total:
        return round(done * 100 / total), "children"
    if item.linked_task_id and item.linked_task_id in ctx.tasks:
        return PLATFORM_PROGRESS.get(ctx.tasks[item.linked_task_id][0], 0), "platform"
    return (100 if item.status == "done" else item.progress), "manual"


def dump_item(item: WbItem, ctx: ListCtx) -> dict:
    from app.core.timefmt import iso

    progress, source = progress_of(item, ctx)
    total, done = ctx.children.get(item.id, (0, 0))
    linked = None
    if item.linked_task_id and item.linked_task_id in ctx.tasks:
        status, title = ctx.tasks[item.linked_task_id]
        linked = {"id": item.linked_task_id, "title": title, "status": status,
                  "status_name": PLATFORM_STATUS_NAMES.get(status, status)}
    return {
        "id": item.id, "project_id": item.project_id, "parent_id": item.parent_id,
        "title": item.title, "notes": item.notes, "status": item.status,
        "status_name": STATUS_NAMES.get(item.status, item.status), "priority": item.priority,
        "category": item.category, "due_at": iso(item.due_at), "remind_at": iso(item.remind_at),
        "progress": progress, "progress_source": source, "children_total": total, "children_done": done,
        "tags": item.tags or [], "linked_task": linked, "revision": item.revision,
        "created_at": iso(item.created_at), "updated_at": iso(item.updated_at),
        "completed_at": iso(item.completed_at),
    }


# ------------------------------------------------------------------ 概览（PWB-004）
def _platform_section(db: Session, user_id: int) -> dict:
    """平台上等我处理的事：个人门户要能一眼看到自己在平台上的协作进度。"""
    from app.modules.task.models import Application, Task

    pending = (db.query(Task.id, Task.title, func.count(Application.id))
               .join(Application, Application.task_id == Task.id)
               .filter(Task.creator_id == user_id, Task.status == "published", Application.status == "pending")
               .group_by(Task.id, Task.title).order_by(Task.id.desc()).limit(10).all())
    to_accept = (db.query(Task.id, Task.title).filter(Task.creator_id == user_id,
                 Task.status == "pending_acceptance").order_by(Task.id.desc()).limit(10).all())
    doing = (db.query(Task.id, Task.title, Task.status).filter(
        Task.executor_id == user_id, Task.status.in_(("matched", "in_progress", "pending_acceptance")))
        .order_by(Task.id.desc()).limit(10).all())
    return {
        "to_choose": [{"task_id": i, "title": t, "applicants": n} for i, t, n in pending],
        "to_accept": [{"task_id": i, "title": t} for i, t in to_accept],
        "executing": [{"task_id": i, "title": t, "status": s, "status_name": PLATFORM_STATUS_NAMES.get(s, s)}
                      for i, t, s in doing],
    }


def overview(db: Session, user_id: int, now: datetime | None = None) -> dict:
    now = now or utcnow()
    items = (db.query(WbItem).filter(WbItem.owner_id == user_id, WbItem.parent_id.is_(None))
             .order_by(WbItem.id.desc()).limit(LIMITS["items"]).all())
    ctx = ListCtx(db, items)
    loc = local(now)
    day_end = _back(loc.replace(hour=23, minute=59, second=59, microsecond=0))
    week_start = _back((loc - timedelta(days=loc.weekday())).replace(hour=0, minute=0, second=0, microsecond=0))
    stale_before = now - timedelta(days=STALE_DAYS)
    open_items = [i for i in items if i.status in OPEN]
    buckets = {
        "overdue": [i for i in open_items if i.due_at and i.due_at < now],
        "today": [i for i in open_items if i.due_at and now <= i.due_at <= day_end],
        "doing": [i for i in open_items if i.status == "doing"],
        "blocked": [i for i in open_items if i.status == "blocked"],
        "stale": [i for i in open_items if i.updated_at < stale_before],
        "done_this_week": [i for i in items if i.status == "done" and i.completed_at and i.completed_at >= week_start],
    }
    projects = db.query(WbProject).filter(WbProject.owner_id == user_id, WbProject.archived.is_(False)) \
        .order_by(WbProject.sort, WbProject.id).all()
    per = {}
    for i in items:
        if i.status == "dropped":
            continue
        t, d = per.get(i.project_id, (0, 0))
        per[i.project_id] = (t + 1, d + (1 if i.status == "done" else 0))
    return {
        "counts": {k: len(v) for k, v in buckets.items()} | {"open": len(open_items)},
        **{k: [dump_item(i, ctx) for i in v[:20]] for k, v in buckets.items()},
        "projects": [{"id": p.id, "name": p.name, "color": p.color, "total": per.get(p.id, (0, 0))[0],
                      "done": per.get(p.id, (0, 0))[1],
                      "progress": round(per[p.id][1] * 100 / per[p.id][0]) if per.get(p.id, (0, 0))[0] else 0}
                     for p in projects],
        "platform": _platform_section(db, user_id),
    }


def _titles(rows: list[dict], n: int = 3) -> str:
    names = "、".join(f"「{r['title']}」" for r in rows[:n])
    return names + ("等" if len(rows) > n else "")


def digest_text(ov: dict) -> str:
    c, p = ov["counts"], ov["platform"]
    parts = [f"今天到期 {c['today']} 项" + (f"：{_titles(ov['today'])}" if ov["today"] else ""),
             f"已逾期 {c['overdue']} 项" + (f"：{_titles(ov['overdue'])}" if ov["overdue"] else ""),
             f"进行中 {c['doing']} 项", f"卡住 {c['blocked']} 项"]
    if c["stale"]:
        parts.append(f"{c['stale']} 项超过 {STALE_DAYS} 天没有动静")
    plat = []
    if p["to_choose"]:
        plat.append(f"{len(p['to_choose'])} 单有人报名等你选人")
    if p["to_accept"]:
        plat.append(f"{len(p['to_accept'])} 单等你验收")
    if p["executing"]:
        plat.append(f"你在执行 {len(p['executing'])} 单")
    return "；".join(parts) + "。" + (("平台上：" + "，".join(plat) + "。") if plat else "")


def review_text(ov: dict) -> str:
    c = ov["counts"]
    done = ov["done_this_week"]
    return (f"本周完成 {c['done_this_week']} 项" + (f"：{_titles(done, 5)}" if done else "")
            + f"；逾期 {c['overdue']} 项；卡住 {c['blocked']} 项；还开着 {c['open']} 项。")


# ------------------------------------------------------------------ 例行任务（PWB-007）
def next_run(r: WbRoutine, after: datetime) -> datetime | None:
    """`after` 之后的下一次运行时间（UTC 朴素值）。时间按北京时间解释。"""
    if r.freq == "once":
        return r.run_at if r.run_at and r.run_at > after else None
    hh, mm = (int(x) for x in r.time_of_day.split(":"))
    loc = local(after)
    base = loc.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if r.freq == "daily":
        cand = base if base > loc else base + timedelta(days=1)
    elif r.freq == "weekly":
        cand = base + timedelta(days=(r.weekday - loc.weekday()) % 7)
        if cand <= loc:
            cand += timedelta(days=7)
    else:   # monthly：31 号在小月按月末算——「每月 31 号」不该在 2 月静默跳过
        def on(year, month):
            day = min(r.monthday, calendar.monthrange(year, month)[1])
            return base.replace(year=year, month=month, day=day)
        cand = on(loc.year, loc.month)
        if cand <= loc:
            y, m = (loc.year + 1, 1) if loc.month == 12 else (loc.year, loc.month + 1)
            cand = on(y, m)
    return _back(cand)


def missed_between(r: WbRoutine, start: datetime, now: datetime, cap: int = 100) -> int:
    """`start`（本该运行的那次）之后、`now` 之前还错过了几次。"""
    n, t = 0, start
    while n < cap:
        t = next_run(r, t)
        if t is None or t > now:
            break
        n += 1
    return n


def compose(db: Session, r: WbRoutine, now: datetime) -> str:
    if r.kind == "reminder":
        text = r.note or r.name
        if r.item_id:
            item = db.get(WbItem, r.item_id)
            if item is not None and item.owner_id == r.owner_id:
                text += f"（任务「{item.title}」，当前{STATUS_NAMES.get(item.status, item.status)}）"
        return text
    ov = overview(db, r.owner_id, now)
    return review_text(ov) if r.kind == "review" else digest_text(ov)


def run_routine(db: Session, r: WbRoutine, now: datetime, manual: bool = False) -> WbRoutineRun:
    """运行一次。失败不抛出：记一条失败，连续 3 次自动暂停并通知（不让坏掉的例行任务每分钟写一条失败）。"""
    from app.modules.notification.service import notify

    missed = 0 if manual or r.next_run_at is None else missed_between(r, r.next_run_at, now)
    try:
        with db.begin_nested():
            output = compose(db, r, now)
            if missed:
                output += f"（服务暂停期间错过了 {missed} 次，只补这一次）"
            notify(db, r.owner_id, "assistant", f"助手：{r.name}", output)
        status = "ok"
        r.failures = 0
    except Exception as exc:   # noqa: BLE001 —— 例行任务的失败要落库给人看，不能让整批 job 失败
        status, output = "failed", f"运行失败：{type(exc).__name__}"
        r.failures += 1
        if r.failures >= MAX_FAILURES:
            r.enabled = False
            notify(db, r.owner_id, "assistant", "例行任务已暂停",
                   f"「{r.name}」连续 {MAX_FAILURES} 次运行失败，已暂停。修改后重新开启即可。")
    run = WbRoutineRun(routine_id=r.id, owner_id=r.owner_id, status=status, output=output, started_at=now)
    db.add(run)
    r.last_run_at, r.last_status = now, status
    if not manual:
        r.next_run_at = next_run(r, now)
        if r.next_run_at is None:
            r.enabled = False
    db.add(r)
    return run


def run_due(db: Session, now: datetime | None = None, limit: int = 500) -> dict:
    """到点的例行任务与任务提醒。由 `/workbench/jobs/run-routines` 每分钟调用。"""
    from app.modules.notification.service import notify

    now = now or utcnow()
    due = (db.query(WbRoutine).filter(WbRoutine.enabled.is_(True), WbRoutine.next_run_at.isnot(None),
                                      WbRoutine.next_run_at <= now)
           .order_by(WbRoutine.next_run_at).limit(limit).all())
    ok = failed = 0
    for r in due:
        run = run_routine(db, r, now)
        ok, failed = (ok + 1, failed) if run.status == "ok" else (ok, failed + 1)
    items = (db.query(WbItem).filter(WbItem.remind_at.isnot(None), WbItem.remind_at <= now,
                                     WbItem.reminded_at.is_(None), WbItem.status.in_(OPEN))
             .order_by(WbItem.remind_at).limit(limit).all())
    for i in items:
        notify(db, i.owner_id, "assistant", f"提醒：{i.title}",
               (f"截止 {local(i.due_at):%m-%d %H:%M}。" if i.due_at else "") + (i.notes[:100] if i.notes else ""))
        i.reminded_at = now
        db.add(i)
    return {"routines_ok": ok, "routines_failed": failed, "reminders": len(items)}


# ------------------------------------------------------------------ 助手拆清单（PWB-005）
def breakdown(db: Session, item: WbItem) -> dict:
    """只出草稿。走既有分解网关：配了模型就由模型拆（带上记忆），否则查模板，再没有就给通用清单。"""
    from app.modules.decompose.llm import TemplateLLM, get_gateway

    gw = get_gateway()
    desc = item.notes or ""
    if not isinstance(gw, TemplateLLM):
        mem = [m.content for m in db.query(WbMemory).filter(WbMemory.owner_id == item.owner_id)
               .order_by(WbMemory.id).all()]
        if mem:
            desc += "\n\n（我的习惯与偏好：" + "；".join(mem) + "）"
    try:
        res = gw.expand(db, {"root": {"title": item.title, "description": desc, "category": item.category,
                                      "budget_cents": 0, "city": ""},
                             "path": [], "depth": 1, "node": None})
    except Exception:  # noqa: BLE001 —— 模型挂了也要给出一份能用的清单
        res = {"children": [], "source": "generic"}
    children = res.get("children") or []
    if not children or res.get("source") == "generic" or res.get("fallback"):
        return {"source": "generic", "steps": [{"title": t, "note": n} for t, n in GENERIC_STEPS]}
    steps = []
    for c in children[:LIMITS["children"]]:
        note = "；".join(x for x in (f"交付：{c['deliverable']}" if c.get("deliverable") else "",
                                    f"完成标准：{c['acceptance']}" if c.get("acceptance") else "") if x)
        steps.append({"title": c["title"][:200], "note": note[:500]})
    return {"source": res.get("source", "model"), "steps": steps}


def count(db: Session, model, owner_id: int, *extra) -> int:
    return db.query(func.count(model.id)).filter(model.owner_id == owner_id, *extra).scalar() or 0
