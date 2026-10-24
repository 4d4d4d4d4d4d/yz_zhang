"""KB-080~089 经验要变成能被调用的工具（109 号 spec，设计见 95 号）。

用户 2026-10-10：「攒经验完全可以作为检索数据库或者 skilltool 工具给后续复用」。

此前的「复用」只有一种：经验以文本拼进分解提示词，模型读到它。平台不知道哪条经验
被用了、用了之后结果是好是坏——**单向、不计量、不可验证**。

三层：样本 → 子类（V134）→ **可复用单元**（这里）。蒸馏这一步不能跳：子类是统计描述，
工具需要确定的输入输出——把子类直接当工具，等于让 Agent 在运行时自己决定走哪条分歧。

四条硬规则：

- **注册门槛**（KB-080a）：来源、适用条件（**含排除条件**）、验证状态、两个授权位，缺一不得注册。
  来源样本必须**双方都同意了经验复用**（KB-002：个案引用要双方授权）。
- **计量**（KB-083）：每次使用记一条：哪个单元的哪个版本、什么场景、谁调的。
- **结果回流**（KB-084）：用过之后那一单闭环了没有、返工了没有。返工与失败多了，单元自己转待复核——
  **只统计成功的系统学不会任何东西。**
- **撤回真的生效**（KB-089）：贡献者撤回后，样本退出子类统计、单元转待复核、草稿标出来源已撤回。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request, conflict, not_found
from app.core.timefmt import iso
from app.modules.account.models import utcnow

from .models import KnowledgeCard, KnowledgeCluster, ReusableUnit, UnitInvocation

KINDS = ("price_hint", "checklist", "procedure", "skill_tool")
KIND_LABEL = {"price_hint": "报价与工期提示", "checklist": "验收清单",
              "procedure": "分解流程", "skill_tool": "可执行工具"}
# 只读单元：退化态下仍可用；skill_tool 不行（95 号第 6 节）
READ_ONLY = ("price_hint", "checklist", "procedure")
# 平台内置、可被注册成 skill_tool 的工具。实现在 tools.py（AST 闸门：不许碰钱、签约、权益）
TOOLS = {
    "acceptance_report_draft": {
        "label": "按验收清单生成验收报告草稿",
        "reads": ["task", "unit.checklist"],
        "writes": ["draft"],
        "spends": False,
        "messages": False,
    },
}


# ------------------------------------------------------------------ 授权
def _reuse_ok(db: Session, user_id: int | None) -> bool:
    from app.modules.legal.consent import has_consent

    return bool(user_id) and has_consent(db, user_id, "experience_reuse")


def _parties(db: Session, card: KnowledgeCard) -> list[int]:
    from app.modules.task.models import Task

    task = db.get(Task, card.source_task_id) if card.source_task_id else None
    if task is None:
        return []
    return [u for u in (task.creator_id, task.executor_id) if u]


def _consented_samples(db: Session, cluster_id: int) -> list[KnowledgeCard]:
    """能作来源的样本：已并入这个子类、且**双方**都同意了经验复用。"""
    cards = (db.query(KnowledgeCard)
             .filter(KnowledgeCard.cluster_id == cluster_id, KnowledgeCard.cluster_state == "assigned")
             .order_by(KnowledgeCard.id).all())
    out = []
    for c in cards:
        parties = _parties(db, c)
        if parties and all(_reuse_ok(db, u) for u in parties):
            out.append(c)
    return out


def contributors(db: Session, unit: ReusableUnit) -> list[dict]:
    """KB-085 受益贡献者：单元 → 样本 → 任务双方，**只列当前仍同意的人**。"""
    from app.modules.account.models import User

    seen: dict[int, str] = {}
    for c in db.query(KnowledgeCard).filter(KnowledgeCard.id.in_(unit.sample_ids or [-1])):
        for uid in _parties(db, c):
            if uid not in seen and _reuse_ok(db, uid):
                u = db.get(User, uid)
                if u is not None and not u.is_deleted:
                    seen[uid] = u.nickname
    return [{"user_id": k, "nickname": v} for k, v in sorted(seen.items())]


# ------------------------------------------------------------------ 蒸馏（KB-080）
def distill(db: Session, cluster_id: int, kind: str, title: str, applicability: dict,
            scope: str, reuse_license: bool, train_license: bool, admin_id: int,
            tool: str = "", content_override: dict | None = None) -> ReusableUnit:
    from . import clusters

    if kind not in KINDS:
        raise bad_request("单元类型只能是：报价提示 / 验收清单 / 分解流程 / 可执行工具", "unit_kind_invalid")
    cluster = db.get(KnowledgeCluster, cluster_id)
    if cluster is None or cluster.status != "active":
        raise not_found("子类不存在或已停用")
    exclusions = [str(x).strip() for x in (applicability.get("exclusions") or []) if str(x).strip()]
    if not exclusions:
        # 只说「适用于什么」的单元，会在它不适用的场合被照样调用
        raise bad_request("必须写明排除条件：什么情况下**不该**用这个单元", "unit_exclusions_required")
    if scope != "platform":
        # 「仅自己 / 项目内」要先有归属对象（谁的、哪个项目的）才能被执行，而单元表里还没有这两个字段。
        # 收下却执行不了的范围，等于把私有单元公开给所有人——所以只开放全平台。
        # KB-093（309 号 spec）定下来：单元是从多人的样本里蒸馏的，「仅自己」没有归属对象，也不需要——
        # 只想自己用的经验本来就有地方放（个人知识库、「我的方法」，只有本人能看）；「项目内」等项目的定义（KB-093b）
        if scope == "private":
            raise bad_request("经验单元是从多人的样本里蒸馏出来给大家复用的，没有「仅自己」这一档：只想自己用的经验，"
                              "请记在个人知识库（笔记）或「我的方法」里，那里本来就只有你能看", "unit_scope_invalid")
        raise bad_request("「项目内」范围还不开放（要先定项目指协作空间还是母任务）：先选「全平台」，"
                          "或者先不注册这个单元", "unit_scope_invalid")
    samples = _consented_samples(db, cluster.id)
    if not samples:
        raise conflict("这个子类里没有双方都同意经验复用的样本——没有可回溯的来源，不能注册单元",
                       "unit_no_consented_source")
    view = clusters.view(db, cluster, detail=True)
    content = _content_for(kind, view, tool, content_override)
    manifest, cost = {}, 0
    if kind == "skill_tool":
        manifest = {"tool": tool, **TOOLS[tool]}
        cost = settings.KB_TOOL_COST_CENTS
    unit = ReusableUnit(
        cluster_id=cluster.id, kind=kind, title=title.strip()[:120] or f"{cluster.label}·{KIND_LABEL[kind]}",
        content=content,
        applicability={"category": cluster.category,
                       "cities": [str(c) for c in (applicability.get("cities") or [])],
                       "budget_min_cents": applicability.get("budget_min_cents"),
                       "budget_max_cents": applicability.get("budget_max_cents"),
                       "exclusions": exclusions},
        sample_ids=[c.id for c in samples],
        validation={"status": "unvalidated", "uses": 0, "closed": 0, "reworked": 0, "failed": 0},
        scope=scope, reuse_license=bool(reuse_license), train_license=bool(train_license),
        manifest=manifest, est_cost_cents=cost, created_by=admin_id,
    )
    db.add(unit)
    db.flush()
    return unit


def _content_for(kind: str, view: dict, tool: str, override: dict | None) -> dict:
    steps = [s["title"] for s in view.get("consensus_steps", [])]
    if kind == "price_hint":
        if view["few_samples"] or view["price_p50_cents"] is None:
            raise conflict("这个子类样本太少，不能产出报价提示（单样本的中位数不是统计量）",
                           "unit_too_few_samples")
        return {"p50_cents": view["price_p50_cents"], "p90_cents": view["price_p90_cents"],
                "duration_p50_days": view["duration_p50_days"], "sample_count": view["sample_count"],
                "as_of": view["last_sample_at"]}
    if kind in ("checklist", "skill_tool", "procedure") and not steps and not (override or {}).get("steps"):
        raise conflict("这个子类还没有共识流程（至少两个任务出现过的步骤），产不出清单或流程",
                       "unit_no_consensus")
    if kind == "checklist":
        return {"items": [f"确认已完成：{s}" for s in steps]}
    if kind == "procedure":
        given = (override or {}).get("steps")
        rows = given or [{"title": s} for s in steps]
        n = len(rows)
        out = []
        for i, r in enumerate(rows):
            title_ = str(r.get("title", "")).strip()
            if not title_:
                raise bad_request("流程的每一步都要有名字", "unit_step_title_required")
            out.append({
                "title": title_,
                "deliverable": str(r.get("deliverable") or f"「{title_}」完成的凭证（照片、文件或记录）"),
                "acceptance": str(r.get("acceptance") or f"发布方确认「{title_}」已按约定完成"),
                "budget_ratio_bps": int(r.get("budget_ratio_bps") or (10000 // n + (10000 % n if i == n - 1 else 0))),
                "depends_on": [i - 1] if i > 0 else [],
            })
        return {"steps": out}
    if kind == "skill_tool":
        if tool not in TOOLS:
            raise bad_request(f"平台没有这个工具：{tool}", "unit_tool_unknown")
        return {"tool": tool, "checklist": [f"确认已完成：{s}" for s in steps]}
    raise AssertionError(kind)


# ------------------------------------------------------------------ 读与用（KB-083/086/087）
def applies_to(unit: ReusableUnit, category: str, city: str, budget_cents: int) -> bool:
    a = unit.applicability or {}
    if a.get("category") and a["category"] != category:
        return False
    if a.get("cities") and city not in a["cities"]:
        return False
    if a.get("budget_min_cents") is not None and budget_cents < a["budget_min_cents"]:
        return False
    if a.get("budget_max_cents") is not None and budget_cents > a["budget_max_cents"]:
        return False
    return True


def usable(unit: ReusableUnit) -> bool:
    return unit.status == "active" and unit.reuse_license


def view(db: Session, unit: ReusableUnit, detail: bool = False) -> dict:
    out = {
        "id": unit.id, "cluster_id": unit.cluster_id, "kind": unit.kind, "kind_label": KIND_LABEL[unit.kind],
        "title": unit.title, "version": unit.version, "status": unit.status,
        "applicability": unit.applicability, "validation": unit.validation,
        "sample_count": len(unit.sample_ids or []), "scope": unit.scope,
        "reuse_license": unit.reuse_license, "train_license": unit.train_license,
        "created_at": iso(unit.created_at),
    }
    if detail:
        out["content"] = unit.content
        out["manifest"] = unit.manifest
        out["est_cost_cents"] = unit.est_cost_cents
        out["contributors"] = contributors(db, unit)
    return out


def record_use(db: Session, unit: ReusableUnit, scenario: str, caller_id: int,
               task_id: int | None, summary: str = "", output: dict | None = None,
               draft: bool = False, cost_cents: int = 0, duration_ms: int = 0) -> UnitInvocation:
    """KB-083 每次使用留痕；KB-085 记下这一次的受益贡献者。"""
    inv = UnitInvocation(
        unit_id=unit.id, version=unit.version, scenario=scenario, caller_id=caller_id,
        task_id=task_id, input_summary=summary[:300], output=output or {}, draft=draft,
        cost_cents=cost_cents, duration_ms=duration_ms,
        beneficiaries=[c["user_id"] for c in contributors(db, unit)],
    )
    db.add(inv)
    db.flush()
    return inv


def best_procedure(db: Session, category: str, city: str, budget_cents: int) -> ReusableUnit | None:
    """AI-DEC-012 分解的模板来源：适用的、可复用的、已验证的优先。"""
    rows = [u for u in db.query(ReusableUnit).filter(ReusableUnit.kind == "procedure",
                                                     ReusableUnit.status == "active").all()
            if usable(u) and applies_to(u, category, city, budget_cents)]
    rank = {"validated": 0, "unvalidated": 1}
    rows.sort(key=lambda u: (rank.get((u.validation or {}).get("status"), 2), -u.id))
    return rows[0] if rows else None


# ------------------------------------------------------------------ 结果回流（KB-084）
def _refresh_validation(unit: ReusableUnit) -> None:
    v = dict(unit.validation or {})
    uses = v.get("uses", 0)
    bad = v.get("reworked", 0) + v.get("failed", 0)
    if uses >= settings.KB_UNIT_REVIEW_MIN_USES and bad * 2 >= uses:
        v["status"] = "needs_review"
        unit.status = "needs_review"
    elif uses >= settings.KB_UNIT_REVIEW_MIN_USES and bad * 5 < uses and v.get("status") != "needs_review":
        v["status"] = "validated"
    unit.validation = v


def settle(db: Session, task_id: int, outcome: str) -> int:
    """一单有了结果：把这一单用过的单元的调用结果记上，并更新单元的验证状态。"""
    n = 0
    for inv in db.query(UnitInvocation).filter(UnitInvocation.task_id == task_id,
                                               UnitInvocation.outcome == "pending").all():
        inv.outcome = outcome
        unit = db.get(ReusableUnit, inv.unit_id)
        if unit is not None:
            v = dict(unit.validation or {})
            v["uses"] = v.get("uses", 0) + 1
            v[outcome] = v.get(outcome, 0) + 1
            unit.validation = v
            _refresh_validation(unit)
        n += 1
    return n


def _on_task_completed(db: Session, payload: dict) -> None:
    from app.modules.task.models import Task

    task = db.get(Task, payload["task_id"])
    if task is None:
        return
    # 被驳回过（返工）才完成的，记 reworked：用了这个单元，事情没一次做对。
    # 用分解流程拆出来的项目，返工发生在子任务上——任一子任务被驳回过也算
    reworked = (task.reject_count or 0) > 0 or db.query(Task.id).filter(
        Task.parent_id == task.id, Task.reject_count > 0).first() is not None
    settle(db, task.id, "reworked" if reworked else "closed")


def _on_task_cancelled(db: Session, payload: dict) -> None:
    settle(db, payload["task_id"], "failed")


def register_event_handlers() -> None:
    from app.core.events import subscribe

    subscribe("task.completed", _on_task_completed, retry=True)
    subscribe("task.cancelled", _on_task_cancelled, retry=True)


# ------------------------------------------------------------------ 撤回（KB-089）
def on_reuse_revoked(db: Session, user_id: int) -> list[str]:
    """撤回经验复用：样本退出子类统计、以它们为来源的单元转待复核、草稿标出来源已撤回。"""
    from app.modules.task.models import Task

    from . import clusters

    task_ids = [t.id for t in db.query(Task.id).filter(
        (Task.creator_id == user_id) | (Task.executor_id == user_id))]
    cards = db.query(KnowledgeCard).filter(KnowledgeCard.source_task_id.in_(task_ids or [-1])).all()
    card_ids = {c.id for c in cards}
    touched = {c.cluster_id for c in cards if c.cluster_id}
    for c in cards:
        if c.cluster_state in ("assigned", "pending", "held", "undecided"):
            c.cluster_state, c.cluster_id = "retracted", None
            c.cluster_hint = {"reason": "贡献者撤回了经验复用授权"}
    db.flush()
    for cid in touched:
        cl = db.get(KnowledgeCluster, cid)
        if cl is not None:
            clusters.recompute(db, cl)
    units_hit = []
    for u in db.query(ReusableUnit).all():
        if card_ids & set(u.sample_ids or []):
            u.sample_ids = [s for s in u.sample_ids if s not in card_ids]
            v = dict(u.validation or {})
            v["status"] = "needs_review"
            u.validation, u.status = v, "needs_review"
            units_hit.append(u.id)
    flagged = 0
    if units_hit:
        flagged = (db.query(UnitInvocation).filter(UnitInvocation.unit_id.in_(units_hit))
                   .update({"source_revoked": True}, synchronize_session=False))
    db.flush()
    out = [f"samples_retracted:{len(card_ids)}"]
    if touched:
        out.append(f"clusters_recomputed:{len(touched)}")
    if units_hit:
        out.append(f"units_to_review:{len(units_hit)}")
    if flagged:
        out.append(f"drafts_flagged:{flagged}")
    return out


# ------------------------------------------------------------------ AGT-084 经验工具的统一关口（131 号 spec）
class ToolBlocked(Exception):
    """带着要返回给人的那个 409：人点按钮时原样抛出，编排代调用时只取文字写进时间线。"""

    def __init__(self, http):
        super().__init__(http.detail["message"])
        self.http, self.code, self.message = http, http.detail["code"], http.detail["message"]


def tool_gate(unit: ReusableUnit, task) -> None:
    """人点按钮（KB-088）和编排代调用（AGT-084）走同一道关口：可用、非退化态、成本不超单次上限、适用于这一单。"""
    tool_ready(unit)
    tool_applies(unit, task)


def tool_ready(unit: ReusableUnit) -> None:
    from . import clusters

    if not usable(unit):
        raise ToolBlocked(conflict("这个经验工具在复核中或已停用，暂不可用", "tool_unavailable"))
    _, semantic = clusters._provider_state()
    if not semantic:
        raise ToolBlocked(conflict("当前经验检索不是语义模型，可执行的经验工具暂停使用", "tool_degraded"))
    if unit.est_cost_cents > settings.KB_TOOL_MAX_COST_CENTS:
        raise ToolBlocked(conflict("这次调用的预估成本超过上限，没有执行；请改为人工处理", "tool_over_budget"))


def tool_applies(unit: ReusableUnit, task) -> None:
    if not applies_to(unit, task.category, task.city or "", task.budget_cents):
        raise ToolBlocked(conflict("这个经验工具不适用于这一单（类目、城市或预算不在它的适用范围内）", "tool_not_applicable"))


def month_start_utc(now):
    """北京时间本月 1 号 0 点对应的 UTC。"""
    from datetime import timedelta

    local = now + timedelta(hours=8)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)


def assistant_costs(db: Session, user_id: int, now=None) -> dict:
    """REL-110 本月助手花了多少（北京时间自然月）：agent 代调用的经验工具 + 例行任务的模型调用。"""
    from datetime import timedelta

    from sqlalchemy import func

    from app.modules.workbench.models import WbRoutineRun

    now = now or utcnow()
    since = month_start_utc(now)
    tools_cents, calls = db.query(func.coalesce(func.sum(UnitInvocation.cost_cents), 0), func.count(UnitInvocation.id))\
        .filter(UnitInvocation.caller_id == user_id, UnitInvocation.agent != "", UnitInvocation.created_at >= since).one()
    routines_cents = db.query(func.coalesce(func.sum(WbRoutineRun.cost_cents), 0))\
        .filter(WbRoutineRun.owner_id == user_id, WbRoutineRun.started_at >= since).scalar() or 0
    cap = settings.AGENT_MONTHLY_COST_CAP_CENTS
    total = int(tools_cents) + int(routines_cents)
    return {"month": (now + timedelta(hours=8)).strftime("%Y-%m"),
            "agent_tools_cents": int(tools_cents), "routines_cents": int(routines_cents), "total_cents": total,
            "cap_cents": cap, "remaining_cents": max(cap - total, 0), "agent_calls": int(calls)}
