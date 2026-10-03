"""Versioned records of external legal structures, separate from project contributions.

This records declared source documents; it never incorporates an entity, issues
shares, changes the venture contribution ledger or certifies legal validity.
"""
import hashlib
import json
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column
from app.core.db import Base, get_db
from app.core.deps import require_verified, get_current_user
from app.core.errors import forbidden, bad_request, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow
from .models import Venture
from .service import is_member

router=APIRouter(tags=['organization-records'])
FORMS={
 'project_cooperation':'项目合作（未声明登记主体）',
 'sole_proprietor':'个体／独资经营主体',
 'limited_company':'有限责任公司',
 'joint_stock_company':'股份有限公司',
 'general_partnership':'普通合伙企业',
 'limited_partnership':'有限合伙企业',
 'other':'其他法域／组织形式',
}


class OrganizationRecord(Base):
    __tablename__='organization_records'
    __table_args__=(UniqueConstraint('venture_id','revision',name='uq_org_revision'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    venture_id: Mapped[int]=mapped_column(Integer,index=True)
    revision: Mapped[int]=mapped_column(Integer)
    submitted_by: Mapped[int]=mapped_column(Integer)
    entity_type: Mapped[str]=mapped_column(String(32))
    jurisdiction: Mapped[str]=mapped_column(String(80))
    registered_name: Mapped[str]=mapped_column(String(200))
    registration_number: Mapped[str]=mapped_column(String(100))
    representative_user_id: Mapped[int]=mapped_column(Integer)
    governance_basis: Mapped[str]=mapped_column(String(4000))
    document_references: Mapped[list]=mapped_column(JSON)
    rights: Mapped[list]=mapped_column(JSON)
    record_hash: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class RightIn(BaseModel):
    holder_name: str=Field(min_length=2,max_length=200)
    role: Literal['shareholder','general_partner','limited_partner','cooperator','proprietor']
    subscribed_cents: int=Field(default=0,ge=0,le=1_000_000_000)
    paid_cents: int=Field(default=0,ge=0,le=1_000_000_000)
    interest_description: str=Field(min_length=2,max_length=1000)
    source_document: str=Field(min_length=2,max_length=300)
    @model_validator(mode='after')
    def paid_limit(self):
        if self.paid_cents > self.subscribed_cents:
            raise ValueError('实缴不能超过本记录的认缴金额')
        return self


class OrganizationIn(BaseModel):
    entity_type: Literal['project_cooperation','sole_proprietor','limited_company','joint_stock_company','general_partnership','limited_partnership','other']
    jurisdiction: str=Field(min_length=2,max_length=80)
    registered_name: str=Field(min_length=2,max_length=200)
    registration_number: str=Field(default='',max_length=100)
    representative_user_id: int=Field(gt=0)
    governance_basis: str=Field(min_length=10,max_length=4000)
    document_references: list[str]=Field(min_length=1,max_length=20)
    rights: list[RightIn]=Field(default_factory=list,max_length=100)
    acknowledge_record_only: Literal[True]
    acknowledge_member_visibility: Literal[True]


def _access(db,venture_id,user):
    v=db.get(Venture,venture_id)
    if not v:
        raise not_found('合作体不存在')
    if not is_member(db,venture_id,user.id):
        raise forbidden('仅合作体成员可读取或提交主体资料')
    return v


def _dump(r):
    return {'id':r.id,'venture_id':r.venture_id,'revision':r.revision,
        'submitted_by':r.submitted_by,'entity_type':r.entity_type,'jurisdiction':r.jurisdiction,
        'registered_name':r.registered_name,'registration_number':r.registration_number,
        'representative_user_id':r.representative_user_id,'governance_basis':r.governance_basis,
        'document_references':r.document_references,'rights':r.rights,
        'record_hash':r.record_hash,'created_at':iso(r.created_at),
        'verification_status':'declared_unverified',
        'notice':'这是成员提交的外部主体与权益文件记录，尚未核验，不是登记、确权或可靠电子签名。项目贡献份额不转换为公司股权或合伙权益。'}


@router.get('/ventures/{venture_id}/organization-records')
def list_records(venture_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    _access(db,venture_id,user)
    rows=db.query(OrganizationRecord).filter_by(venture_id=venture_id).order_by(OrganizationRecord.revision.desc()).all()
    return [_dump(r) for r in rows]


@router.post('/ventures/{venture_id}/organization-records',status_code=201)
def add_record(venture_id:int,body:OrganizationIn,user:User=Depends(require_verified),db:Session=Depends(get_db)):
    venture=_access(db,venture_id,user)
    from app.modules.legal.consent import require_current_agreement
    require_current_agreement(db,user.id)
    representative=db.get(User,body.representative_user_id)
    if not representative or not is_member(db,venture_id,representative.id) or representative.is_agent or representative.is_venture:
        raise bad_request('经办责任人须为本合作体自然人成员')
    if body.entity_type!='project_cooperation' and not body.registration_number.strip():
        raise bad_request('已登记主体需提供登记编号；未登记项目请选择项目合作')
    if any(not x.strip() or len(x)>300 for x in body.document_references):
        raise bad_request('文件依据不能为空或超过300字符')
    roles={r.role for r in body.rights}
    allowed={
        'limited_company':{'shareholder'},'joint_stock_company':{'shareholder'},
        'general_partnership':{'general_partner'},'limited_partnership':{'general_partner','limited_partner'},
        'sole_proprietor':{'proprietor'},'project_cooperation':{'cooperator'},'other':set(roles),
    }[body.entity_type]
    if roles-allowed:
        raise bad_request('权益角色与所选组织形式不一致')
    # Serialize revision assignment for this venture, preserving prior versions.
    db.query(Venture).filter_by(user_id=venture_id).update({'status':Venture.status})
    latest=db.query(OrganizationRecord).filter_by(venture_id=venture_id).order_by(OrganizationRecord.revision.desc()).first()
    payload=body.model_dump(exclude={'acknowledge_record_only','acknowledge_member_visibility'})
    digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    row=OrganizationRecord(venture_id=venture_id,revision=latest.revision+1 if latest else 1,
                           submitted_by=user.id,record_hash=digest,**payload)
    db.add(row);db.flush()
    from app.modules.notification.service import notify
    from .service import members
    for member in members(db,venture_id):
        if member.user_id!=user.id:
            notify(db,member.user_id,'system','组织资料新版本',
                   f'「{venture.name}」新增第 {row.revision} 版主体与权益记录，请查看文件依据；本记录尚未核验，不改变项目贡献账。')
    return _dump(row)
