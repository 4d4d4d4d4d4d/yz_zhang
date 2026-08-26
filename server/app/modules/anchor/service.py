import hashlib
import json

from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import AnchorEntry, AnchorReceipt

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
    # EVT-012 critical：签了字却没有链上记录，等于平台对外承诺的证据能力有洞。
    # retry=False 的理由是时序而非幂等：几小时后补进去的条目，seq 会排在
    # 真实发生更晚的事件之后，链所声称的「按此顺序发生」就变成了假话——
    # 而这条链是要拿去举证的。所以宁可当场失败，也不事后补。
    subscribe("contract.signed", _on_signed, retry=False, critical=True)
    subscribe("contract.funded", _on_funded, retry=False, critical=True)
    subscribe("contract.released", _on_released, retry=False, critical=True)
    subscribe("contract.verdict_executed", _on_verdict, retry=False, critical=True)


# ---------- LAW-010/011 第三方存证锚定 ----------
def notarize_pending(db: Session) -> dict:
    """把尚未被存证覆盖的链区间交给存证机构，取回回执。

    自算哈希链只能自证前后一致；**自己给自己作证采信度有限**，
    所以要定期把 head 交给第三方背书。缺省 `LocalNotary` 不背书，
    回执里会诚实写明这一点（backed=False）。
    """
    from app.vendors.notary import get_notary

    last = db.query(AnchorReceipt).order_by(AnchorReceipt.seq_to.desc()).first()
    covered_to = last.seq_to if last else 0
    head_entry = db.query(AnchorEntry).order_by(AnchorEntry.seq.desc()).first()
    if not head_entry or head_entry.seq <= covered_to:
        return {"notarized": 0, "covered_to": covered_to}

    provider = get_notary()
    receipt = provider.notarize(head_entry.chain_hash, covered_to + 1, head_entry.seq)
    row = AnchorReceipt(
        seq_from=covered_to + 1, seq_to=head_entry.seq, chain_head=head_entry.chain_hash,
        receipt_no=receipt.receipt_no, authority=receipt.authority,
        backed=receipt.backed, detail=receipt.detail,
    )
    db.add(row)
    db.flush()
    return {"notarized": head_entry.seq - covered_to, "covered_to": head_entry.seq,
            "receipt_no": receipt.receipt_no, "backed": receipt.backed}


def coverage(db: Session) -> dict:
    """LAW-013 存证覆盖情况：哪些区间有第三方背书、哪些没有。

    诚实标注证明力边界，好过让人误以为全部有司法效力。
    """
    head_entry = db.query(AnchorEntry).order_by(AnchorEntry.seq.desc()).first()
    total = head_entry.seq if head_entry else 0
    receipts = db.query(AnchorReceipt).order_by(AnchorReceipt.seq_to).all()
    backed_to = max((r.seq_to for r in receipts if r.backed), default=0)
    return {
        "total_entries": total,
        "third_party_backed_to_seq": backed_to,
        "uncovered_entries": max(0, total - backed_to),
        "receipts": [
            {"seq_from": r.seq_from, "seq_to": r.seq_to, "receipt_no": r.receipt_no,
             "authority": r.authority, "backed": r.backed, "detail": r.detail,
             "at": r.created_at.isoformat()}
            for r in receipts
        ],
        "note": (
            "全部存证均有第三方背书。" if backed_to >= total > 0 else
            "标注 backed=false 的区间仅为平台自算哈希链，无第三方背书，"
            "可证明「平台记录未被事后改动」，但司法采信度低于第三方存证。"
        ),
    }
