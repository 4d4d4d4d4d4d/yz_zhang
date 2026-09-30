"""IM（09）：任务会话自动创建、防跳单风控、陌生人频控。"""
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request
from app.core.events import subscribe

from .models import Conversation, Message

# IM-006 站外联系方式/引导模式（RISK-004 防跳单简化版）
RISK_PATTERNS = [
    re.compile(r"1[3-9]\d{9}"),  # 手机号
    re.compile(r"(微信|vx|wx|加我|私下|线下交易|直接转账)", re.IGNORECASE),
]


def is_risky(content: str) -> bool:
    return any(p.search(content) for p in RISK_PATTERNS)


def get_or_create_direct(db: Session, user_a: int, user_b: int) -> Conversation:
    for conv in db.query(Conversation).filter(Conversation.kind == "direct").all():
        if set(conv.participants) == {user_a, user_b}:
            return conv
    conv = Conversation(kind="direct", participants=[user_a, user_b])
    db.add(conv)
    db.flush()
    return conv


def check_stranger_limit(db: Session, conv: Conversation, sender_id: int) -> None:
    """IM-005 陌生人单聊：对方未回复前最多发 N 条（任务会话不受限）。"""
    if conv.kind != "direct":
        return
    msgs = db.query(Message).filter(Message.conversation_id == conv.id).all()
    if any(m.sender_id != sender_id for m in msgs):
        return  # 对方已回复
    if len(msgs) >= settings.STRANGER_MSG_LIMIT:
        raise bad_request("对方回复前最多发送 5 条消息", "stranger_limit")


def send(db: Session, conv: Conversation, sender_id: int, content: str, kind: str = "text") -> Message:
    check_stranger_limit(db, conv, sender_id)
    msg = Message(
        conversation_id=conv.id,
        sender_id=sender_id,
        kind=kind,
        content=content,
        # 结构化卡片消息（IM-009）不做站外引导风控（内容为平台生成）
        risk_flagged=is_risky(content) if kind == "text" else False,
    )
    db.add(msg)
    db.flush()
    return msg


# ---------- 事件：合约资金托管成功 → 自动建任务会话（IM-002/TASK-023） ----------
def _on_contract_funded(db: Session, payload: dict) -> None:
    from app.modules.contract.models import Contract

    contract = db.get(Contract, payload["contract_id"])
    if not contract:
        return
    existing = db.query(Conversation).filter(Conversation.task_id == contract.task_id).first()
    if existing:
        return
    db.add(
        Conversation(
            kind="task",
            task_id=contract.task_id,
            participants=[contract.requester_id, contract.executor_id],
        )
    )


def register_event_handlers() -> None:
    # 已有会话时直接返回，补建晚一点不影响正确性
    subscribe("contract.funded", _on_contract_funded, retry=True)
