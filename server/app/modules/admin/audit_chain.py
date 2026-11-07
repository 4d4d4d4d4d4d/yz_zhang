"""ADMIN-062 审计日志的哈希链（149 号 spec）。

每条审计的哈希 = sha256(上一条的哈希 | 本条的管理员、动作、对象、说明、时间)。链头单独一行，写的时候锁住：
- 改了某一条的内容 → 这一条重算对不上；
- 删了中间某一条 → 下一条的「上一条哈希」对不上；
- 删了最后几条 → 链头记的最新编号 / 哈希对不上；
- 绕过 `record_audit` 直接插一条 → 它没有哈希，夹在链中间会被指出来。
这不是外部存证（数据库管理员可以把链整条重算），所以 V182（156 号 spec）起每天把链头写进平台存证链
（存证链再由公证 job 交给第三方背书）；自检时逐个核对锚点：整条重算过的链，锚定那一刻的哈希对不上。
"""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.core.timefmt import iso
from app.modules.account.models import utcnow

from .models import AdminAudit, AuditChainHead


def digest(prev: str, r: AdminAudit) -> str:
    body = "|".join([prev, str(r.admin_id), r.action or "", r.target_type or "",
                     "" if r.target_id is None else str(r.target_id), r.detail or "", iso(r.created_at) or ""])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _head(db: Session) -> AuditChainHead:
    head = db.query(AuditChainHead).filter(AuditChainHead.id == 1).with_for_update().first()
    if head is None:
        head = AuditChainHead(id=1, last_audit_id=0, last_hash="", count=0)
        db.add(head)
        db.flush()
    return head


def append(db: Session, row: AdminAudit) -> AdminAudit:
    head = _head(db)
    row.created_at = row.created_at or utcnow()
    row.prev_hash = head.last_hash
    row.hash = digest(head.last_hash, row)
    db.add(row)
    db.flush()
    head.last_audit_id, head.last_hash, head.count = row.id, row.hash, head.count + 1
    return row


ANCHOR_EVENT = "admin_audit.head"


def anchor_head(db: Session) -> dict:
    """ADMIN-063 把当前链头写进存证链。链头没变（这期间没有新的审计）就不重复写。"""
    import json

    from app.modules.anchor.models import AnchorEntry
    from app.modules.anchor.service import anchor

    head = db.query(AuditChainHead).filter(AuditChainHead.id == 1).first()
    if head is None or not head.last_hash:
        return {"anchored": False, "reason": "审计链还没有记录"}
    last = (db.query(AnchorEntry).filter(AnchorEntry.event_type == ANCHOR_EVENT)
            .order_by(AnchorEntry.seq.desc()).first())
    if last is not None and json.loads(last.payload).get("head_hash") == head.last_hash:
        return {"anchored": False, "reason": "链头没有变化", "seq": last.seq}
    entry = anchor(db, ANCHOR_EVENT, "audit_chain", head.last_audit_id,
                   {"head_audit_id": head.last_audit_id, "head_hash": head.last_hash, "count": head.count,
                    "at": iso(utcnow())})
    return {"anchored": True, "seq": entry.seq, "head_audit_id": head.last_audit_id, "head_hash": head.last_hash}


def _anchors(db: Session) -> list[dict]:
    import json

    from app.modules.anchor.models import AnchorEntry

    rows = (db.query(AnchorEntry).filter(AnchorEntry.event_type == ANCHOR_EVENT).order_by(AnchorEntry.seq).all())
    return [{**json.loads(r.payload), "seq": r.seq} for r in rows]


def verify(db: Session, limit: int = 200_000) -> dict:
    """从链上第一条走到链头。返回是否完整、走了多少条、第一处断点（编号与原因）。"""
    head = db.query(AuditChainHead).filter(AuditChainHead.id == 1).first()
    rows = db.query(AdminAudit).order_by(AdminAudit.id).limit(limit).all()
    started, prev, checked, problems, legacy = False, "", 0, [], 0
    last_id, last_hash = 0, ""
    for r in rows:
        if not r.hash:
            if started:
                problems.append({"audit_id": r.id, "reason": "没有哈希：不是经由审计接口写入的（绕过了留痕）"})
            else:
                legacy += 1   # 链开始之前的旧记录不在链上
            continue
        started = True
        if r.prev_hash != prev:
            problems.append({"audit_id": r.id, "reason": "上一条的哈希对不上：前面有记录被删或被替换"})
        if digest(r.prev_hash, r) != r.hash:
            problems.append({"audit_id": r.id, "reason": "内容与哈希对不上：这一条被改过"})
        prev, last_id, last_hash = r.hash, r.id, r.hash
        checked += 1
    if head is not None and (head.last_audit_id != last_id or head.last_hash != last_hash):
        problems.append({"audit_id": head.last_audit_id, "reason": "链头记的最新一条与实际不符：最后几条被删了"})
    # ADMIN-063 存证锚点：锚定那一刻的那一条，现在的哈希必须还是当时的哈希
    hashes = {r.id: r.hash for r in rows if r.hash}
    anchors = _anchors(db)
    for a in anchors:
        now_hash = hashes.get(a["head_audit_id"])
        if now_hash is None:
            problems.append({"audit_id": a["head_audit_id"],
                             "reason": f"存证链上锚定过的这一条（{a.get('at', '')}）已经不在了"})
        elif now_hash != a["head_hash"]:
            problems.append({"audit_id": a["head_audit_id"],
                             "reason": f"与存证链上 {a.get('at', '')} 锚定的哈希对不上：链被整体重算过"})
    last_anchor = anchors[-1] if anchors else None
    return {"ok": not problems, "checked": checked, "head_hash": head.last_hash if head else "",
            "head_audit_id": head.last_audit_id if head else 0, "legacy_unchained": legacy,
            "problems": problems[:20], "anchors_checked": len(anchors),
            "last_anchor_audit_id": last_anchor["head_audit_id"] if last_anchor else None,
            "last_anchored_at": last_anchor.get("at") if last_anchor else None}
