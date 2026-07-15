"""合约引擎（05）：生成、签署、托管、放款、取消规则、纠纷冻结与分割。

设计对应 SC-001~SC-009；实现为链下规则引擎（阶段一），
接口保持可替换为链上实现（见 05 号 spec 演进路线）。
"""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request, conflict
from app.core.events import publish
from app.modules.account.models import utcnow
from app.modules.wallet import service as wallet

from .models import ChangeOrder, Contract, Milestone

# SC-006 取消/违约规则表：执行者获得托管金的比例（万分比），按阶段与责任方
CANCEL_RULES = {
    # (托管后阶段, 取消发起方) -> 执行者补偿比例 bps
    ("funded_early", "requester"): 2000,  # 托管后发布者取消：补偿执行者 20%
    ("funded_early", "executor"): 0,  # 执行者取消：全额退款（另扣信用分）
}


def generate(db: Session, task, executor_id: int, amount_cents: int) -> Contract:
    """SC-001 成交自动生成合约。"""
    existing = db.query(Contract).filter(Contract.task_id == task.id).first()
    if existing:
        raise conflict("该任务已存在合约", "contract_exists")
    terms = (
        f"任务《{task.title}》(ID:{task.id})\n"
        f"发布方: 用户{task.creator_id} / 执行方: 用户{executor_id}\n"
        f"金额: {amount_cents / 100:.2f} 元(托管) / 平台服务费率: {settings.PLATFORM_FEE_BPS / 100:.1f}%\n"
        f"验收: 交付后由发布方验收，{settings.AUTO_ACCEPT_DAYS} 天未处理视为自动通过\n"
        f"争议: 按《平台争议处理规则》仲裁，裁决结果自动执行"
    )
    # CRED-003 信用等级权益：高信用执行者享费率折扣
    from app.modules.account import service as credit
    from app.modules.account.models import User

    executor = db.get(User, executor_id)
    fee_bps = credit.fee_bps_for(executor) if executor else settings.PLATFORM_FEE_BPS
    contract = Contract(
        task_id=task.id,
        requester_id=task.creator_id,
        executor_id=executor_id,
        amount_cents=amount_cents,
        fee_bps=fee_bps,
        terms=terms,
        deposit_cents=task.deposit_cents or 0,
    )
    db.add(contract)
    db.flush()
    # CRED-005 成交即冻结执行者保证金
    if contract.deposit_cents > 0:
        wallet.freeze_deposit(db, executor_id, contract.deposit_cents, contract.id)
        contract.deposit_status = "held"
        db.add(contract)
    # SC-004 默认单里程碑=全额；双签前可由发布者重新定义分期
    db.add(Milestone(contract_id=contract.id, idx=1, title="全部交付", amount_cents=amount_cents))
    return contract


def define_milestones(db: Session, contract: Contract, user_id: int, items: list[dict]) -> list[Milestone]:
    """SC-004 双签前定义分期结构（金额必须与合约总额守恒）。"""
    if user_id != contract.requester_id:
        raise bad_request("仅发布方可定义里程碑", "not_party")
    if contract.status != "pending_signatures":
        raise conflict("合约签署后不可重定义里程碑，请走变更单", "milestones_locked")
    if not items:
        raise bad_request("里程碑不能为空", "empty_milestones")
    total = sum(i["amount_cents"] for i in items)
    if total != contract.amount_cents:
        raise bad_request(
            f"里程碑合计 {total} 必须等于合约金额 {contract.amount_cents}", "amount_mismatch"
        )
    if any(i["amount_cents"] <= 0 for i in items):
        raise bad_request("每期金额必须为正", "invalid_amount")
    db.query(Milestone).filter(Milestone.contract_id == contract.id).delete()
    rows = [
        Milestone(contract_id=contract.id, idx=i + 1, title=item.get("title", f"第{i + 1}期"),
                  amount_cents=item["amount_cents"])
        for i, item in enumerate(items)
    ]
    db.add_all(rows)
    db.flush()
    return rows


def sign(db: Session, contract: Contract, user_id: int) -> Contract:
    """SC-002 双方电子签署。"""
    if contract.status != "pending_signatures":
        raise conflict("合约当前不可签署", "not_signable")
    if user_id == contract.requester_id:
        contract.signed_by_requester = True
    elif user_id == contract.executor_id:
        contract.signed_by_executor = True
    else:
        raise bad_request("非合约当事人", "not_party")
    if contract.signed_by_requester and contract.signed_by_executor:
        contract.status = "signed"
        publish(db, "contract.signed", {"contract_id": contract.id, "task_id": contract.task_id})
    db.add(contract)
    return contract


