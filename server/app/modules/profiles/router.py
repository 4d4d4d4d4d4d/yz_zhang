"""PROF-100 任务画像与能力画像接口（126 号 spec）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.core.timefmt import UtcDatetime
from app.modules.account.models import User

from . import service as svc

router = APIRouter(tags=["profiles"])


class DraftIn(BaseModel):
    """发布页的草稿：只用来算画像，不落库。"""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=10000)
    category: str = Field(default="", max_length=50)
    budget_cents: int = Field(default=0, ge=0, le=10_000_000_000)
    is_remote: bool = False
    city: str = Field(default="", max_length=50)
    lat: float | None = None
    deadline: UtcDatetime | None = None
    required_skills: list[str] = Field(default_factory=list, max_length=20)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=20)


@router.post("/profiles/task-draft")
def draft_profile(body: DraftIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """发布页实时调用：还缺什么、价格在什么位置、有什么风险。"""
    return svc.task_profile(db, body.model_dump())


@router.get("/tasks/{task_id}/profile")
def task_profile(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """看得到这单的人才能看画像：公开招募中的任何人，或者双方。"""
    from app.modules.task.models import Task

    t = db.get(Task, task_id)
    if t is None or (user.id not in (t.creator_id, t.executor_id)
                     and (t.status == "draft" or t.visibility != "public")):
        raise not_found("任务不存在")
    return {"task_id": t.id, **svc.task_profile(db, svc.task_fields(t))}


@router.get("/users/me/capability")
def my_capability(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return svc.capability(db, user, public=False)


@router.get("/users/{user_id}/capability")
def user_capability(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """对外的能力画像：资料不公开、封禁、注销的人一律 404（与公开资料同一条可见性规则）。"""
    target = db.get(User, user_id)
    if (target is None or target.is_deleted or target.is_banned
            or ((target.privacy or {}).get("profile_public") is False and target.id != user.id)):
        raise not_found("用户不存在")
    return svc.capability(db, target, public=target.id != user.id)
