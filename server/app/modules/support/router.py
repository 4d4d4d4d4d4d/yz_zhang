"""智能客服（10）MVP：FAQ 检索问答 + 账户上下文 + 低置信度转人工工单。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.modules.account.models import User
from app.modules.knowledge import service as kb

router = APIRouter(prefix="/support", tags=["support"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/ask")
def ask(body: AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """CS-002 RAG 问答的 MVP：FAQ 关键词检索；CS-003 资金类问题带账户上下文。"""
    hit = kb.search_faq(db, body.question)
    context = None
    if any(kw in body.question for kw in ("余额", "钱", "到账", "提现")):
        from app.modules.wallet import service as wallet

        acct = wallet.get_or_create(db, user.id)
        context = {
            "available_cents": acct.available_cents,
            "escrow_cents": acct.escrow_cents,
        }
    if hit:
        return {"answer": hit["answer"], "source": hit["source"],
                "account_context": context, "escalate_to_human": False, "ticket_id": None}
    # CS-006 无把握不编造 → 转人工并自动建工单（CS-013）
    from .models import Ticket

    ticket = Ticket(user_id=user.id, subject=body.question[:120], body=body.question)
    db.add(ticket)
    db.flush()
    return {"answer": "这个问题我还不确定，已为你转接人工客服并生成工单。",
            "source": None, "account_context": context, "escalate_to_human": True,
            "ticket_id": ticket.id}


# ---------- 工单（CS-013） ----------
class TicketIn(BaseModel):
    subject: str = Field(min_length=2, max_length=120)
    body: str = Field(default="", max_length=2000)


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Ticket

    ticket = Ticket(user_id=user.id, subject=body.subject, body=body.body)
    db.add(ticket)
    db.flush()
    return {"id": ticket.id, "status": ticket.status}


@router.get("/tickets")
def my_tickets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Ticket

    rows = db.query(Ticket).filter(Ticket.user_id == user.id).order_by(Ticket.id.desc()).all()
    return [
        {"id": t.id, "subject": t.subject, "status": t.status, "reply": t.reply,
         "created_at": t.created_at.isoformat()}
        for t in rows
    ]
