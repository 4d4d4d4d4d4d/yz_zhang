"""KB-100 个人知识库接口（122 号 spec）。全部只对本人可见：别人的 id 一律 404，不泄露是否存在。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from . import service as svc
from .models import NbMethod, NbNote

router = APIRouter(tags=["notebook"])

Kind = Literal["note", "link", "minutes"]
NoteStatus = Literal["inbox", "filed", "archived"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_tags(v):
    if v is None:
        return v
    out = []
    for t in v:
        t = t.strip().lstrip("#")[:20]
        if t and t not in out:
            out.append(t)
    return out


def _check_url(v: str) -> str:
    v = v.strip()
    if v and not svc.is_url(v):
        raise ValueError("链接只支持 http / https，且不超过 500 字")
    return v


class NoteIn(_In):
    body: str = Field(default="", max_length=20000)
    title: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=500)
    kind: Kind | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)
    status: NoteStatus = "inbox"
    project_id: int | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        return _clean_tags(v)

    @field_validator("url")
    @classmethod
    def _url(cls, v):
        return _check_url(v)


class NotePatch(_In):
    revision: int | None = Field(default=None, ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=20000)
    url: str | None = Field(default=None, max_length=500)
    kind: Kind | None = None
    tags: list[str] | None = Field(default=None, max_length=10)
    status: NoteStatus | None = None
    pinned: bool | None = None
    project_id: int | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        return _clean_tags(v)

    @field_validator("url")
    @classmethod
    def _url(cls, v):
        return v if v is None else _check_url(v)


class AskIn(_In):
    q: str = Field(min_length=1, max_length=200)


class TodoIn(_In):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime | None = None


class TodosIn(_In):
    items: list[TodoIn] = Field(min_length=1, max_length=svc.LIMITS["todos"])
    project_id: int | None = None


class StepIn(_In):
    title: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=500)


class DistillIn(_In):
    note_ids: list[int] = Field(min_length=1, max_length=20)


class MethodIn(_In):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=500)
    steps: list[StepIn] = Field(min_length=1, max_length=svc.LIMITS["steps"])
    source_note_ids: list[int] = Field(default_factory=list, max_length=20)


class MethodPatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=500)
    steps: list[StepIn] | None = Field(default=None, min_length=1, max_length=svc.LIMITS["steps"])


class ApplyIn(_In):
    item_id: int


# ------------------------------------------------------------------ 工具
def _own(db: Session, model, obj_id: int, user: User, what: str):
    obj = db.get(model, obj_id)
    if obj is None or obj.owner_id != user.id:
        raise not_found(f"{what}不存在")
    return obj


def _count(db: Session, model, user: User) -> int:
    return db.query(func.count(model.id)).filter(model.owner_id == user.id).scalar() or 0


def _check_project(db: Session, project_id: int | None, user: User) -> None:
    if project_id is not None:
        from app.modules.workbench.models import WbProject

        _own(db, WbProject, project_id, user, "项目")


def _brief(n: NbNote, snippet: str | None = None) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "url": n.url, "status": n.status,
            "tags": n.tags or [], "pinned": n.pinned, "project_id": n.project_id, "revision": n.revision,
            "excerpt": snippet if snippet is not None else (n.body[:140] + ("…" if len(n.body) > 140 else "")),
            "created_at": iso(n.created_at), "updated_at": iso(n.updated_at)}


def _full(n: NbNote) -> dict:
    return {**_brief(n), "body": n.body}


# AGT-095（168 号 spec）方法的效果：按它拆过的编排做成了几个、失败几个、花了多少。做完的少于 3 个不给成功率
MIN_FINISHED_FOR_RATE = 3


def method_stats(db: Session, ids: list[int]) -> dict[int, dict]:
    from sqlalchemy import func

    from app.modules.orchestrator.models import Mission

    out = {i: {"total": 0, "succeeded": 0, "failed": 0, "spent_cents": 0, "versions": {}} for i in ids}
    if not ids:
        return out
    # AGT-097（239 号 spec）多按版本分一层，仍是一次查询
    rows = (db.query(Mission.method_id, Mission.method_version, Mission.status, func.count(Mission.id),
                     func.coalesce(func.sum(Mission.spent_cents), 0))
            .filter(Mission.method_id.in_(ids)).group_by(Mission.method_id, Mission.method_version, Mission.status).all())
    for mid, ver, status, n, spent in rows:
        v = out[mid]["versions"].setdefault(ver, {"total": 0, "succeeded": 0, "failed": 0, "spent_cents": 0})
        for o in (out[mid], v):
            o["total"] += int(n)
            o["spent_cents"] += int(spent)
            if status == "succeeded":
                o["succeeded"] += int(n)
            elif status in ("failed", "cancelled"):
                o["failed"] += int(n)
    return out


def _rate(st: dict) -> float | None:
    finished = st["succeeded"] + st["failed"]
    return round(st["succeeded"] / finished, 2) if finished >= MIN_FINISHED_FOR_RATE else None


def _versions(st: dict) -> list[dict]:
    """AGT-097 每一版各自的效果，新版在前；记版本之前建的编排归在 version=null 一组、排最后。"""
    vs = st.get("versions") or {}
    keys = sorted((k for k in vs if k is not None), reverse=True) + ([None] if None in vs else [])
    return [{"version": k, "missions_total": vs[k]["total"], "missions_succeeded": vs[k]["succeeded"],
             "missions_failed": vs[k]["failed"], "missions_spent_cents": vs[k]["spent_cents"],
             "success_rate": _rate(vs[k])} for k in keys]


def _dump_method(m: NbMethod, stats: dict | None = None) -> dict:
    st = stats if stats is not None else {"total": 0, "succeeded": 0, "failed": 0, "spent_cents": 0}
    return {"id": m.id, "name": m.name, "description": m.description, "steps": m.steps or [],
            "source_note_ids": m.source_note_ids or [], "uses": m.uses,
            "missions_total": st["total"], "missions_succeeded": st["succeeded"], "missions_failed": st["failed"],
            "missions_spent_cents": st["spent_cents"],
            "success_rate": _rate(st),
            "version": m.version or 1, "versions": _versions(st),
            "created_at": iso(m.created_at), "updated_at": iso(m.updated_at)}


def _own_notes(db: Session, ids: list[int], user: User) -> list[NbNote]:
    """只认自己的笔记：混进别人的 id 时整批 404，而不是悄悄丢掉（否则能用来探测 id 是否存在）。"""
    rows = db.query(NbNote).filter(NbNote.id.in_(ids), NbNote.owner_id == user.id).all()
    if len({n.id for n in rows}) != len(set(ids)):
        raise not_found("笔记不存在")
    by_id = {n.id: n for n in rows}
    return [by_id[i] for i in dict.fromkeys(ids)]


# ------------------------------------------------------------------ 笔记
@router.get("/notebook/notes")
def list_notes(q: str = Query(default="", max_length=200), tag: str = Query(default="", max_length=20),
               status: NoteStatus | None = None, kind: Kind | None = None,
               limit: int = Query(default=50, ge=1, le=200),
               user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """不给 status 时不含已归档；给了 q 时按相关度排序、摘要取命中处。"""
    hits = svc.search(db, user.id, q, tag, status, kind, limit)
    ts = svc.terms(q)
    return [_brief(n, svc.snippet(n.body or n.url, ts) if ts else None) for n, _ in hits]


@router.post("/notebook/notes", status_code=201)
def create_note(body: NoteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """随手记：一句话、一段纪要或一个链接。链接只存地址，服务端不去抓取。"""
    if not body.body.strip() and not body.url and not body.title.strip():
        raise bad_request("记点什么吧：正文、标题或链接至少一项", "note_empty")
    if _count(db, NbNote, user) >= svc.LIMITS["notes"]:
        raise conflict(f"笔记数量已达上限（{svc.LIMITS['notes']}），请先归档导出后删除不用的", "nb_limit_reached")
    _check_project(db, body.project_id, user)
    c = svc.capture(body.body, body.title, body.url, body.kind)
    now = utcnow()
    n = NbNote(owner_id=user.id, kind=c["kind"], title=c["title"], body=c["body"], url=c["url"], tags=body.tags,
               status=body.status, project_id=body.project_id, created_at=now, updated_at=now)
    db.add(n)
    db.flush()
    return _full(n)


@router.get("/notebook/notes/{note_id}")
def get_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return _full(_own(db, NbNote, note_id, user, "笔记"))


@router.patch("/notebook/notes/{note_id}")
def update_note(note_id: int, body: NotePatch, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    n = _own(db, NbNote, note_id, user, "笔记")
    if body.revision is not None and body.revision != n.revision:
        raise conflict("这条笔记已在其他窗口或设备上改过，请刷新后再改", "nb_revision_conflict")
    data = body.model_dump(exclude_unset=True)
    data.pop("revision", None)
    if "project_id" in data:
        _check_project(db, data["project_id"], user)
    for k, v in data.items():
        if v is not None or k == "project_id":
            setattr(n, k, v.strip() if k == "title" else v)
    # 整理过（改了标签、标题或正文）就出收件箱，除非这次明确设了状态
    if n.status == "inbox" and "status" not in data and ({"tags", "title", "body"} & data.keys()):
        n.status = "filed"
    n.updated_at = utcnow()
    n.revision += 1
    db.add(n)
    db.flush()
    return _full(n)


@router.delete("/notebook/notes/{note_id}")
def delete_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    db.delete(_own(db, NbNote, note_id, user, "笔记"))
    return {"deleted": True}


@router.get("/notebook/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """收件箱数、总数、标签与方法数。标签按次数排序（最多 50 个）。"""
    by_status = dict(db.query(NbNote.status, func.count(NbNote.id)).filter(NbNote.owner_id == user.id)
                     .group_by(NbNote.status).all())
    counts: dict[str, int] = {}
    for (tags,) in db.query(NbNote.tags).filter(NbNote.owner_id == user.id, NbNote.status != "archived"):
        for t in tags or []:
            counts[t] = counts.get(t, 0) + 1
    tags = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:50]
    return {"total": sum(by_status.values()), "inbox": by_status.get("inbox", 0),
            "archived": by_status.get("archived", 0), "methods": _count(db, NbMethod, user),
            "limit": svc.LIMITS["notes"], "tags": [{"tag": t, "count": c} for t, c in tags]}


# ------------------------------------------------------------------ 助手引用（KB-104）
@router.post("/notebook/ask")
def ask(body: AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return svc.ask(db, user.id, body.q)


@router.get("/notebook/related")
def related(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """工作台某个任务的相关笔记：做这件事时，把自己以前记过的东西摆到眼前。"""
    from app.modules.workbench.models import WbItem

    item = _own(db, WbItem, item_id, user, "任务")
    return svc.related(db, user.id, f"{item.title} {' '.join(item.tags or [])} {item.category}")


# ------------------------------------------------------------------ 纪要抽待办（KB-105）
@router.post("/notebook/notes/{note_id}/extract-todos")
def extract_todos(note_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    """只出草稿，不写库：人看过、改过，再调 `/todos` 放进工作台。"""
    n = _own(db, NbNote, note_id, user, "笔记")
    items = svc.extract_todos(n.body, utcnow())
    return {"note_id": n.id, "items": [{"title": i["title"], "due_at": iso(i["due_at"]), "line": i["line"]}
                                       for i in items]}


@router.post("/notebook/notes/{note_id}/todos", status_code=201)
def add_todos(note_id: int, body: TodosIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db, scope="function")):
    from app.modules.workbench import service as wsvc
    from app.modules.workbench.models import WbItem, WbLog

    n = _own(db, NbNote, note_id, user, "笔记")
    project_id = body.project_id if body.project_id is not None else n.project_id
    _check_project(db, project_id, user)
    if wsvc.count(db, WbItem, user.id) + len(body.items) > wsvc.LIMITS["items"]:
        raise conflict(f"工作台任务数量已达上限（{wsvc.LIMITS['items']}）", "wb_limit_reached")
    now = utcnow()
    made = []
    for t in body.items:
        item = WbItem(owner_id=user.id, project_id=project_id, title=t.title.strip(),
                      notes=f"来自笔记「{n.title}」", due_at=wsvc.to_utc(t.due_at), created_at=now, updated_at=now)
        db.add(item)
        made.append(item)
    db.flush()
    for item in made:
        db.add(WbLog(item_id=item.id, owner_id=user.id, kind="assistant", body=f"从笔记「{n.title}」抽出"))
    db.flush()
    ctx = wsvc.ListCtx(db, made)
    return [wsvc.dump_item(i, ctx) for i in made]


# ------------------------------------------------------------------ 个人方法（KB-106）
@router.post("/notebook/methods/distill")
def distill(body: DistillIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """把几条笔记里的步骤收成一份方法草稿。只出草稿；没找到步骤就如实说，让人手写。"""
    return svc.distill(_own_notes(db, body.note_ids, user))


@router.get("/notebook/methods")
def list_methods(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.query(NbMethod).filter(NbMethod.owner_id == user.id).order_by(NbMethod.uses.desc(), NbMethod.id).all()
    stats = method_stats(db, [m.id for m in rows])   # 一次查完，不按方法逐个查
    return [_dump_method(m, stats[m.id]) for m in rows]


@router.post("/notebook/methods", status_code=201)
def create_method(body: MethodIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    if _count(db, NbMethod, user) >= svc.LIMITS["methods"]:
        raise conflict(f"方法数量已达上限（{svc.LIMITS['methods']}）", "nb_limit_reached")
    if body.source_note_ids:
        _own_notes(db, body.source_note_ids, user)
    now = utcnow()
    m = NbMethod(owner_id=user.id, name=body.name.strip(), description=body.description,
                 steps=[s.model_dump() for s in body.steps], source_note_ids=list(dict.fromkeys(body.source_note_ids)),
                 created_at=now, updated_at=now)
    db.add(m)
    db.flush()
    return _dump_method(m, method_stats(db, [m.id])[m.id])


@router.patch("/notebook/methods/{method_id}")
def update_method(method_id: int, body: MethodPatch, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    m = _own(db, NbMethod, method_id, user, "方法")
    if body.name is not None:
        m.name = body.name.strip()
    if body.description is not None:
        m.description = body.description
    if body.steps is not None:
        steps = [s.model_dump() for s in body.steps]
        if steps != (m.steps or []):
            m.version = (m.version or 1) + 1      # AGT-097 只有步骤真的变了才升版；改名、改说明不升
        m.steps = steps
    m.updated_at = utcnow()
    db.add(m)
    db.flush()
    return _dump_method(m, method_stats(db, [m.id])[m.id])


@router.delete("/notebook/methods/{method_id}")
def delete_method(method_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    db.delete(_own(db, NbMethod, method_id, user, "方法"))
    return {"deleted": True}


@router.post("/notebook/methods/{method_id}/apply", status_code=201)
def apply_method(method_id: int, body: ApplyIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db, scope="function")):
    """把方法套到工作台的一个任务上：步骤变成它的清单子项（上限与层级规则与手动加清单相同）。"""
    from app.modules.workbench import router as wb

    m = _own(db, NbMethod, method_id, user, "方法")
    out = wb.add_children(body.item_id, wb.ChildrenIn(steps=[wb.StepIn(**s) for s in m.steps]), user, db)
    m.uses += 1
    db.add(m)
    db.flush()
    return out


# ------------------------------------------------------------------ 导出（KB-108）
@router.get("/notebook/export")
def export(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    notes = db.query(NbNote).filter(NbNote.owner_id == user.id).order_by(NbNote.id).all()
    methods = db.query(NbMethod).filter(NbMethod.owner_id == user.id).order_by(NbMethod.id).all()
    return {"filename": f"knowledge-{utcnow():%Y%m%d}.md", "notes": len(notes), "methods": len(methods),
            "markdown": svc.export_markdown(notes, methods)}