def fund(db: Session, contract: Contract, user_id: int) -> Contract:
    """SC-003 发布者注入托管资金，合约生效。"""
    if user_id != contract.requester_id:
        raise bad_request("仅发布方可托管资金", "not_party")
    if contract.status != "signed":
        raise conflict("合约需双方签署后才能托管", "not_fundable")
    wallet.escrow_hold(db, contract.requester_id, contract.amount_cents, contract.id)
    contract.status = "funded"
    contract.funded_at = utcnow()
    db.add(contract)
    publish(db, "contract.funded", {"contract_id": contract.id, "task_id": contract.task_id})
    return contract


def _fee(contract: Contract, amount: int) -> int:
    return amount * contract.fee_bps // 10000


def _settle_deposit(db: Session, contract: Contract, forfeit: bool = False) -> None:
    """保证金结清：正常闭环退还，执行者违约罚没给发布者（CRED-005）。"""
    if contract.deposit_status != "held":
        return
    if forfeit:
        wallet.forfeit_deposit(
            db, contract.executor_id, contract.requester_id, contract.deposit_cents, contract.id
        )
        contract.deposit_status = "forfeited"
    else:
        wallet.unfreeze_deposit(db, contract.executor_id, contract.deposit_cents, contract.id)
        contract.deposit_status = "returned"
    db.add(contract)


def release(db: Session, contract: Contract) -> Contract:
    """SC-005 整体验收放款：放出全部剩余托管（已分期放款的部分不重复）。"""
    if contract.frozen:
        raise conflict("合约处于纠纷冻结中", "contract_frozen")
    if contract.status != "funded":
        raise conflict("合约不在可放款状态", "not_releasable")
    remaining = contract.amount_cents - contract.released_cents
    if remaining > 0:
        wallet.escrow_release(
            db, contract.requester_id, contract.executor_id,
            remaining, _fee(contract, remaining), contract.id,
        )
    db.query(Milestone).filter(
        Milestone.contract_id == contract.id, Milestone.status != "released"
    ).update({"status": "released"})
    contract.released_cents = contract.amount_cents
    contract.status = "released"
    contract.closed_at = utcnow()
    db.add(contract)
    _settle_deposit(db, contract)
    publish(db, "contract.released", {"contract_id": contract.id, "task_id": contract.task_id})
    return contract


def deliver_milestone(db: Session, contract: Contract, user_id: int, milestone: Milestone) -> Milestone:
    """SC-004 分期交付。"""
    if user_id != contract.executor_id:
        raise bad_request("仅执行方可提交里程碑交付", "not_party")
    if contract.status != "funded" or contract.frozen:
        raise conflict("合约不在执行中", "not_active")
    if milestone.status != "pending":
        raise conflict("该里程碑已交付或已放款", "invalid_milestone_state")
    milestone.status = "delivered"
    db.add(milestone)
    return milestone


def release_milestone(db: Session, contract: Contract, user_id: int, milestone: Milestone) -> Milestone:
    """SC-004/005 分期验收放款；全部放完 → 合约终结。"""
    if user_id != contract.requester_id:
        raise bad_request("仅发布方可验收里程碑", "not_party")
    if contract.frozen:
        raise conflict("合约处于纠纷冻结中", "contract_frozen")
    if contract.status != "funded":
        raise conflict("合约不在可放款状态", "not_releasable")
    if milestone.status != "delivered":
        raise conflict("里程碑需先交付", "invalid_milestone_state")
    wallet.escrow_release(
        db, contract.requester_id, contract.executor_id,
        milestone.amount_cents, _fee(contract, milestone.amount_cents), contract.id,
    )
    milestone.status = "released"
    contract.released_cents += milestone.amount_cents
    db.add_all([milestone, contract])
    if contract.released_cents >= contract.amount_cents:
        contract.status = "released"
        contract.closed_at = utcnow()
        db.add(contract)
        _settle_deposit(db, contract)
        publish(db, "contract.released", {"contract_id": contract.id, "task_id": contract.task_id})
    return milestone


def propose_change(db: Session, contract: Contract, user_id: int, new_amount: int, reason: str) -> ChangeOrder:
    """SC-007 变更单：改价提案（放款开始后不可改）。"""
    if user_id not in (contract.requester_id, contract.executor_id):
        raise bad_request("非合约当事人", "not_party")
    if contract.status not in ("signed", "funded") or contract.frozen:
        raise conflict("当前状态不可变更", "not_changeable")
    if contract.released_cents > 0:
        raise conflict("已开始分期放款，不可整体改价", "already_releasing")
    if new_amount <= 0 or new_amount == contract.amount_cents:
        raise bad_request("变更金额无效", "invalid_amount")
    pending = (
        db.query(ChangeOrder)
        .filter(ChangeOrder.contract_id == contract.id, ChangeOrder.status == "pending")
        .first()
    )
    if pending:
        raise conflict("已有待处理的变更单", "change_pending")
    order = ChangeOrder(
        contract_id=contract.id, proposed_by=user_id, new_amount_cents=new_amount, reason=reason
    )
    db.add(order)
    db.flush()
    return order


