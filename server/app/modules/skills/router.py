"""SKL-100 技能概念表接口（135 号 spec）：给两端提示「这个技能会按哪个概念匹配」，运营在后台维护。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import conflict, not_found
from app.core.timefmt import iso
from app.core.admin_roles import require_role
from app.modules.account.models import User, utcnow

from . import service as svc
from .models import SkillConcept

router = APIRouter(tags=["skills"])


class ConceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40)
    aliases: list[str] = Field(default_factory=list, max_length=30)


@router.get("/skills/concepts")
def list_concepts(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return {"items": svc.concepts(db)}


@router.get("/skills/normalize")
def normalize(skills: str = Query(default="", max_length=500), user: User = Depends(get_current_user),
              db: Session = Depends(get_db, scope="function")):
    """SKL-106 「这些技能会按什么来匹配」：认得出的给规范名，认不出的原样（不猜）。"""
    idx = svc.index(db)
    words = [w for w in (x.strip() for x in skills.replace("，", ",").replace("、", ",").split(",")) if w][:30]
    return {"items": [{"skill": w, "canonical": svc.canonical(w, idx), "known": svc.norm(w) in idx} for w in words]}


def _dump(c: SkillConcept) -> dict:
    return {"id": c.id, "name": c.name, "aliases": c.aliases or [], "status": c.status, "updated_by": c.updated_by,
            "updated_at": iso(c.updated_at)}


@router.get("/admin/skill-concepts")
def admin_concepts(admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    """后台：生效的概念（含种子）与后台改过的记录。"""
    return {"effective": svc.concepts(db),
            "overrides": [_dump(c) for c in db.query(SkillConcept).order_by(SkillConcept.id.desc()).all()]}


@router.post("/admin/skill-concepts")
def upsert_concept(body: ConceptIn, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    """新增或改一个概念（同名覆盖种子）。一个别名不能同时属于两个概念。"""
    name = body.name.strip()
    aliases = list(dict.fromkeys(a.strip() for a in body.aliases if a.strip() and svc.norm(a) != svc.norm(name)))
    idx = svc.index(db)
    clash = [a for a in [name, *aliases] if idx.get(svc.norm(a)) not in (None, name)]
    if clash:
        raise conflict(f"这些写法已经属于别的概念：{'、'.join(f'{a}（{idx[svc.norm(a)]}）' for a in clash)}", "skill_alias_taken")
    c = db.query(SkillConcept).filter(SkillConcept.name == name).first()
    if c is None:
        c = SkillConcept(name=name, updated_by=admin.id)
    c.aliases, c.status, c.updated_by, c.updated_at = aliases, "active", admin.id, utcnow()
    db.add(c)
    db.flush()
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, "skill_concept_upsert", "skill_concept", c.id, f"{name}：{'、'.join(aliases)}"[:300])
    return _dump(c)


@router.post("/admin/skill-concepts/{concept_id}/retire")
def retire_concept(concept_id: int, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    """下线：这个概念（含种子里的同名概念）不再参与匹配。"""
    c = db.get(SkillConcept, concept_id)
    if c is None:
        raise not_found("概念不存在")
    c.status, c.updated_by, c.updated_at = "retired", admin.id, utcnow()
    db.add(c)
    db.flush()
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, "skill_concept_retire", "skill_concept", c.id, c.name)
    return _dump(c)
