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

from .models import Contract

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
    contract = Contract(
        task_id=task.id,
        requester_id=task.creator_id,
        executor_id=executor_id,
        amount_cents=amount_cents,
        fee_bps=settings.PLATFORM_FEE_BPS,
        terms=terms,
    )
    db.add(contract)
    db.flush()
    return contract


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


def release(db: Session, contract: Contract) -> Contract:
    """SC-005 验收通过自动放款。"""
    if contract.frozen:
        raise conflict("合约处于纠纷冻结中", "contract_frozen")
    if contract.status != "funded":
        raise conflict("合约不在可放款状态", "not_releasable")
    wallet.escrow_release(
        db,
        contract.requester_id,
        contract.executor_id,
        contract.amount_cents,
        _fee(contract, contract.amount_cents),
        contract.id,
    )
    contract.status = "released"
    contract.closed_at = utcnow()
    db.add(contract)
    publish(db, "contract.released", {"contract_id": contract.id, "task_id": contract.task_id})
    return contract


def cancel(db: Session, contract: Contract, cancelled_by: int) -> dict:
    """SC-006 取消规则引擎：按阶段计算责任并执行退款/补偿。"""
    if contract.frozen:
        raise conflict("合约处于纠纷冻结中", "contract_frozen")
    if contract.status in ("pending_signatures", "signed"):
        contract.status = "cancelled"
        contract.closed_at = utcnow()
        db.add(contract)
        return {"executor_compensation_cents": 0}
    if contract.status != "funded":
        raise conflict("合约不在可取消状态", "not_cancellable")
    who = "requester" if cancelled_by == contract.requester_id else "executor"
    comp_bps = CANCEL_RULES.get(("funded_early", who), 0)
    comp = contract.amount_cents * comp_bps // 10000
    if comp > 0:
        wallet.dispute_split(
            db,
            contract.requester_id,
            contract.executor_id,
            contract.amount_cents,
            comp,
            _fee(contract, comp),
            contract.id,
        )
        contract.status = "split"
    else:
        wallet.escrow_refund(db, contract.requester_id, contract.amount_cents, contract.id, "任务取消退款")
        contract.status = "refunded"
    contract.closed_at = utcnow()
    db.add(contract)
    return {"executor_compensation_cents": comp, "cancelled_by": who}


def freeze(db: Session, contract: Contract) -> None:
    """SC-008/DSP-002 纠纷冻结。"""
    contract.frozen = True
    db.add(contract)


def execute_verdict(db: Session, contract: Contract, executor_share_bps: int) -> dict:
    """DSP-007 裁决自动执行：按比例分割托管资金。"""
    if contract.status != "funded":
        raise conflict("合约不在可执行裁决状态", "not_splittable")
    share = contract.amount_cents * executor_share_bps // 10000
    wallet.dispute_split(
        db,
        contract.requester_id,
        contract.executor_id,
        contract.amount_cents,
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
    publish(db, "contract.verdict_executed", {"contract_id": contract.id, "task_id": contract.task_id})
    return {"executor_amount_cents": share}
