import hashlib
import json

from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import AnchorEntry

GENESIS = "0" * 64


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def anchor(db: Session, event_type: str, ref_type: str, ref_id: int, payload: dict) -> AnchorEntry:
    """追加一条存证记录（append-only）。"""
    last = db.query(AnchorEntry).order_by(AnchorEntry.seq.desc()).first()
    prev = last.chain_hash if last else GENESIS
    seq = (last.seq + 1) if last else 1
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload_hash = _sha(payload_text)
    entry = AnchorEntry(
        seq=seq, event_type=event_type, ref_type=ref_type, ref_id=ref_id,
        payload=payload_text, payload_hash=payload_hash,
        prev_chain_hash=prev, chain_hash=_sha(prev + payload_hash),
    )
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session) -> dict:
    """全链完整性校验：重算每条链哈希，返回首个被篡改位置。"""
    rows = db.query(AnchorEntry).order_by(AnchorEntry.seq).all()
    prev = GENESIS
    for row in rows:
        if row.prev_chain_hash != prev or _sha(row.payload) != row.payload_hash:
            return {"valid": False, "broken_at_seq": row.seq, "total": len(rows)}
        expected = _sha(prev + row.payload_hash)
        if row.chain_hash != expected:
            return {"valid": False, "broken_at_seq": row.seq, "total": len(rows)}
        prev = row.chain_hash
    return {"valid": True, "total": len(rows), "head": prev if rows else GENESIS}


# ---------- 事件订阅：合约关键动作自动入链 ----------
def _snapshot(db: Session, contract_id: int) -> dict | None:
    from app.modules.contract.models import Contract

    c = db.get(Contract, contract_id)
    if not c:
        return None
    return {
        "contract_id": c.id, "task_id": c.task_id, "version": c.version,
        "requester_id": c.requester_id, "executor_id": c.executor_id,
        "amount_cents": c.amount_cents, "released_cents": c.released_cents,
        "status": c.status, "terms_hash": _sha(c.terms),
    }


def _anchor_contract_event(event_type: str, db: Session, payload: dict) -> None:
    snap = _snapshot(db, payload["contract_id"])
    if snap:
        anchor(db, event_type, "contract", snap["contract_id"], snap)


# 模块级具名 handler（事件总线按对象去重，闭包会导致重复注册）
def _on_signed(db, payload):
    _anchor_contract_event("contract.signed", db, payload)


def _on_funded(db, payload):
    _anchor_contract_event("contract.funded", db, payload)


def _on_released(db, payload):
    _anchor_contract_event("contract.released", db, payload)


def _on_verdict(db, payload):
    _anchor_contract_event("contract.verdict_executed", db, payload)


def register_event_handlers() -> None:
    subscribe("contract.signed", _on_signed)
    subscribe("contract.funded", _on_funded)
    subscribe("contract.released", _on_released)
    subscribe("contract.verdict_executed", _on_verdict)
