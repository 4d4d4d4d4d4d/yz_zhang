"""IM（09）：任务会话自动创建、防跳单风控、陌生人频控。"""
import re

from sqlalchemy.exc import IntegrityError
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


def direct_key(user_a: int, user_b: int) -> str:
    """单聊的规范化键：小 id-大 id。

    规范化是关键——`(1,2)` 与 `(2,1)` 必须得到同一个键，否则两个人从各自
    那一侧发起会得到两条会话，而那正是这一批在修的病。
    """
    low, high = sorted((user_a, user_b))
    return f"{low}-{high}"


def get_or_create_direct(db: Session, user_a: int, user_b: int) -> Conversation:
    """IM-052 取单聊会话，没有就建一条。

    改造前这里有两个毛病，都在同一行上：

    1. **check-then-insert 没有任何东西兜底**。`participants` 是 JSON，
       库里建不了唯一约束，于是并发会建出两条会话——两人各说各话、
       消息分在两条线上，而**谁都不会看到错误**。
       探针实测：并发 10 次开同一个单聊，拿到两个会话 id。
       V112 的钱包是同一个形状，但那张表有唯一约束，所以它只是 500；
       **没有约束的地方，竞态不报错，只把数据悄悄弄错**。
    2. **把全平台所有单聊取出来在 Python 里比参与者集合**。
       每开一次私聊扫一遍全表——用户量一上来就是首屏最慢的那个请求。

    现在按 `direct_key` 走唯一索引查，并接住唯一约束冲突（与 V112 的钱包
    同一个写法：`begin_nested()` 让插入失败只回滚这一步，不把外层事务
    一起带走——调用方常常正在做发消息/建任务会话这种多步写入）。
    """
    key = direct_key(user_a, user_b)
    conv = db.query(Conversation).filter(Conversation.direct_key == key).first()
    if conv:
        return conv
    try:
        with db.begin_nested():
            conv = Conversation(kind="direct", participants=[user_a, user_b],
                                direct_key=key)
            db.add(conv)
            db.flush()
        return conv
    except IntegrityError:
        # 别人刚建好了：按键重读。读不到才是真的坏了，那就让它抛。
        conv = db.query(Conversation).filter(Conversation.direct_key == key).first()
        if conv is None:
            raise
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
