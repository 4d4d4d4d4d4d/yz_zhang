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
                "account_context": context, "escalate_to_human": False}
    # CS-006 无把握不编造 → 转人工
    return {"answer": "这个问题我还不确定，已为你转接人工客服。",
            "source": None, "account_context": context, "escalate_to_human": True}
