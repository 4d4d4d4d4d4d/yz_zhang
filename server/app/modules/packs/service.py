"""场景包引擎（123 号 spec）：启用 / 停用 / 升级、助手专家问答、效果指标、场景雷达、种子导入。"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.core.timefmt import day

from app.modules.account.models import utcnow

from . import schema
from .models import PackEnrollment, PackEvent, ScenarioPack

SEEDS = Path(__file__).resolve().parent / "seeds"
K_ANON = 3              # 雷达里任何来自用户行为的信号，至少要 3 个不同的人：一个人的行为永远不单独出现
RADAR_DAYS = 30
STUCK_DAYS = 3
MIN_ASKS = 5            # 指标少于这么多次不下结论
# SCN-161（289 号 spec）知识到期前这么多天就进雷达，让运营赶在过期前对照最新通报或法规更新
EXPIRING_DAYS = 30


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


# ------------------------------------------------------------------ 角色契约（REL-107，130 号 spec）
# 「让助手去做」的说法：帮我 / 替我 / 代我 / 直接 / 你来 / 你去。「帮我看看、帮我算算、帮我解释」是问，不是让它去做
_DELEGATE = re.compile(r"(?:帮我|帮忙|替我|代我|给我)(?!看|查|算|想|解释|理解|分析|整理|列|写|讲|说|总结|估)|直接|你来|你去|你替")
_STRONG_VERBS = set("签付缴转")
_CORE_STRIP = re.compile(r"^(?:替你|帮你|代你|动用你的|把你的)")


def _actions(phrase: str) -> list[str]:
    """「替你付款、收款或确认验收」→ ["付款", "收款", "确认验收"]。只看「替你 / 动用你的 / 把你的」开头的动作类禁区。"""
    if not _CORE_STRIP.match(phrase):
        return []
    core = _CORE_STRIP.sub("", phrase)
    return [x for x in re.split(r"[、，,或和及与/]", core) if len(x) >= 2]


def _hits(action: str, q: str) -> bool:
    """动作的关键两字（动词或宾语）在问题里出现。「申报或缴税」→ 申报 / 缴税；「开具发票」→ 开具 / 发票。"""
    grams = {action[i:i + 2] for i in range(len(action) - 1)} - {"你的"}
    if action[0] in _STRONG_VERBS:      # 「签署合同」也要认出「帮我签了」
        grams.add(action[0])
    return any(g in q for g in grams)


def contract_violation(a, q: str) -> str:
    """问题是在让助手去做它角色契约里禁止的事：返回那条禁区（空串 = 没有）。"""
    if not _DELEGATE.search(q):
        return ""
    for phrase in a.forbidden:
        if any(_hits(act, q) for act in _actions(phrase)):
            return phrase
    return ""


def contract(a) -> dict:
    """REL-107 给人看的角色契约：它是谁、要什么、给什么、不做什么、用哪些工具、哪些事必须你本人确认。"""
    return {"key": a.key, "name": a.name, "persona": a.persona, "inputs": list(a.inputs), "outputs": list(a.outputs),
            "forbidden": list(a.forbidden),
            "tools": [{"key": t, "name": schema.TOOLS.get(t, t)} for t in a.tools],
            "human_gates": [{"key": g, "name": schema.GATES.get(g, g)} for g in a.human_gates],
            "fallback_category": a.fallback_category}


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
        meta = f"\n\n出处：{k.source}" + (f"\n有效期至：{day(k.valid_until)}（以官方最新为准）" if k.valid_until else "")
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
# SCN-105 标签整词出现在问题里就算强命中（138 号 spec）：标签是运营挑出来的关键词，
# 「雇人还是发临时单」切成二字片覆盖不到一半，但「雇人」「临时单」两个标签整词都在
TAG_IN_QUESTION = 6


def tag_bonus(tags: list[str], q: str) -> int:
    low = q.lower()
    return sum(TAG_IN_QUESTION for t in dict.fromkeys(tags) if len(t) >= 2 and t.lower() in low)


def _knowledge_hits(d: schema.PackDef, keys: list[str], q: str,
                    db: Session | None = None) -> list[tuple[schema.KnowledgeDef, int]]:
    from app.modules.notebook.service import MIN_RELATED, score, terms
    from app.modules.skills.service import expand_query

    # SCN-105 与个人知识库一样，问题里的技能概念展开成「规范名 + 别名」再检索（135 号的概念表）
    ts = terms(expand_query(q, db))
    pool = [k for k in d.knowledge if not keys or k.key in keys]
    scored = []
    for k in pool:
        s = score(SimpleNamespace(title=k.title, body=k.body, tags=k.tags, url=""), ts) + tag_bonus(k.tags, q)
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
    banned = contract_violation(a, q)
    if banned:
        # REL-107 角色契约在运行时生效：让它去做禁区里的事，直接说不做、为什么、该怎么办
        event(db, pack, user_id, "refused")
        return {**base, "refused": True,
                "answer": f"这件事不在「{a.name}」的角色契约里：它不会{banned.removeprefix('替你')}。"
                          f"它能做的是给你草稿、清单和出处；{base['gate_notice']}",
                "citations": [], "remedy": None}
    cites: list[dict] = []
    today = date.today()
    if "pack.knowledge" in a.tools:
        ts = nsvc.terms(q)
        for k, _ in _knowledge_hits(d, a.knowledge, q, db):
            expired = bool(k.valid_until and k.valid_until < today)
            cites.append({"kind": "pack", "title": k.title, "snippet": nsvc.snippet(k.body, ts),
                          "source": k.source, "valid_until": day(k.valid_until) if k.valid_until else None,
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
    cites += _tool_citations(db, user_id, a.tools, q)
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


_ASK_CALENDAR = re.compile(r"申报|报税|截止|什么时候|几号|日历|年报|汇算")
_ASK_BOOKS = re.compile(r"收入|账|免税|销售额|赚了|利润|多少钱")
_ASK_CONTRACT = re.compile(r"合同|条款|协议")
_ASK_NEARBY = re.compile(r"附近|有什么单|接单|有活|顺路")
_ASK_QUOTE = re.compile(r"报价|多少钱|价格|报多少|行情")
_ASK_BRIEF = re.compile(r"需求|甲方|客户|brief|要求|帮我看看|缺什么", re.I)
_ASK_SCRIPT = re.compile(r"话术|文案|台词|口播|能不能说|这样说|帮我看看|帮我查")


def _experience_citations(db: Session, q: str, k: int = 2) -> list[dict]:
    """AGT-084 助手只读检索平台经验单元（131 号 spec）：只引用、不执行；只用可复用、在用的单元，写明版本与验证状态。"""
    from app.modules.knowledge import units
    from app.modules.knowledge.models import ReusableUnit
    from app.modules.notebook.service import MIN_RELATED, score, snippet, terms

    ts = terms(q)
    if not ts:
        return []
    scored = []
    for u in db.query(ReusableUnit).filter(ReusableUnit.status == "active").order_by(ReusableUnit.id.desc()).limit(500):
        if not units.usable(u):
            continue
        content = u.content or {}
        body = " ".join(str(x) for x in [content.get("summary", ""), *(content.get("steps") or []), *(content.get("checklist") or [])])
        s = score(SimpleNamespace(title=u.title, body=body, tags=[], url=""), ts)
        if s >= MIN_RELATED:
            scored.append((s, u, body))
    scored.sort(key=lambda x: -x[0])
    status = {"validated": "已验证", "unvalidated": "未验证"}
    return [{"kind": "experience", "title": u.title, "snippet": snippet(body or u.title, ts),
             "source": f"平台经验（第 {u.version} 版，{status.get((u.validation or {}).get('status'), '未验证')}）",
             "valid_until": None, "expired": False, "note_id": None} for _, u, body in scored[:k]]


CALENDAR_DAYS = 120


def _tool_citations(db: Session, user_id: int, tools: list[str], q: str) -> list[dict]:
    """白名单里的一人公司工具：问到相关的事，就用本人的数据算一遍，作为一条「按你的数据推算」的出处。"""
    from app.modules.opc import service as osvc
    from app.modules.opc.models import OpcProfile
    from app.modules.workbench.service import local

    out: list[dict] = []
    if "experience.search" in tools:
        out += _experience_citations(db, q)
    today = local(utcnow()).date()
    profile = db.get(OpcProfile, user_id)
    if "opc.calendar" in tools and _ASK_CALENDAR.search(q):
        # 按季申报的两个节点最多隔 92 天、再加周末顺延：只看 90 天会在季度申报期刚过的那几天什么都看不到
        # （10-16 起下一个是 1-15，差一天落在窗外）。用日历本身的默认 120 天，保证至少看得到下一次
        items = osvc.deadlines(profile or OpcProfile(user_id=user_id, entity="individual", vat="none",
                                                     vat_period="quarter"), today, CALENDAR_DAYS)[:4]
        if items:
            out.append({"kind": "tool", "title": f"你的申报日历（接下来 {CALENDAR_DAYS} 天）",
                        "snippet": "；".join(f"{i['date']} {i['title']}" for i in items),
                        "source": "按你在「一人公司」里填的主体与纳税人类型推算" + ("" if profile else "（还没填，按个人推算）"),
                        "valid_until": None, "expired": False, "note_id": None})
    if "opc.books" in tools and _ASK_BOOKS.search(q):
        s = osvc.summary(db, user_id, osvc.current_quarter(today), profile, today)
        out.append({"kind": "tool", "title": f"你的记账底稿（{s['period']}）",
                    "snippet": f"收入 ¥{s['income_cents'] / 100:.2f}，支出 ¥{s['expense_cents'] / 100:.2f}。" + (s["notes"][0] if s["notes"] else ""),
                    "source": "按你的记账底稿汇总（不是申报表）", "valid_until": None, "expired": False, "note_id": None})
    if "opc.contract_review" in tools and len(q) >= 20 and _ASK_CONTRACT.search(q):
        r = osvc.review_contract(q)
        top = [f for f in r["findings"] if f["level"] == "high"][:3] or r["findings"][:3]
        if top:
            out.append({"kind": "tool", "title": "合同体检（按条款清单）",
                        "snippet": "；".join(f"{f['clause']}：{f['finding']}" for f in top),
                        "source": "条款清单与风险句式（不构成法律意见）", "valid_until": None, "expired": False, "note_id": None})
    if "gig.nearby" in tools and _ASK_NEARBY.search(q):
        from app.modules.gig import service as gsvc

        a = gsvc.active(db, user_id)
        if a is None:
            out.append({"kind": "tool", "title": "附近的单", "snippet": "你还没打开「现在有空」：打开后我才知道你在哪、能接多远的单",
                        "source": "接单助手（需要你的位置）", "valid_until": None, "expired": False, "note_id": None})
        else:
            items = gsvc.nearby(db, user_id, a.lat, a.lng, a.radius_km, a.categories, limit=3)
            out.append({"kind": "tool", "title": f"你附近 {a.radius_km} 公里内的单",
                        "snippet": "；".join(f"{i['title']}（{i['category']}，约 {i['distance_m'] / 1000:.1f} 公里，到手约 ¥{i['net_cents'] / 100:.0f}）"
                                            for i in items) or "现在附近没有招募中的单",
                        "source": "按你「现在有空」的位置（直线距离）", "valid_until": None, "expired": False, "note_id": None})
    if "gig.quote" in tools and _ASK_QUOTE.search(q):
        from app.modules.gig import service as gsvc
        from app.modules.task.models import Category

        names = [n for (n,) in db.query(Category.name).filter(Category.active.is_(True))]
        cat = next((n for n in sorted(names, key=len, reverse=True) if n in q), None)
        if cat:
            r = gsvc.quote(db, cat, None, None)
            out.append({"kind": "tool", "title": f"「{cat}」报价参考", "snippet": "；".join(r["basis"]),
                        "source": "平台近 180 天成交数据（不是承诺价）", "valid_until": None, "expired": False, "note_id": None})
    if "creator.brief" in tools and len(q) >= 20 and _ASK_BRIEF.search(q):
        from app.modules.packs.creator import brief_check

        r = brief_check(q)
        out.append({"kind": "tool", "title": f"需求单体检（写到 {len(r['present'])}/{len(r['present']) + len(r['missing'])} 项）",
                    "snippet": ("没写：" + "、".join(r["missing"]) + "。先问甲方：" + "".join(r["questions"][:3]))
                    if r["missing"] else "九项都写到了：可以按这份需求报价、写进验收标准",
                    "source": "需求单九项清单（只看你贴的这段文字）", "valid_until": None, "expired": False, "note_id": None})
    if "live.script_check" in tools and len(q) >= 15 and _ASK_SCRIPT.search(q):
        from app.modules.packs.live import script_check

        hits = script_check(q)["hits"]
        out.append({"kind": "tool", "title": f"话术自查（标出 {len(hits)} 处）",
                    "snippet": "；".join(f"「{h['word']}」：{h['kind']}，{h['why']}（{h['source']}）" for h in hits[:5])
                    if hits else "没发现词表里的词；词表只是常见的那几类，具体算不算违规以市场监管部门认定为准",
                    "source": "话术自查词表（只看你贴的这段文字，不断定违规）", "valid_until": None, "expired": False, "note_id": None})
    return out


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
    3. 已上线的包没接住：答不上的比例 ≥30%、或觉得没用的比例 ≥50%（样本 ≥5）、或知识过了有效期；
    4. 法律问答答不上的问题按粗主题（153 号 spec，原文不落库）；
    5. 客服没接住的工单（超时或升级过）按标题归到粗主题（153 号 spec，只出主题与人数）。
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
    out += _legal_gaps(db, now) + _support_gaps(db, now)
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
        soon = [k.title for k in expiring_knowledge(definition(p), today)]
        if soon:
            reasons.append(f"{len(soon)} 条知识 {EXPIRING_DAYS} 天内到期：{'、'.join(soon[:3])}（到期前对照最新通报或法规更新）")
        if reasons:
            out.append({"source": "pack_gap", "key": p.key, "title": f"场景包「{p.title}」要复核",
                        "evidence": "；".join(reasons), "people": x.get("active", 0), "suggested": {}})
    return out


def expiring_knowledge(d, today: date) -> list:
    """SCN-161 / SCN-163 今天到 30 天后（含）到期的知识；已过期的不算在这里。"""
    return [k for k in d.knowledge if k.valid_until and today <= k.valid_until <= today + timedelta(days=EXPIRING_DAYS)]


# SCN-163（292 号 spec）同一个包一周最多提醒一次
EXPIRY_REMIND_EVERY_DAYS = 7


def remind_expiring_knowledge(db: Session) -> dict:
    """SCN-163 已上线的包里有知识 30 天内到期：直接通知写这个包的运营（雷达要有人去看，这里推过去）。

    写包的人已不是管理员、被封或没有运营角色时，通知全部运营，免得提醒落空。
    """
    from app.core.admin_roles import has_role
    from app.modules.account.models import User, utcnow
    from app.modules.notification.service import notify

    now = utcnow()
    today = date.today()
    ops = None
    sent = 0
    for p in db.query(ScenarioPack).filter(ScenarioPack.status == "published").order_by(ScenarioPack.id):
        soon = expiring_knowledge(definition(p), today)
        if not soon:
            continue
        if p.expiry_reminded_at and p.expiry_reminded_at > now - timedelta(days=EXPIRY_REMIND_EVERY_DAYS):
            continue
        author = db.get(User, p.created_by)
        if author is not None and author.is_admin and not author.is_banned and has_role(author, "ops"):
            to = [author.id]
        else:
            if ops is None:
                ops = [u.id for u in db.query(User).filter(User.is_admin.is_(True), User.is_banned.is_(False))
                       .order_by(User.id) if has_role(u, "ops")]
            to = ops
        items = "；".join(f"「{k.title}」{day(k.valid_until)} 到期" for k in soon[:5])
        for uid in to:
            notify(db, uid, "system", f"场景包「{p.title}」有知识快到期了",
                   f"{len(soon)} 条知识 {EXPIRING_DAYS} 天内到期：{items}。请对照最新通报或法规更新后建新版本、"
                   "交另一位管理员审核上线；过期后助手回答会标「已过有效期」。")
        p.expiry_reminded_at = now
        db.add(p)
        sent += 1
    return {"reminded": sent}


def radar_knowledge_draft(signal: dict, taken: set) -> dict:
    """SCN-112 把一条雷达信号起草成知识条目：只有骨架与依据，答案和出处留给人写（「【待填写】」）。"""
    from .schema import PLACEHOLDER
    from .topics import LEGAL_TOPICS, SUPPORT_TOPICS

    src, key = signal["source"], signal["key"]
    words = {"legal_gap": LEGAL_TOPICS, "support_gap": SUPPORT_TOPICS}.get(src, {}).get(key, ())
    title = {"legal_gap": f"{key}：常见问题怎么答", "support_gap": f"{key}：客服常见问题",
             "search_gap": f"想找「{key}」时怎么办", "stuck_demand": f"「{key}」的需求怎么写才有人接"}.get(src, f"复核：{key}")
    n = 1
    while f"radar-{src.replace('_', '-')}-{n}" in taken:
        n += 1
    body = (f"{PLACEHOLDER}这里写给用户看的回答：先说结论，再说依据和步骤。\n\n"
            f"起草依据（场景雷达）：{signal['evidence']}\n"
            + (f"这类问题常出现的词：{'、'.join(words)}\n" if words else "")
            + "写的时候：碰钱、签署、申报的只给步骤，不替人做决定；拿不准的写明「建议找律师」或「转人工客服」。")
    return {"key": f"radar-{src.replace('_', '-')}-{n}", "title": title[:200], "body": body[:5000],
            "kind": "rule" if src == "legal_gap" else "howto",
            "source": f"{PLACEHOLDER}出处：法规名与条号、官网链接或平台规则", "tags": [key[:20], "雷达起草"]}


def _legal_gaps(db: Session, now) -> list[dict]:
    """SCN-108 法律问答答不上的问题，按粗主题聚合（原文从不落库，见 legal_ask）。"""
    from app.modules.analytics.models import AnalyticsEvent

    users = func.count(distinct(AnalyticsEvent.user_id))
    rows = (db.query(AnalyticsEvent.ref_type, users)
            .filter(AnalyticsEvent.name == "legal_unanswered", AnalyticsEvent.user_id.isnot(None),
                    AnalyticsEvent.created_at >= now - timedelta(days=RADAR_DAYS))
            .group_by(AnalyticsEvent.ref_type).having(users >= K_ANON).order_by(users.desc()).all())
    return [{"source": "legal_gap", "key": topic, "title": f"「{topic}」类法律问题常答不上",
             "evidence": f"近 {RADAR_DAYS} 天 {n} 个不同的人问到这类问题，平台法律知识库答不上（只记主题，不存原文）",
             "people": n, "suggested": {"coverage": _level(n), "frequency": _level(n)}} for topic, n in rows]


def _support_gaps(db: Session, now) -> list[dict]:
    """SCN-108 客服没接住的工单：近 30 天超时升级过、或至今未结且已超过 SLA 的，按标题归到粗主题聚合。
    标题只在这里归类，雷达上只出现主题与不同的人数。"""
    from app.core.config import settings
    from app.modules.support.models import Ticket

    from .topics import SUPPORT_TOPICS, topic_of

    overdue = now - timedelta(hours=settings.SUPPORT_SLA_HOURS)
    rows = (db.query(Ticket.user_id, Ticket.subject)
            .filter(Ticket.created_at >= now - timedelta(days=RADAR_DAYS),
                    (Ticket.escalation_level > 0) | ((Ticket.status == "open") & (Ticket.created_at < overdue)))
            .all())
    people: dict[str, set[int]] = {}
    for uid, subject in rows:
        people.setdefault(topic_of(subject or "", SUPPORT_TOPICS), set()).add(uid)
    out = []
    for topic, who in sorted(people.items(), key=lambda kv: -len(kv[1])):
        if len(who) < K_ANON:
            continue
        n = len(who)
        out.append({"source": "support_gap", "key": topic, "title": f"「{topic}」类工单客服没接住",
                    "evidence": f"近 {RADAR_DAYS} 天 {n} 个不同的人的这类工单超时或被升级（只按标题归类，不出原文）",
                    "people": n, "suggested": {"coverage": _level(n), "frequency": _level(n)}})
    return out


# ------------------------------------------------------------------ 种子（PACK-108）
def seed_files() -> list[Path]:
    return sorted(SEEDS.glob("*.json"))


def load_seed(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
