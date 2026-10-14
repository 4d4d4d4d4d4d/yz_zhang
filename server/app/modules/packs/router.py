"""PACK-100 场景包接口（123 号 spec）：用户浏览 / 启用 / 问助手专家 / 反馈；管理员定义 / 审核（四眼）/ 上线 / 下线 / 指标 / 雷达。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import bad_request, conflict, not_found
from app.core.timefmt import day, iso
from app.modules.account.models import User, utcnow

from . import schema
from . import service as svc
from .models import PackEnrollment, ScenarioPack

router = APIRouter(tags=["packs"])


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnableIn(_In):
    with_routines: bool = True


class DisableIn(_In):
    remove_copies: bool = False


class AskIn(_In):
    q: str = Field(min_length=1, max_length=300)


class FeedbackIn(_In):
    helpful: bool


class PackIn(_In):
    definition: dict


class RetireIn(_In):
    reason: str = Field(min_length=2, max_length=300)


# ------------------------------------------------------------------ 输出
def _assets(d: schema.PackDef) -> dict:
    return {
        "assistants": [{"key": a.key, "name": a.name, "persona": a.persona, "inputs": a.inputs, "outputs": a.outputs,
                        "forbidden": a.forbidden, "tools": a.tools,
                        "human_gates": [schema.GATES[g] for g in a.human_gates if g in schema.GATES]}
                       for a in d.assistants],
        "methods": [{"key": m.key, "name": m.name, "steps": len(m.steps)} for m in d.methods],
        "knowledge": [{"key": k.key, "title": k.title, "kind": k.kind, "source": k.source,
                       "valid_until": day(k.valid_until) if k.valid_until else None} for k in d.knowledge],
        "routines": [{"key": r.key, "name": r.name, "freq": r.freq, "time_of_day": r.time_of_day} for r in d.routines],
        # 发单模板只预填发布页（标题 / 类目 / 说明含验收标准），发不发由人决定（publish 关口）
        "task_templates": [{"key": t.key, "title": t.title, "category": t.category,
                            "description": t.description + ("\n\n验收标准：\n" + "\n".join(f"- {x}" for x in t.acceptance)
                                                            if t.acceptance else "")}
                           for t in d.task_templates],
    }


def _card(p: ScenarioPack, enr: PackEnrollment | None = None, active_users: int = 0) -> dict:
    d = svc.definition(p)
    mine = enr is not None and enr.status == "active"
    return {"key": p.key, "version": p.version, "title": p.title, "segment": p.segment, "summary": p.summary,
            "pains": d.pains, "enabled": mine, "enabled_version": enr.version if mine else None,
            "upgrade_available": bool(mine and enr.pack_id != p.id), "active_users": active_users,
            "assets": _assets(d), "published_at": iso(p.published_at)}


def _admin_row(p: ScenarioPack) -> dict:
    return {"id": p.id, "key": p.key, "version": p.version, "title": p.title, "segment": p.segment,
            "status": p.status, "score": p.score, "created_by": p.created_by, "reviewed_by": p.reviewed_by,
            "published_at": iso(p.published_at), "retired_reason": p.retired_reason,
            "updated_at": iso(p.updated_at), "definition": p.definition}


def _latest_or_404(db: Session, key: str) -> ScenarioPack:
    p = svc.latest_published(db, key)
    if p is None:
        raise not_found("场景包不存在或已下线")
    return p


# ------------------------------------------------------------------ 用户
@router.get("/packs")
def list_packs(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """已上线的场景包（每个 key 取最新版本）。附带我是否已启用、有没有新版本、多少人在用。"""
    rows = db.query(ScenarioPack).filter(ScenarioPack.status == "published").order_by(ScenarioPack.version.desc()).all()
    latest: dict[str, ScenarioPack] = {}
    for p in rows:
        latest.setdefault(p.key, p)
    enr = {e.pack_key: e for e in db.query(PackEnrollment).filter(PackEnrollment.user_id == user.id)}
    m = svc.metrics(db, list(latest))
    return [_card(p, enr.get(k), m[k]["active"]) for k, p in sorted(latest.items(), key=lambda x: -x[1].score)]


@router.get("/packs/{key}")
def get_pack(key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    p = _latest_or_404(db, key)
    return _card(p, svc.enrollment(db, user.id, key), svc.metrics(db, [key])[key]["active"])


@router.post("/packs/{key}/enable")
def enable(key: str, body: EnableIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db, scope="function")):
    """启用＝把包里的方法、知识、例行任务复制进我的知识库与工作台。已启用时再调＝升级（只补新增的资产）。"""
    p = _latest_or_404(db, key)
    enr = svc.enrollment(db, user.id, key)
    prev = (enr.installed if enr and enr.status == "active" else None) or None
    try:
        installed = svc.install(db, user.id, p, body.with_routines, prev)
    except svc.InstallLimit:
        raise conflict("知识库或工作台的数量已到上限，先整理一下再启用", "pack_install_limit") from None
    now = utcnow()
    if enr is None:
        enr = PackEnrollment(user_id=user.id, pack_key=key, pack_id=p.id, created_at=now)
    enr.pack_id, enr.version, enr.status, enr.installed, enr.updated_at = p.id, p.version, "active", installed, now
    db.add(enr)
    svc.event(db, p, user.id, "enable")
    db.flush()
    return {**_card(p, enr), "installed": {g: len(v) for g, v in installed.items()}}


@router.post("/packs/{key}/disable")
def disable(key: str, body: DisableIn, user: User = Depends(get_current_user),
            db: Session = Depends(get_db, scope="function")):
    enr = svc.enrollment(db, user.id, key)
    if enr is None or enr.status != "active":
        raise not_found("你没有启用这个场景包")
    out = svc.uninstall(db, user.id, enr.installed or {}, body.remove_copies)
    enr.status, enr.updated_at = "removed", utcnow()
    db.add(enr)
    pack = db.get(ScenarioPack, enr.pack_id)
    if pack is not None:
        svc.event(db, pack, user.id, "disable")
    db.flush()
    return {"disabled": True, **out}


@router.post("/packs/{key}/assistants/{akey}/ask")
def ask(key: str, akey: str, body: AskIn, user: User = Depends(get_current_user),
        db: Session = Depends(get_db, scope="function")):
    """问助手专家。没启用也能问（先试再用）；提问原文不落库，只记一次「问了 / 没答上」。"""
    p = _latest_or_404(db, key)
    out = svc.ask(db, user.id, p, akey, body.q)
    if out is None:
        raise not_found("这个场景包里没有这位助手")
    return out


@router.get("/packs/{key}/assistants/{akey}/contract")
def assistant_contract(key: str, akey: str, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db, scope="function")):
    """REL-107 这位助手的角色契约：问之前就看得到它做什么、不做什么、哪些事必须你本人确认。"""
    p = _latest_or_404(db, key)
    a = next((x for x in svc.definition(p).assistants if x.key == akey), None)
    if a is None:
        raise not_found("这个场景包里没有这位助手")
    return svc.contract(a)


@router.post("/packs/{key}/feedback")
def feedback(key: str, body: FeedbackIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db, scope="function")):
    p = _latest_or_404(db, key)
    svc.event(db, p, user.id, "helpful" if body.helpful else "unhelpful")
    return {"recorded": True}


# ------------------------------------------------------------------ 管理员（PACK-102 / 103）
def _own_pack(db: Session, pack_id: int) -> ScenarioPack:
    p = db.get(ScenarioPack, pack_id)
    if p is None:
        raise not_found("场景包不存在")
    return p


def _checked(data: dict) -> schema.PackDef:
    d, problems = schema.validate(data)
    if problems or d is None:
        raise bad_request("场景包定义有问题：" + "；".join(problems[:8]), "pack_invalid")
    return d


def _check_categories(db: Session, d: schema.PackDef) -> None:
    """包里引用的类目（答不了时的去处、发单模板）必须是开着的类目：否则用户点过去就是一个发不出去的单。"""
    from app.modules.task.models import Category

    names = {a.fallback_category for a in d.assistants if a.fallback_category} | {t.category for t in d.task_templates}
    if not names:
        return
    live = {n for (n,) in db.query(Category.name).filter(Category.name.in_(names), Category.active.is_(True))}
    missing = sorted(names - live)
    if missing:
        raise conflict(f"包里用到的类目不存在或已停用：{'、'.join(missing)}。先在「城市与类目」里开好", "pack_unknown_category")


def _new_version(db: Session, d: schema.PackDef, admin: User) -> ScenarioPack:
    pending = db.query(ScenarioPack.id).filter(ScenarioPack.key == d.key,
                                               ScenarioPack.status.in_(("draft", "review"))).first()
    if pending:
        raise conflict("这个场景包已有一个没上线的版本：先改它，或下线它", "pack_draft_exists")
    last = db.query(ScenarioPack.version).filter(ScenarioPack.key == d.key).order_by(ScenarioPack.version.desc()).first()
    now = utcnow()
    p = ScenarioPack(key=d.key, version=(last[0] + 1) if last else 1, title=d.title, segment=d.segment,
                     summary=d.summary, status="draft", definition=d.model_dump(mode="json"), score=d.score.total(),
                     created_by=admin.id, created_at=now, updated_at=now)
    db.add(p)
    db.flush()
    return p


@router.post("/admin/packs/validate")
def admin_validate(body: PackIn, admin: User = Depends(require_admin)):
    """只校验不保存：给编辑器用，也给 skill `scenario-discovery` 产出的文件用。"""
    d, problems = schema.validate(body.definition)
    return {"ok": not problems, "problems": problems, "score": d.score.total() if d else None}


@router.get("/admin/packs")
def admin_list(admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    rows = db.query(ScenarioPack).order_by(ScenarioPack.key, ScenarioPack.version.desc()).all()
    m = svc.metrics(db, sorted({p.key for p in rows}))
    return [{**_admin_row(p), "metrics": m[p.key]} for p in rows]


@router.post("/admin/packs", status_code=201)
def admin_create(body: PackIn, admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    from app.modules.admin.router import record_audit

    p = _new_version(db, _checked(body.definition), admin)
    record_audit(db, admin.id, "pack_create", "scenario_pack", p.id, f"{p.key} v{p.version}")
    return _admin_row(p)


@router.put("/admin/packs/{pack_id}")
def admin_update(pack_id: int, body: PackIn, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db, scope="function")):
    p = _own_pack(db, pack_id)
    if p.status != "draft":
        raise conflict("只有草稿能改；已上线的版本不可变，改动请建新版本", "pack_not_draft")
    d = _checked(body.definition)
    if d.key != p.key:
        raise bad_request("草稿不能改 key：换 key 等于另一个场景包", "pack_key_changed")
    p.title, p.segment, p.summary = d.title, d.segment, d.summary
    p.definition, p.score, p.updated_at = d.model_dump(mode="json"), d.score.total(), utcnow()
    db.add(p)
    db.flush()
    return _admin_row(p)


@router.post("/admin/packs/{pack_id}/submit")
def admin_submit(pack_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    p = _own_pack(db, pack_id)
    if p.status != "draft":
        raise conflict("只有草稿能提交审核", "pack_not_draft")
    _checked(p.definition)     # 规则可能在草稿保存之后更新过：提交时再过一遍
    p.status, p.updated_at = "review", utcnow()
    db.add(p)
    db.flush()
    return _admin_row(p)


@router.post("/admin/packs/{pack_id}/approve")
def admin_approve(pack_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    """四眼原则：上线的人不能是写它的人。上线后同 key 的旧版本转为 superseded（已启用的用户照常可用）。"""
    from app.modules.admin.router import record_audit

    p = _own_pack(db, pack_id)
    if p.status != "review":
        raise conflict("只有待审核的版本能上线", "pack_not_in_review")
    if p.created_by == admin.id:
        raise conflict("上线需要另一位管理员审核：写它的人不能自己批", "pack_four_eyes")
    d = _checked(p.definition)
    _check_categories(db, d)
    now = utcnow()
    for old in db.query(ScenarioPack).filter(ScenarioPack.key == p.key, ScenarioPack.status == "published"):
        old.status, old.updated_at = "superseded", now
        db.add(old)
    p.status, p.reviewed_by, p.published_at, p.updated_at = "published", admin.id, now, now
    db.add(p)
    record_audit(db, admin.id, "pack_publish", "scenario_pack", p.id, f"{p.key} v{p.version}")
    db.flush()
    return _admin_row(p)


@router.post("/admin/packs/{pack_id}/reject")
def admin_reject(pack_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    p = _own_pack(db, pack_id)
    if p.status != "review":
        raise conflict("只有待审核的版本能退回", "pack_not_in_review")
    p.status, p.updated_at = "draft", utcnow()
    db.add(p)
    db.flush()
    return _admin_row(p)


@router.post("/admin/packs/{pack_id}/retire")
def admin_retire(pack_id: int, body: RetireIn, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db, scope="function")):
    """下线要写理由（只增不删：记录留着、已启用用户装进去的副本留着）。"""
    from app.modules.admin.router import record_audit

    p = _own_pack(db, pack_id)
    if p.status == "retired":
        raise conflict("已经下线了", "pack_retired")
    p.status, p.retired_reason, p.updated_at = "retired", body.reason, utcnow()
    db.add(p)
    record_audit(db, admin.id, "pack_retire", "scenario_pack", p.id, body.reason)
    db.flush()
    return _admin_row(p)


@router.get("/admin/packs/radar")
def admin_radar(admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    return svc.radar(db)


@router.post("/admin/packs/import-seeds")
def admin_import_seeds(admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    """把仓库里的种子包（`app/modules/packs/seeds/*.json`）导成草稿：内容与最新版本一样的跳过。

    导进来是**草稿**，照样要另一位管理员审核才上线——仓库里的文件不能绕过四眼。
    """
    created, skipped, invalid = [], [], []
    for path in svc.seed_files():
        d, problems = schema.validate(svc.load_seed(path))
        if problems or d is None:
            invalid.append({"file": path.name, "problems": problems[:5]})
            continue
        last = (db.query(ScenarioPack).filter(ScenarioPack.key == d.key)
                .order_by(ScenarioPack.version.desc()).first())
        if last is not None and (last.definition == d.model_dump(mode="json") or last.status in ("draft", "review")):
            skipped.append(d.key)
            continue
        created.append(_admin_row(_new_version(db, d, admin))["key"])
    return {"created": created, "skipped": skipped, "invalid": invalid}
