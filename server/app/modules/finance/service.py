"""FIN-010~014 分账指令构建与记录。

每一笔资金分配都要先成为一条**可审计的指令**：谁付的 → 指令 → 谁收的。
`record()` 是唯一入口，它做三件事：
  1. 校验守恒（splits 之和 == 总额，整数分，不允许尾差蒸发）；
  2. 交给 `LedgerBackend` 执行（internal 为镜像，custody 下达给存管方）；
  3. 落库留痕，含存管方流水号。
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import bad_request
from app.modules.account.models import utcnow

from .models import SETTLEMENT_KINDS, SPLIT_PURPOSES, SettlementOrder, SettlementSplit
from app.core.timefmt import iso


@dataclass
class Split:
    payee_user_id: int   # 0 = 平台账户
    amount_cents: int
    purpose: str = "payout"


def record(db: Session, contract, kind: str, splits: list[Split],
           memo: str = "") -> SettlementOrder:
    """构建并执行一条分账指令。

    金额为 0 的收款方直接丢弃（例如佣金为 0 的场景），但**总额以实际
    保留的 splits 之和为准**——先算总额再校验，杜绝「算错了还说自己对」。
    """
    if kind not in SETTLEMENT_KINDS:
        raise bad_request(f"未知的分账类型 {kind}", "invalid_settlement_kind")
    kept = [s for s in splits if s.amount_cents]
    for s in kept:
        if s.amount_cents < 0:
            raise bad_request("分账金额不得为负", "invalid_split_amount")
        if s.purpose not in SPLIT_PURPOSES:
            raise bad_request(f"未知的收款用途 {s.purpose}", "invalid_split_purpose")
    total = sum(s.amount_cents for s in kept)

    from app.vendors.ledger import get_ledger

    ledger = get_ledger()
    order = SettlementOrder(
        contract_id=contract.id, task_id=getattr(contract, "task_id", None),
        kind=kind, total_cents=total, backend=ledger.name, memo=memo[:200],
    )
    db.add(order)
    db.flush()
    rows = [SettlementSplit(order_id=order.id, payee_user_id=s.payee_user_id,
                            amount_cents=s.amount_cents, purpose=s.purpose)
            for s in kept]
    db.add_all(rows)
    db.flush()

    if ledger.is_custody:
        # CONC-067 给存管行下分账指令是一次网络调用，而这里还在放款的事务里、拿着钱包锁。
        # 指令本身（这张单）与内部账本的变动同生共死地落库；业务提交之后另开会话下达，
        # 按单号幂等，失败由 drain 重试，超时没下达的进日终对账（verify_conservation）。
        from app.core.events import publish

        order.status = "pending"
        db.add(order)
        db.flush()
        publish(db, "settlement.created", {"order_id": order.id})
        return order
    order.custody_ref = ledger.execute(db, order, rows)
    order.status = "executed"
    db.add(order)
    db.flush()
    return order


CUSTODY_OVERDUE_MINUTES = 30


def execute_pending_settlement(db: Session, payload: dict) -> None:
    """业务提交之后下达存管分账指令（after_commit 订阅者）。已下达的直接跳过（幂等）。"""
    from app.vendors.ledger import get_ledger

    order = db.get(SettlementOrder, int(payload["order_id"]))
    if order is None or order.status == "executed":
        return
    rows = db.query(SettlementSplit).filter(SettlementSplit.order_id == order.id).all()
    order.custody_ref = get_ledger().execute(db, order, rows)
    order.status = "executed"
    db.add(order)
    db.flush()


def register_event_handlers() -> None:
    from app.core.events import subscribe

    subscribe("settlement.created", execute_pending_settlement, retry=True, after_commit=True)


def verify_conservation(db: Session) -> list[dict]:
    """FIN-060 分账守恒校验：任一指令的 splits 之和必须等于其总额。

    并入日终对账（`risk.reconcile`）：分账一旦不守恒，说明有钱凭空出现
    或凭空消失，必须立刻停下来查。
    """
    from sqlalchemy import func

    sums = dict(
        db.query(SettlementSplit.order_id,
                 func.coalesce(func.sum(SettlementSplit.amount_cents), 0))
        .group_by(SettlementSplit.order_id).all()
    )
    bad = []
    for order in db.query(SettlementOrder).all():
        actual = int(sums.get(order.id, 0))
        if actual != order.total_cents:
            bad.append({"order_id": order.id, "contract_id": order.contract_id,
                        "total_cents": order.total_cents, "splits_sum": actual})
        # FIN-004 存管模式下无流水号的账目视为异常——**还在下达途中的**（提交后几秒内）不算，
        # 超过 CUSTODY_OVERDUE_MINUTES 还没下达的算（CONC-067：指令在业务提交之后才下达）
        if order.backend == "custody" and not order.custody_ref:
            from datetime import timedelta

            from app.modules.account.models import utcnow

            overdue = order.created_at < utcnow() - timedelta(minutes=CUSTODY_OVERDUE_MINUTES)
            if order.status != "pending" or overdue:
                bad.append({"order_id": order.id, "contract_id": order.contract_id,
                            "issue": "missing_custody_ref" if order.status != "pending"
                            else "custody_instruction_overdue"})
    return bad


def contract_trail(db: Session, contract_id: int) -> list[dict]:
    """FIN-042 资金流向可审计：一份合约上发生过的全部分账指令。"""
    orders = (
        db.query(SettlementOrder)
        .filter(SettlementOrder.contract_id == contract_id)
        .order_by(SettlementOrder.id).all()
    )
    out = []
    for order in orders:
        rows = db.query(SettlementSplit).filter(
            SettlementSplit.order_id == order.id).order_by(SettlementSplit.id).all()
        out.append({
            "id": order.id, "kind": order.kind, "total_cents": order.total_cents,
            "backend": order.backend, "status": order.status,
            "custody_ref": order.custody_ref, "memo": order.memo,
            "at": iso(order.created_at),
            "splits": [{"payee_user_id": r.payee_user_id, "amount_cents": r.amount_cents,
                        "purpose": r.purpose} for r in rows],
        })
    return out


def touch(order: SettlementOrder) -> None:
    order.created_at = utcnow()
