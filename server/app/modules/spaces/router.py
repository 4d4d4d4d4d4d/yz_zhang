"""Opt-in public spaces. Never crawl remote URLs or serialize private account fields."""
from typing import Literal
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, not_found
from app.modules.account.models import User
from app.modules.task.service import machine_review
from .models import PersonalSpace

router = APIRouter(tags=['spaces'])


class SpaceItem(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    kind: Literal['work', 'article', 'video', 'shop', 'live', 'service'] = 'work'
    summary: str = Field(default='', max_length=500)
    url: str = Field(default='', max_length=1500)

    @field_validator('url')
    @classmethod
    def safe_link(cls, value):
        if not value:
            return value
        try:
            p = urlsplit(value)
            if p.scheme != 'https' or not p.hostname or p.username or p.password or any(ord(c) <= 32 for c in value) or '\\' in value:
                raise ValueError()
            _ = p.port
        except ValueError:
            raise ValueError('外部链接须为完整 HTTPS 地址，不可包含登录凭据')
        return value


class SpaceIn(BaseModel):
    revision: int = Field(ge=0)
    published: bool = False
    headline: str = Field(default='', max_length=120)
    introduction: str = Field(default='', max_length=1600)
    theme: Literal['clay', 'moss', 'ink'] = 'clay'
    items: list[SpaceItem] = Field(default_factory=list, max_length=24)


def visible(query):
    return query.filter(PersonalSpace.published.is_(True), User.is_deleted.is_(False), User.is_banned.is_(False),
        or_(User.privacy['profile_public'].as_boolean().is_(None), User.privacy['profile_public'].as_boolean().is_(True)))


def dump(space, user, full=True):
    result = {'user_id': user.id, 'nickname': user.nickname, 'headline': space.headline,
        'theme': space.theme, 'kind': 'agent' if user.is_agent else 'organization' if user.is_team or user.is_venture else 'person',
        'items_count': len(space.items), 'accepting_orders': user.accepting_orders}
    if full:
        result.update(introduction=space.introduction, items=space.items)
    else:
        result['preview'] = space.items[:2]
    return result


@router.get('/spaces')
def discover_spaces(response: Response, q: str = Query(default='', max_length=80), after: int = Query(default=0, ge=0),
                    limit: int = Query(default=18, ge=1, le=48), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    query = visible(db.query(PersonalSpace, User).join(User, User.id == PersonalSpace.user_id))
    if q.strip():
        query = query.filter(or_(User.nickname.contains(q.strip(), autoescape=True),
            PersonalSpace.headline.contains(q.strip(), autoescape=True), PersonalSpace.introduction.contains(q.strip(), autoescape=True)))
    rows = query.filter(PersonalSpace.user_id > after).order_by(PersonalSpace.user_id).limit(limit + 1).all()
    return {'items': [dump(s, u, False) for s, u in rows[:limit]],
        'next_cursor': rows[limit - 1][0].user_id if len(rows) > limit else None}


@router.get('/spaces/me')
def own_space(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    s = db.get(PersonalSpace, user.id)
    if not s:
        s = PersonalSpace(user_id=user.id, headline='', introduction='', theme='clay', items=[], published=False, revision=0)
    return {**dump(s, user), 'revision': s.revision, 'published': s.published,
        'profile_public': (user.privacy or {}).get('profile_public') is not False}


@router.put('/spaces/me')
def save_space(body: SpaceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Serialize saves for the same owner; revision prevents silent edits from stale browser tabs.
    db.query(User).filter(User.id == user.id).with_for_update().one()
    s = db.query(PersonalSpace).filter(PersonalSpace.user_id == user.id).populate_existing().first()
    if body.revision != (s.revision if s else 0):
        raise conflict('空间已在其他窗口更新，请重新打开后编辑', 'space_revision_conflict')
    if body.published and (user.privacy or {}).get('profile_public') is False:
        raise bad_request('请先在账户隐私设置中允许公开个人资料', 'profile_private')
    if body.published and not body.headline.strip():
        raise bad_request('公开前请写一句介绍', 'headline_required')
    text = ' '.join([body.headline, body.introduction] + [i.title + ' ' + i.summary + ' ' + i.url for i in body.items])
    if machine_review(text):
        raise bad_request('空间内容需要调整后再发布', 'space_content_rejected')
    if s is None:
        s = PersonalSpace(user_id=user.id)
        db.add(s)
    for key, value in body.model_dump(exclude={'revision'}).items():
        setattr(s, key, value)
    s.revision = body.revision + 1
    db.flush()
    return {**dump(s, user), 'revision': s.revision, 'published': s.published,
        'profile_public': (user.privacy or {}).get('profile_public') is not False}


@router.get('/spaces/{user_id}')
def public_space(user_id: int, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    row = visible(db.query(PersonalSpace, User).join(User, User.id == PersonalSpace.user_id)).filter(User.id == user_id).first()
    if not row:
        raise not_found('空间未公开或已收起')
    return dump(*row)
