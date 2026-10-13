"""场景包引擎（123 号 spec）：启用 / 停用 / 升级、助手专家问答、效果指标、场景雷达、种子导入。"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.modules.account.models import utcnow

from . import schema
from .models import PackEnrollment, PackEvent, ScenarioPack

SEEDS = Path(__file__).resolve().parent / "seeds"
K_ANON = 3              # 雷达里任何来自用户行为的信号，至少要 3 个不同的人：一个人的行为永远不单独出现
RADAR_DAYS = 30
STUCK_DAYS = 3
MIN_ASKS = 5            # 指标少于这么多次不下结论


# ------------------------------------------------------------------ 读取
def latest_published(db: Session, key: str) -> ScenarioPack | None:
    return (db.query(ScenarioPack).filter(ScenarioPack.key == key, ScenarioPack.status == "published")
            .order_by(ScenarioPack.version.desc()).first())


def definition(pack: ScenarioPack) -> schema.PackDef:
    return schema.PackDef.model_validate(pack.definition)


def enrollment(db: Session, user_id: int, key: str) -> PackEnrollment | None:
    return db.query(PackEnrollment).filter(PackEnrollment.user_id == user_id, PackEnrollment.pack_key == key).first()


def event(db: Session, pack: ScenarioPack, user_id: int, kind: str) -> None:
    db.add(PackEvent(pack_key=pack.key, pack_id=pack.id, user_id=user_id, kind=kind))


# ------------------------------------------------------------------ 启用（PACK-104）
class InstallLimit(Exception):
    pass


def install(db: Session, user_id: int, pack: ScenarioPack, with_routines: bool = True,
            installed: dict | None = None) -> dict:
    """把包里的方法、知识、例行任务**复制**到用户自己的知识库与工作台。

    复制之后就是用户自己的东西：可以改、可以删；包升级时只补新增的资产（按资产 key），
    **从不覆盖**用户改过的副本。上限沿用知识库与工作台自己的上限。
    """
    from app.modules.notebook import service as nsvc
    from app.modules.notebook.models import NbMethod, NbNote
    from app.modules.workbench import service as wsvc
    from app.modules.workbench.models import WbRoutine

    d = definition(pack)
    have = {g: dict((installed or {}).get(g, {})) for g in ("methods", "notes", "routines")}
    new_methods = [m for m in d.methods if m.key not in have["methods"]]
    new_notes = [k for k in d.knowledge if k.key not in have["notes"]]
    new_routines = [r for r in d.routines if r.key not in have["routines"]] if with_routines else []

    def count(model, owner_col):
        return db.query(func.count(model.id)).filter(owner_col == user_id).scalar() or 0

    if (count(NbMethod, NbMethod.owner_id) + len(new_methods) > nsvc.LIMITS["methods"]
            or count(NbNote, NbNote.owner_id) + len(new_notes) > nsvc.LIMITS["notes"]
            or count(WbRoutine, WbRoutine.owner_id) + len(new_routines) > wsvc.LIMITS["routines"]):
        raise InstallLimit()
    now = utcnow()
    tag = d.title[:20]
    for m in new_methods:
        row = NbMethod(owner_id=user_id, name=m.name, description=(m.description or f"来自场景包「{d.title}」")[:500],
                       steps=[s.model_dump() for s in m.steps], source_note_ids=[], created_at=now, updated_at=now)
        db.add(row)
        db.flush()
        have["methods"][m.key] = row.id
    for k in new_notes:
        meta = f"\n\n出处：{k.source}" + (f"\n有效期至：{k.valid_until.isoformat()}（以官方最新为准）" if k.valid_until else "")
        row = NbNote(owner_id=user_id, kind="note", title=k.title, body=(k.body + meta)[:20000], url="",
                     status="filed", tags=list(dict.fromkeys([tag, *k.tags]))[:10], created_at=now, updated_at=now)
        db.add(row)
        db.flush()
        have["notes"][k.key] = row.id
    for r in new_routines:
        row = WbRoutine(owner_id=user_id, name=r.name[:60], kind=r.kind, freq=r.freq, time_of_day=r.time_of_day,
                        weekday=r.weekday, monthday=r.monthday, note=r.note, enabled=True, created_at=now)
        row.next_run_at = wsvc.next_run(row, now)
        db.add(row)
        db.flush()
        have["routines"][r.key] = row.id
    return have


def uninstall(db: Session, user_id: int, installed: dict, remove_copies: bool) -> dict:
    """停用：例行任务一律关掉（停用了还推通知是骚扰）；`remove_copies` 时删掉**没改过**的副本，改过的留着。"""
    from app.modules.notebook.models import NbMethod, NbNote
    from app.modules.workbench.models import WbRoutine, WbRoutineRun

    kept = removed = 0
    rids = list((installed.get("routines") or {}).values())
    for r in db.query(WbRoutine).filter(WbRoutine.id.in_(rids or [-1]), WbRoutine.owner_id == user_id):
        if remove_copies:
            db.query(WbRoutineRun).filter(WbRoutineRun.routine_id == r.id).delete(synchronize_session=False)
            db.delete(r)
            removed += 1
        else:
            r.enabled, r.next_run_at = False, None
            db.add(r)
    if remove_copies:
        mids = list((installed.get("methods") or {}).values())
        for m in db.query(NbMethod).filter(NbMethod.id.in_(mids or [-1]), NbMethod.owner_id == user_id):
            if m.uses == 0 and m.updated_at == m.created_at:
                db.delete(m)
                removed += 1
            else:
                kept += 1
        nids = list((installed.get("notes") or {}).values())
        for n in db.query(NbNote).filter(NbNote.id.in_(nids or [-1]), NbNote.owner_id == user_id):
            if n.revision == 0:
                db.delete(n)
                removed += 1
            else:
                kept += 1
    return {"removed": removed, "kept_modified": kept}


# ------------------------------------------------------------------ 助手专家（PACK-105）
def _knowledge_hits(d: schema.PackDef, keys: list[str], q: str) -> list[tuple[schema.KnowledgeDef, int]]:
    from app.modules.notebook.service import MIN_RELATED, score, terms

    ts = terms(q)
    pool = [k for k in d.knowledge if not keys or k.key in keys]
    scored = []
    for k in pool:
        s = score(SimpleNamespace(title=k.title, body=k.body, tags=k.tags, url=""), ts)
        if s >= MIN_RELATED:
            scored.append((k, s))
    scored.sort(key=lambda x: -x[1])
    return scored[:3]


def ask(db: Session, user_id: int, pack: ScenarioPack, akey: str, q: str) -> dict | None:
    """摘录式回答：只用助手白名单里的工具，每一句都标出处；碰到人工关口的事明说「须你本人确认」。"""
    from app.modules.legal.router import HIGH_RISK_KEYWORDS, LEGAL_FAQS
    from app.modules.notebook import service as nsvc

    d = definition(pack)
    a = next((x for x in d.assistants if x.key == akey), None)
    if a is None:
        return None
    gates = [schema.GATES[g] for g in a.human_gates if g in schema.GATES]
    base = {"assistant": a.name, "gates": gates,
            "gate_notice": "这些事助手只给草稿，必须你本人确认后再做：" + "；".join(gates)}
    if any(kw in q for kw in HIGH_RISK_KEYWORDS):
        event(db, pack, user_id, "ask")
        return {**base, "refused": True, "answer": "这个问题涉及人身安全或刑事风险，请立即拨打 110 或联系专业机构。",
                "citations": [], "remedy": None}
    cites: list[dict] = []
    today = date.today()
    if "pack.knowledge" in a.tools:
        ts = nsvc.terms(q)
        for k, _ in _knowledge_hits(d, a.knowledge, q):
            expired = bool(k.valid_until and k.valid_until < today)
            cites.append({"kind": "pack", "title": k.title, "snippet": nsvc.snippet(k.body, ts),
                          "source": k.source, "valid_until": k.valid_until.isoformat() if k.valid_until else None,
                          "expired": expired, "note_id": None})
    if "notebook.search" in a.tools:
        for r in nsvc.related(db, user_id, q, k=2):
            cites.append({"kind": "note", "title": r["title"], "snippet": r["snippet"], "source": "我的知识库",
                          "valid_until": None, "expired": False, "note_id": r["note_id"]})
    if "legal.faq" in a.tools:
        best, hits = None, 0
        for faq in LEGAL_FAQS:
            h = sum(1 for kw in faq["keywords"] if kw in q)
            if h > hits:
                best, hits = faq, h
        if best:
            cites.append({"kind": "legal", "title": best["keywords"][0], "snippet": best["answer"][:160],
                          "source": "平台法律常识（不构成法律意见）", "valid_until": None, "expired": False, "note_id": None})
    if not cites:
        event(db, pack, user_id, "unanswered")
        remedy = ({"action": "publish_task", "category": a.fallback_category,
                   "label": f"发布一单「{a.fallback_category}」，请专业的人来做"} if a.fallback_category else None)
        return {**base, "refused": False, "answer": "这个问题包里的资料和你的笔记都没有覆盖到。", "citations": [],
                "remedy": remedy}
    event(db, pack, user_id, "ask")
    for n, c in enumerate(cites, 1):
        c["n"] = n
    lines = [f"「{a.name}」从 {len(cites)} 处资料里找到："]
    for c in cites:
        tail = f"（出处：{c['source']}" + (f"；有效期至 {c['valid_until']}" if c["valid_until"] else "") + "）"
        lines.append(f"[{c['n']}] {c['title']}：{c['snippet']}{tail}" + ("【已过有效期，以官方最新为准】" if c["expired"] else ""))
    return {**base, "refused": False, "answer": "\n".join(lines), "citations": cites, "remedy": None}


# ------------------------------------------------------------------ 指标（PACK-106）
def metrics(db: Session, keys: list[str]) -> dict[str, dict]:
    since = utcnow() - timedelta(days=RADAR_DAYS)
    out = {k: {"active": 0, "enabled_total": 0, "asks_30d": 0, "unanswered_30d": 0, "helpful_30d": 0,
               "unhelpful_30d": 0} for k in keys}
    if not keys:
        return out
    for key, status, n in (db.query(PackEnrollment.pack_key, PackEnrollment.status, func.count(PackEnrollment.id))
                           .filter(PackEnrollment.pack_key.in_(keys))
                           .group_by(PackEnrollment.pack_key, PackEnrollment.status)):
        out[key]["enabled_total"] += n
        if status == "active":
            out[key]["active"] = n
    names = {"ask": "asks_30d", "unanswered": "unanswered_30d", "helpful": "helpful_30d", "unhelpful": "unhelpful_30d"}
    for key, kind, n in (db.query(PackEvent.pack_key, PackEvent.kind, func.count(PackEvent.id))
                         .filter(PackEvent.pack_key.in_(keys), PackEvent.created_at >= since)
                         .group_by(PackEvent.pack_key, PackEvent.kind)):
        if kind in names:
            out[key][names[kind]] = n
    for m in out.values():
        total = m["asks_30d"] + m["unanswered_30d"]
        m["unanswered_rate"] = round(m["unanswered_30d"] / total, 2) if total else None
        fb = m["helpful_30d"] + m["unhelpful_30d"]
        m["helpful_rate"] = round(m["helpful_30d"] / fb, 2) if fb else None
    return out


# ------------------------------------------------------------------ 场景雷达（PACK-107）
def _level(n: int, steps=(3, 5, 10, 20)) -> int:
    return 1 + sum(1 for s in steps if n >= s)


def radar(db: Session) -> list[dict]:
    """从**聚合**信号里找没被满足的需求。不读任何人的私人数据（个人笔记、私聊、提问原文一概不碰）。

    1. 搜了没有供给：至少 3 个不同的人近 30 天搜过、而公开招募中的任务里一条都匹配不上的词；
    2. 有需求没人接：同一类目近 60 天有 ≥3 单招募超过 3 天还没人报名；
    3. 已上线的包没接住：答不上的比例 ≥30%、或觉得没用的比例 ≥50%（样本 ≥5）、或知识过了有效期。
    """
    from app.modules.analytics.models import SearchQuery
    from app.modules.task.models import Application, Task

    now = utcnow()
    out: list[dict] = []
    users = func.count(distinct(SearchQuery.user_id))
    rows = (db.query(SearchQuery.term, users).filter(SearchQuery.user_id.isnot(None),
                                                     SearchQuery.created_at >= now - timedelta(days=RADAR_DAYS))
            .group_by(SearchQuery.term).having(users >= K_ANON).order_by(users.desc()).limit(50).all())
    for term, n in rows:
        supply = (db.query(Task.id).filter(Task.status == "published", Task.visibility == "public",
                                           Task.title.contains(term, autoescape=True)
                                           | Task.description.contains(term, autoescape=True)).first())
        if supply is None:
            out.append({"source": "search_gap", "key": term, "title": f"有人在找「{term}」，平台上没有",
                        "evidence": f"近 {RADAR_DAYS} 天 {n} 个不同的人搜过，招募中的任务一条都没匹配上",
                        "people": n, "suggested": {"coverage": _level(n), "frequency": _level(n)}})
    stuck = (db.query(Task.category, func.count(Task.id))
             .outerjoin(Application, Application.task_id == Task.id)
             .filter(Task.status == "published", Task.created_at < now - timedelta(days=STUCK_DAYS),
                     Task.created_at >= now - timedelta(days=60), Application.id.is_(None))
             .group_by(Task.category).having(func.count(distinct(Task.creator_id)) >= K_ANON).all())
    for category, n in stuck:
        out.append({"source": "stuck_demand", "key": category, "title": f"「{category}」有需求没人接",
                    "evidence": f"{n} 单招募超过 {STUCK_DAYS} 天还没人报名（来自至少 {K_ANON} 个发布方）",
                    "people": n, "suggested": {"coverage": _level(n), "frequency": _level(n)}})
    live = db.query(ScenarioPack).filter(ScenarioPack.status == "published").all()
    m = metrics(db, [p.key for p in live])
    today = date.today()
    for p in live:
        x = m.get(p.key, {})
        reasons = []
        total = x.get("asks_30d", 0) + x.get("unanswered_30d", 0)
        if total >= MIN_ASKS and (x.get("unanswered_rate") or 0) >= 0.3:
            reasons.append(f"答不上 {round(x['unanswered_rate'] * 100)}%（{total} 次提问）")
        fb = x.get("helpful_30d", 0) + x.get("unhelpful_30d", 0)
        if fb >= MIN_ASKS and (x.get("helpful_rate") or 0) < 0.5:
            reasons.append(f"觉得有用的只有 {round((x['helpful_rate'] or 0) * 100)}%（{fb} 次反馈）")
        expired = [k.title for k in definition(p).knowledge if k.valid_until and k.valid_until < today]
        if expired:
            reasons.append(f"{len(expired)} 条知识已过有效期：{'、'.join(expired[:3])}")
        if reasons:
            out.append({"source": "pack_gap", "key": p.key, "title": f"场景包「{p.title}」要复核",
                        "evidence": "；".join(reasons), "people": x.get("active", 0), "suggested": {}})
    return out


# ------------------------------------------------------------------ 种子（PACK-108）
def seed_files() -> list[Path]:
    return sorted(SEEDS.glob("*.json"))


def load_seed(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
