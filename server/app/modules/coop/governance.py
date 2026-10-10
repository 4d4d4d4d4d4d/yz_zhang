"""Unanimous project payout consent; not a statutory corporate voting system."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Integer, String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, Session
from app.core.db import Base, get_db
from app.core.deps import require_verified
from app.core.errors import conflict, forbidden, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow
from .models import Venture, Distribution
from . import service

router = APIRouter(prefix='/ventures', tags=['cooperation-governance'])


class PayoutProposal(Base):
    __tablename__ = 'payout_proposals'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venture_id: Mapped[int] = mapped_column(Integer, index=True)
    created_by: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(Integer)
    memo: Mapped[str] = mapped_column(String(200))
    member_ids: Mapped[list] = mapped_column(JSON)
    share_snapshot: Mapped[list] = mapped_column(JSON)
    approvals: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default='pending')
    distribution_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ProposalIn(BaseModel):
    amount_cents: int = Field(gt=0, le=1_000_000_000)
    memo: str = Field(default='', max_length=200)


class VoteIn(BaseModel):
    approve: bool


def _lock(db, vid, user):
    if not service.is_member(db, vid, user.id):
        raise forbidden('仅合作体成员可操作分配提案')
    db.query(Venture).filter_by(user_id=vid).update({'status': Venture.status})
    return db.get(Venture, vid)


def _basis(db, vid):
    return (sorted(m.user_id for m in service.members(db, vid)),
            [s for s in service.shares_bps(db, vid) if s['share_bps'] > 0])


def _valid(db, row):
    if row.status != 'pending' or row.expires_at <= utcnow():
        raise conflict('提案已结束或过期，请重新发起')
    ids, shares = _basis(db, row.venture_id)
    if ids != row.member_ids or shares != row.share_snapshot:
        raise conflict('成员或贡献依据已变化，请重新发起分配提案')


def _dump(row):
    return {'id': row.id, 'venture_id': row.venture_id, 'created_by': row.created_by,
            'amount_cents': row.amount_cents, 'memo': row.memo,
            'member_ids': row.member_ids, 'share_snapshot': row.share_snapshot,
            'approvals': row.approvals, 'status': row.status,
            'distribution_id': row.distribution_id, 'expires_at': iso(row.expires_at)}


@router.get('/{venture_id}/payout-proposals')
def proposals(venture_id: int, user: User = Depends(require_verified), db: Session = Depends(get_db)):
    if not service.is_member(db, venture_id, user.id):
        raise forbidden('仅合作体成员可读取分配提案')
    return [_dump(r) for r in db.query(PayoutProposal).filter_by(venture_id=venture_id)
            .order_by(PayoutProposal.id.desc()).limit(100).all()]


@router.post('/{venture_id}/payout-proposals', status_code=201)
def propose(venture_id: int, body: ProposalIn, user: User = Depends(require_verified), db: Session = Depends(get_db)):
    from app.modules.legal.consent import require_current_agreement
    require_current_agreement(db, user.id)
    _lock(db, venture_id, user)
    ids, shares = _basis(db, venture_id)
    if not shares:
        raise conflict('尚无已确认贡献，无法计算分配比例', 'no_shares')
    row = PayoutProposal(venture_id=venture_id, created_by=user.id, amount_cents=body.amount_cents,
        memo=body.memo, member_ids=ids, share_snapshot=shares,
        approvals=[{'user_id': user.id, 'at': iso(utcnow())}], expires_at=utcnow()+timedelta(days=7))
    db.add(row); db.flush()
    service._anchor(db, 'coop.payout.proposed', venture_id, _dump(row))
    from app.modules.notification.service import notify
    for uid in ids:
        if uid != user.id:
            notify(db, uid, 'system', '收益分配待确认', f'合作体 #{venture_id} 提案 #{row.id}：请核对金额、份额和说明后确认；全体成员同意后才能执行。')
    return _dump(row)


@router.post('/{venture_id}/payout-proposals/{proposal_id}/vote')
def vote(venture_id: int, proposal_id: int, body: VoteIn,
         user: User = Depends(require_verified), db: Session = Depends(get_db)):
    from app.modules.legal.consent import require_current_agreement
    require_current_agreement(db, user.id)
    _lock(db, venture_id, user)
    row = db.get(PayoutProposal, proposal_id)
    if not row or row.venture_id != venture_id:
        raise not_found('分配提案不存在')
    _valid(db, row)
    if not body.approve:
        row.status = 'rejected'
    elif user.id not in {a['user_id'] for a in row.approvals}:
        row.approvals = [*row.approvals, {'user_id': user.id, 'at': iso(utcnow())}]
    service._anchor(db, 'coop.payout.vote', venture_id,
                    {'proposal_id': row.id, 'user_id': user.id, 'approve': body.approve})
    return _dump(row)


def execute(db, venture, user, proposal_id, amount_cents, memo):
    from app.modules.legal.consent import require_current_agreement
    require_current_agreement(db, user.id)
    _lock(db, venture.user_id, user)
    row = db.get(PayoutProposal, proposal_id) if proposal_id else None
    if not row or row.venture_id != venture.user_id:
        raise forbidden('必须先发起收益分配提案并取得全体成员确认')
    if row.amount_cents != amount_cents or row.memo != memo:
        raise conflict('执行参数与成员确认的提案不一致')
    if row.status == 'executed':
        return db.get(Distribution, row.distribution_id)
    _valid(db, row)
    if set(row.member_ids) != {a['user_id'] for a in row.approvals}:
        raise forbidden('尚未取得全体成员确认')
    dist = service.distribute(db, venture, user, amount_cents, memo)
    row.status = 'executed'; row.distribution_id = dist.id
    service._anchor(db, 'coop.payout.executed', venture.user_id,
                    {'proposal_id': row.id, 'distribution_id': dist.id, 'approvals': row.approvals})
    return dist
