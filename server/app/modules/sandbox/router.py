"""SBX-100 端侧隐私沙箱接口（128 号 spec）。

服务端在沙箱里只做三件事：记住「这个人开着沙箱」（于是把原文交给 AI 的接口拒绝、服务端替他跑的 AI 退回模板）、
给出审核过的端侧模型目录、让运营登记与上架模型。**本机助手的输入与输出都不经过这里。**
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import conflict, not_found
from app.core.sandbox import CLOUD_AI_ROUTES
from app.core.timefmt import iso
from app.core.admin_roles import require_role
from app.modules.account.models import User, utcnow

from .models import SandboxModel

router = APIRouter(tags=["sandbox"])
SHA256 = re.compile(r"^[0-9a-f]{64}$")
LOCAL_SKILLS = ("summarize", "checklist", "todos", "rewrite", "reply")


class SandboxIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ModelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=120)
    family: str = Field(default="", max_length=60)
    params_b: float = Field(default=0, ge=0, le=20)
    quant: str = Field(default="", max_length=20)
    file_format: str = Field(default="gguf", max_length=20)
    size_mb: int = Field(default=0, ge=0, le=20000)
    sha256: str = Field(default="", max_length=64)
    url: str = Field(default="", max_length=500)
    license: str = Field(default="", max_length=100)
    min_ram_gb: float = Field(default=0, ge=0, le=64)
    languages: list[str] = Field(default_factory=list, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=300)


class RetireIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=2, max_length=200)


def _state(user: User) -> dict:
    p = user.privacy or {}
    return {"enabled": bool(p.get("sandbox")), "since": p.get("sandbox_since") or None,
            "blocked_endpoints": len(CLOUD_AI_ROUTES),
            "note": "开着时：摘要、拆清单、抽待办、改写、起草回复都在手机上本机做，原文不发到云端；"
                    "要交给云端助手的接口会被拦下。同步到云端前会先脱敏，并由你确认。"}


def _dump(m: SandboxModel, admin: bool = False) -> dict:
    out = {"id": m.id, "key": m.key, "name": m.name, "family": m.family, "params_b": m.params_b, "quant": m.quant,
           "file_format": m.file_format, "size_mb": m.size_mb, "sha256": m.sha256, "url": m.url, "license": m.license,
           "min_ram_gb": m.min_ram_gb, "languages": m.languages or [], "skills": m.skills or [], "note": m.note,
           "published_at": iso(m.published_at)}
    if admin:
        out.update({"status": m.status, "created_by": m.created_by, "reviewed_by": m.reviewed_by,
                    "retired_reason": m.retired_reason, "created_at": iso(m.created_at)})
    return out


# ------------------------------------------------------------------ 开关（SBX-101）
@router.get("/users/me/sandbox")
def my_sandbox(user: User = Depends(get_current_user)):
    return _state(user)


@router.put("/users/me/sandbox")
def set_sandbox(body: SandboxIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    p = dict(user.privacy or {})
    if body.enabled and not p.get("sandbox"):
        p["sandbox_since"] = iso(utcnow())
    if not body.enabled:
        p.pop("sandbox_since", None)
    p["sandbox"] = body.enabled
    user.privacy = p
    db.add(user)
    db.flush()
    return _state(user)


# ------------------------------------------------------------------ 模型目录（SBX-106）
@router.get("/sandbox/models")
def models(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.query(SandboxModel).filter(SandboxModel.status == "published").order_by(SandboxModel.params_b, SandboxModel.id).all()
    return {"items": [_dump(m) for m in rows],
            "note": "模型文件从登记的地址直接下载到手机，不经平台；下载完按 sha256 校验，对不上就删掉不用"}


@router.get("/admin/sandbox/models")
def admin_models(admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    return [_dump(m, admin=True) for m in db.query(SandboxModel).order_by(SandboxModel.id.desc()).all()]


def _validate(body: ModelIn) -> None:
    bad = [s for s in body.skills if s not in LOCAL_SKILLS]
    if bad:
        raise conflict(f"本机技能只能是 {'、'.join(LOCAL_SKILLS)}，不认识：{'、'.join(bad)}", "sandbox_model_bad_skill")


@router.post("/admin/sandbox/models", status_code=201)
def create_model(body: ModelIn, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    _validate(body)
    if db.query(SandboxModel.id).filter(SandboxModel.key == body.key).first():
        raise conflict("这个模型标识已经登记过了，换一个或者改已有的那条", "sandbox_model_exists")
    m = SandboxModel(**{**body.model_dump(), "sha256": body.sha256.lower()}, created_by=admin.id)
    db.add(m)
    db.flush()
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, "sandbox_model_create", "sandbox_model", m.id, m.key)
    return _dump(m, admin=True)


@router.patch("/admin/sandbox/models/{model_id}")
def update_model(model_id: int, body: ModelIn, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    m = db.get(SandboxModel, model_id)
    if m is None:
        raise not_found("模型不存在")
    if m.status != "draft":
        raise conflict("只有草稿能改：已上架的要先下架，再登记一条新的", "sandbox_model_not_draft")
    _validate(body)
    for k, v in body.model_dump().items():
        setattr(m, k, v.lower() if k == "sha256" else v)
    db.add(m)
    db.flush()
    return _dump(m, admin=True)


@router.post("/admin/sandbox/models/{model_id}/publish")
def publish_model(model_id: int, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    m = db.get(SandboxModel, model_id)
    if m is None:
        raise not_found("模型不存在")
    if m.status != "draft":
        raise conflict("只有草稿能上架", "sandbox_model_not_draft")
    if m.created_by == admin.id:
        raise conflict("上架需要另一位管理员审核：登记它的人不能自己批", "sandbox_model_four_eyes")
    missing = [n for n, ok in (("sha256（64 位十六进制）", bool(SHA256.match(m.sha256 or ""))),
                               ("https 下载地址", (m.url or "").startswith("https://")),
                               ("文件大小", m.size_mb > 0), ("许可证", bool(m.license)),
                               ("最低内存", m.min_ram_gb > 0)) if not ok]
    if missing:
        raise conflict(f"还缺：{'、'.join(missing)}——手机下载后要靠这些校验和判断能不能跑", "sandbox_model_incomplete")
    m.status, m.reviewed_by, m.published_at = "published", admin.id, utcnow()
    db.add(m)
    db.flush()
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, "sandbox_model_publish", "sandbox_model", m.id, m.key)
    return _dump(m, admin=True)


@router.post("/admin/sandbox/models/{model_id}/retire")
def retire_model(model_id: int, body: RetireIn, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    m = db.get(SandboxModel, model_id)
    if m is None:
        raise not_found("模型不存在")
    m.status, m.retired_reason = "retired", body.reason
    db.add(m)
    db.flush()
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, "sandbox_model_retire", "sandbox_model", m.id, body.reason)
    return _dump(m, admin=True)