def accept_change(db: Session, contract: Contract, user_id: int, order: ChangeOrder) -> Contract:
    """对方接受变更单 → 差额多退少补、版本 +1、任务预算同步。"""
    if order.status != "pending":
        raise conflict("变更单已处理", "change_closed")
    if user_id == order.proposed_by or user_id not in (contract.requester_id, contract.executor_id):
        raise bad_request("需由合约对方接受变更", "not_counterparty")
    milestones = db.query(Milestone).filter(Milestone.contract_id == contract.id).all()
    if len(milestones) > 1:
        raise conflict("多里程碑合约请拆期变更（暂不支持整体改价）", "multi_milestone")
    diff = order.new_amount_cents - contract.amount_cents
    if contract.status == "funded":
        if diff > 0:
            wallet.escrow_hold(db, contract.requester_id, diff, contract.id)
        else:
            wallet.escrow_refund(db, contract.requester_id, -diff, contract.id, "变更单减价退款")
    old_amount = contract.amount_cents
    contract.amount_cents = order.new_amount_cents
    contract.version += 1
    # SC-007 变更以附录形式追加到条款，保证导出文书与实际金额一致（不篡改原始条款）
    contract.terms = (
        f"{contract.terms}\n\n── 变更附录 v{contract.version}（{utcnow().date().isoformat()}）──\n"
        f"金额由 {old_amount / 100:.2f} 元变更为 {order.new_amount_cents / 100:.2f} 元"
        f"（提案人 用户{order.proposed_by}）。事由：{order.reason or '（未填写）'}"
    )
    if milestones:
        milestones[0].amount_cents = order.new_amount_cents
        db.add(milestones[0])
    order.status = "accepted"
    db.add_all([contract, order])
    # 任务预算同步（TASK-025 变更单双方确认后合约同步变更）
    from app.modules.task.models import Task

    task = db.get(Task, contract.task_id)
    if task:
        task.budget_cents = order.new_amount_cents
        db.add(task)
    return contract


def cancel(db: Session, contract: Contract, cancelled_by: int) -> dict:
    """SC-006 取消规则引擎：按阶段计算责任并执行退款/补偿。"""
    if contract.frozen:
        raise conflict("合约处于纠纷冻结中", "contract_frozen")
    if contract.status in ("pending_signatures", "signed"):
        contract.status = "cancelled"
        contract.closed_at = utcnow()
        db.add(contract)
        _settle_deposit(db, contract)  # 未托管阶段取消：保证金原路退还
        return {"executor_compensation_cents": 0}
    if contract.status != "funded":
        raise conflict("合约不在可取消状态", "not_cancellable")
    who = "requester" if cancelled_by == contract.requester_id else "executor"
    remaining = contract.amount_cents - contract.released_cents
    comp_bps = CANCEL_RULES.get(("funded_early", who), 0)
    comp = remaining * comp_bps // 10000
    if comp > 0:
        wallet.dispute_split(
            db,
            contract.requester_id,
            contract.executor_id,
            remaining,
            comp,
            _fee(contract, comp),
            contract.id,
        )
        contract.status = "split"
    else:
        wallet.escrow_refund(db, contract.requester_id, remaining, contract.id, "任务取消退款")
        contract.status = "refunded"
    contract.closed_at = utcnow()
    db.add(contract)
    # CRED-005：执行者违约取消 → 罚没保证金；发布者取消 → 退还
    _settle_deposit(db, contract, forfeit=(who == "executor"))
    return {"executor_compensation_cents": comp, "cancelled_by": who}


def freeze(db: Session, contract: Contract) -> None:
    """SC-008/DSP-002 纠纷冻结。"""
    contract.frozen = True
    db.add(contract)


def execute_verdict(db: Session, contract: Contract, executor_share_bps: int) -> dict:
    """DSP-007 裁决自动执行：按比例分割托管资金。"""
    if contract.status != "funded":
        raise conflict("合约不在可执行裁决状态", "not_splittable")
    remaining = contract.amount_cents - contract.released_cents
    share = remaining * executor_share_bps // 10000
    wallet.dispute_split(
        db,
        contract.requester_id,
        contract.executor_id,
        remaining,
        share,
        _fee(contract, share),
        contract.id,
    )
    contract.frozen = False
    contract.status = "split" if 0 < executor_share_bps < 10000 else (
        "released" if executor_share_bps == 10000 else "refunded"
    )
    contract.closed_at = utcnow()
    db.add(contract)
    _settle_deposit(db, contract)  # 仲裁结案：保证金退还（罚没仅适用于违约取消）
    publish(db, "contract.verdict_executed", {"contract_id": contract.id, "task_id": contract.task_id})
    return {"executor_amount_cents": share}
