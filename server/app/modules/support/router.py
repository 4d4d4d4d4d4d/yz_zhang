"""智能客服（10）MVP：FAQ 检索问答 + 账户上下文 + 低置信度转人工工单。"""
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.modules.account.models import User, utcnow
from app.modules.knowledge import service as kb
from app.core.timefmt import iso

router = APIRouter(prefix="/support", tags=["support"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/ask")
def ask(body: AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
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
    # ESCA-052（172 号 spec）资金 / 账号类加急；不选按一般
    category: str = Field(default="general", max_length=10)
    # ESCA-057（227 号 spec）截图：上传接口返回的 url
    images: list[str] = Field(default_factory=list, max_length=20)


# ESCA-057 一条消息最多附几张图
MAX_TICKET_IMAGES = 4
_FILE_URL = re.compile(r"/files/([A-Za-z0-9_.-]{8,80})$")


def _ticket_images(db: Session, user: User, urls: list[str]) -> list[str]:
    """只收**自己上传过**的图（上传时已过内容审核，被拒的根本不落库）。存图片名，读的时候再拼 url。
    别人的图、不存在的、证件类敏感材料都拒绝——工单附件谁看得到是另一套范围，不能借它把别处的图带进来。"""
    from app.core.errors import bad_request
    from app.modules.files.models import UploadedFile

    if len(urls) > MAX_TICKET_IMAGES:
        raise bad_request(f"一条最多附 {MAX_TICKET_IMAGES} 张图：挑最能说明问题的", "ticket_too_many_images")
    names = []
    for u in urls:
        m = _FILE_URL.search(u or "")
        row = db.get(UploadedFile, m.group(1)) if m else None
        if row is None or row.owner_id != user.id or row.sensitive:
            raise bad_request("只能附你自己刚上传的截图：请重新选择图片上传", "ticket_image_not_yours")
        if row.name not in names:
            names.append(row.name)
    return names


def image_urls(names: list | None) -> list[str]:
    return [f"/api/v1/files/{n}" for n in (names or [])]


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    from .models import Ticket

    from app.core.errors import bad_request

    from .escalation import CATEGORIES, URGENT_CATEGORIES

    if body.category not in CATEGORIES:
        raise bad_request("类别只能是资金（funds）、账号（account）或一般（general）", "ticket_bad_category")
    images = _ticket_images(db, user, body.images)
    ticket = Ticket(user_id=user.id, subject=body.subject, body=body.body, category=body.category,
                    priority="urgent" if body.category in URGENT_CATEGORIES else "normal", images=images)
    db.add(ticket)
    db.flush()
    # `reply` 一开始是空串。共享 SDK 的声明里有它，而这里以前不返回——
    # 「声明了却不给」（V64 那一类）
    return {"id": ticket.id, "status": ticket.status, "reply": ticket.reply, "priority": ticket.priority}


@router.get("/tickets")
def my_tickets(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    from .models import Ticket

    rows = db.query(Ticket).filter(Ticket.user_id == user.id).order_by(Ticket.id.desc()).all()
    return _ticket_rows(db, rows)


# ESCA-056（166 号 spec）提单人追加回复：已结的 7 天内追加就重新打开；更早的请新开一张；转了纠纷的到纠纷里补
REOPEN_DAYS = 7
MAX_USER_REPLIES = 30


class TicketReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    images: list[str] = Field(default_factory=list, max_length=20)   # ESCA-057


# ESCA-059（218 号 spec）只说谢谢、收到、已解决的，不把已结的单重新打开（业界老问题：一句谢谢让客服白跑一趟）。
# 去掉标点、表情和空白后整句都是这些词才算；「谢谢，但还是不行」带了别的内容，照旧重开
_THANKS_WORDS = re.compile(r"(谢谢你?们?|谢了|感谢|多谢|辛苦了?|好的?|好滴|收到了?|明白了?|知道了|嗯+|哦+|ok|okay|thanks?|thank\s*you|"
                           r"已经?解决了?|问题解决了|搞定了?|没问题了?|可以了|行了?)+", re.I)
_NOISE = re.compile(r"[\s\W_]+", re.U)


def thanks_only(text: str) -> bool:
    t = _NOISE.sub("", text or "")
    return bool(t) and len(t) <= 20 and bool(_THANKS_WORDS.fullmatch(t))


@router.post("/tickets/{ticket_id}/replies")
def reply_my_ticket(ticket_id: int, body: TicketReplyIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db, scope="function")):
    from datetime import timedelta

    from app.core.errors import conflict, not_found
    from app.modules.notification.service import notify

    from .models import Ticket, TicketReply

    t = db.get(Ticket, ticket_id)
    if t is None or t.user_id != user.id:
        raise not_found("没有这张工单")
    text = body.body.strip()
    if not text:
        raise conflict("补充的内容是空的", "ticket_reply_empty")
    if t.escalated_to_dispute_id:
        raise conflict(f"这张工单已经转成纠纷（#{t.escalated_to_dispute_id}）：补充材料请到纠纷里提交，仲裁员只看纠纷里的",
                       "ticket_in_dispute")
    images = _ticket_images(db, user, body.images)
    now = utcnow()
    reopened = False
    # 带了截图就不是「只说谢谢」
    kept_closed = t.status == "resolved" and thanks_only(text) and not images
    if t.status == "resolved" and not kept_closed:
        if t.resolved_at is not None and t.resolved_at < now - timedelta(days=REOPEN_DAYS):
            raise conflict(f"这张工单已结超过 {REOPEN_DAYS} 天：请新开一张，写上原工单号 #{t.id}", "ticket_closed_too_long")
        t.status, t.resolved_at, reopened = "open", None, True
    mine = db.query(TicketReply).filter(TicketReply.ticket_id == t.id, TicketReply.is_staff.is_(False)).count()
    if mine >= MAX_USER_REPLIES:
        raise conflict(f"这张工单你已经补充了 {MAX_USER_REPLIES} 次：请等客服回复，或新开一张", "ticket_reply_limit")
    db.add(TicketReply(ticket_id=t.id, author_id=user.id, is_staff=False, body=text, created_at=now, images=images))
    db.add(t)
    if t.assignee_id and not kept_closed:      # 只说谢谢的不打扰客服：记在往来里就够了
        notify(db, t.assignee_id, "system", f"工单 #{t.id} 提单人{'重新打开并' if reopened else ''}补充了内容",
               text[:100])
    db.flush()
    return {**_ticket_rows(db, [t])[0], "reopened": reopened, "kept_closed": kept_closed}


def _ticket_rows(db: Session, rows: list) -> list[dict]:
    from .escalation import sla_view
    from .models import TicketReply

    now = utcnow()
    # ESCA-053（157 号 spec）往来记录：只给回复内容与时间，不给是哪位管理员
    replies: dict[int, list[dict]] = {}
    if rows:
        for r in (db.query(TicketReply).filter(TicketReply.ticket_id.in_([t.id for t in rows]))
                  .order_by(TicketReply.id).all()):
            replies.setdefault(r.ticket_id, []).append(
                {"body": r.body, "is_staff": r.is_staff, "created_at": iso(r.created_at), "images": image_urls(r.images)})
    return [
        # 少了 `body`，用户看到的是一排标题、点进去没有内容——
        # 那不是类型问题，是这个页面缺了东西
        # ESCA-051（150 号）：提单人看得到「有没有人接手」「是否已升级」，看不到接手的是哪位管理员
        {"id": t.id, "subject": t.subject, "body": t.body, "status": t.status,
         "reply": t.reply, "created_at": iso(t.created_at), "claimed": bool(t.assignee_id),
         **sla_view(t, now), "replies": replies.get(t.id, []), "images": image_urls(t.images)}
        for t in rows
    ]
