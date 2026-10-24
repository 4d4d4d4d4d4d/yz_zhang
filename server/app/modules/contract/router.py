from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.locks import job_slot
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User
from app.modules.task.models import Task
from app.modules.task.service import transition

from pydantic import BaseModel, ConfigDict, Field

from . import service
from .models import ChangeOrder, Contract, Milestone
from app.core.timefmt import UtcDatetime, iso

router = APIRouter(prefix="/contracts", tags=["contract"])


class MilestonesIn(BaseModel):
    items: list[dict]  # [{title, amount_cents}]


class ChangeIn(BaseModel):
    # SC-007b 三样可以单独改、也可以一起改；只传 new_amount_cents 的老调用方式不变
    new_amount_cents: int | None = Field(default=None, gt=0)
    reason: str = Field(default="", max_length=500)
    new_deadline: UtcDatetime | None = None
    scope_change: str = Field(default="", max_length=1000)


def _get(db: Session, contract_id: int, user: User) -> Contract:
    contract = db.get(Contract, contract_id)
    if not contract:
        raise not_found("合约不存在")
    if user.id not in (contract.requester_id, contract.executor_id) and not user.is_admin:
        raise forbidden()
    return contract


def _dump(c: Contract, db: Session | None = None) -> dict:
    out = {
        "id": c.id,
        "task_id": c.task_id,
        "requester_id": c.requester_id,
        "executor_id": c.executor_id,
        "amount_cents": c.amount_cents,
        "released_cents": c.released_cents,
        "fee_bps": c.fee_bps,
        "terms": c.terms,
        "status": c.status,
        "signed_by_requester": c.signed_by_requester,
        "signed_by_executor": c.signed_by_executor,
        "frozen": c.frozen,
        "version": c.version,
        "deposit_cents": c.deposit_cents,
        "deposit_status": c.deposit_status,
    }
    if db is not None:
        rows = (
            db.query(Milestone).filter(Milestone.contract_id == c.id).order_by(Milestone.idx).all()
        )
        out["milestones"] = [
            {"idx": m.idx, "title": m.title, "amount_cents": m.amount_cents, "status": m.status,
             # SC-015（296 号 spec）一次交付多期时写的说明；没写的期不出这个字段（与以前一样）
             **({"delivery_note": m.delivery_note} if m.delivery_note else {})}
            for m in rows
        ]
    return out


@router.post("/jobs/expire-unsigned")
def run_expire_unsigned(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
        __=Depends(job_slot("expire_unsigned"), scope="function")):
    """SC-012 签署有效期 job：成交后超期未双签的合约自动作废。

    业界惯例（offer 有效期）：避免一方失联导致任务永久卡在 matched、
    执行者保证金被无限期冻结。作废 = 合约取消 + 保证金原路退还 + 任务关闭，
    并通知双方（任务需重新发布招募，因一任务一合约约束不可原单复用）。
    """
    from datetime import timedelta

    from app.core.config import settings
    from app.modules.account.models import utcnow
    from app.modules.notification.service import notify

    cutoff = utcnow() - timedelta(days=settings.SIGN_EXPIRE_DAYS)
    rows = (
        db.query(Contract)
        .filter(Contract.status == "pending_signatures", Contract.created_at <= cutoff)
        .all()
    )
    for contract in rows:
        service.cancel(db, contract, contract.requester_id)  # 未托管阶段：仅取消+退保证金
        task = db.get(Task, contract.task_id)
        if task and task.status not in ("completed", "cancelled"):
            transition(db, task, "cancelled", {"cancelled_by": "system_sign_expired"})
        for uid in (contract.requester_id, contract.executor_id):
            notify(db, uid, "contract", "合约签署超期作废",
                   f"合约 #{contract.id} 超过 {settings.SIGN_EXPIRE_DAYS} 天未完成双方签署，"
                   "已自动作废；保证金（如有）已原路退还，任务可重新发布。")
    return {"expired": len(rows)}


@router.get("/by-task/{task_id}")
def get_contract_by_task(
    task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    contract = db.query(Contract).filter(Contract.task_id == task_id).first()
    if not contract:
        raise not_found("该任务暂无合约")
    if user.id not in (contract.requester_id, contract.executor_id) and not user.is_admin:
        raise forbidden()
    return _dump(contract, db)


@router.get("/{contract_id}")
def get_contract(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    return _dump(_get(db, contract_id, user), db)


@router.get("/{contract_id}/export")
def export_contract(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    """SC-010 合约文本与结算凭证导出（当事人；含全部资金流水与存证哈希）。"""
    from app.modules.anchor.models import AnchorEntry
    from app.modules.wallet.models import LedgerEntry

    from app.core.timefmt import EXPORT_TZ_LABEL, export_time

    contract = _get(db, contract_id, user)
    milestones = (
        db.query(Milestone).filter(Milestone.contract_id == contract.id).order_by(Milestone.idx).all()
    )
    ledger = (
        db.query(LedgerEntry).filter(LedgerEntry.contract_id == contract.id)
        .order_by(LedgerEntry.id).all()
    )
    anchors = (
        db.query(AnchorEntry)
        .filter(AnchorEntry.ref_type == "contract", AnchorEntry.ref_id == contract.id)
        .order_by(AnchorEntry.seq).all()
    )
    lines = [
        "══════ 服务合约 ══════",
        contract.terms,
        f"合约版本: v{contract.version} / 状态: {contract.status}",
        "",
        "── 里程碑 ──",
        *[f"{m.idx}. {m.title}  {m.amount_cents / 100:.2f} 元  [{m.status}]" for m in milestones],
        "",
        # TZ-069（144 号 spec）：这是给人看、交给律师的文本——时间换成北京时间并写明，不留一个裸的 UTC
        f"── 结算凭证（资金流水；时间为{EXPORT_TZ_LABEL}） ──",
        *[f"{export_time(e.created_at)}  {e.kind}  {e.amount_cents / 100:+.2f} 元  {e.memo}"
          for e in ledger],
    ]
    if anchors:
        lines += ["", "── 存证记录（SHA256 链） ──",
                  *[f"#{a.seq} {a.event_type} {a.chain_hash[:16]}…" for a in anchors]]
    return {
        "contract_id": contract.id,
        "text": "\n".join(lines),
        "ledger_count": len(ledger),
        "anchor_head": anchors[-1].chain_hash if anchors else None,
    }


# ---------- SC-004 里程碑 ----------
def _milestone(db: Session, contract: Contract, idx: int) -> Milestone:
    m = (
        db.query(Milestone)
        .filter(Milestone.contract_id == contract.id, Milestone.idx == idx)
        .first()
    )
    if not m:
        raise not_found("里程碑不存在")
    return m


@router.post("/{contract_id}/milestones")
def define_milestones(
    contract_id: int, body: MilestonesIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    contract = _get(db, contract_id, user)
    service.define_milestones(db, contract, user.id, body.items)
    return _dump(contract, db)


@router.post("/{contract_id}/milestones/{idx}/deliver")
def deliver_milestone(
    contract_id: int, idx: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    contract = _get(db, contract_id, user)
    service.deliver_milestone(db, contract, user.id, _milestone(db, contract, idx))
    return _dump(contract, db)


class BatchDeliverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idxs: list[int] = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=500)


@router.post("/{contract_id}/milestones/deliver-batch")
def deliver_milestones(
    contract_id: int, body: BatchDeliverIn, user: User = Depends(get_current_user),
    db: Session = Depends(get_db, scope="function"),
):
    """SC-015（296 号 spec）执行方一次交付多期（连着做完的几期不用点好几次）。"""
    contract = _get(db, contract_id, user)
    service.deliver_milestones(db, contract, user.id, body.idxs, body.note)
    return _dump(contract, db)


# ---------- SCN-166（297 号 spec）交付文件托管：放款完毕前原图锁着 ----------
DELIVERABLES_MAX = 50


class DeliverableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str = Field(min_length=8, max_length=80)
    kind: str = Field(pattern="^(preview|original)$")
    # SC-017（304 号 spec）可选：挂到第几期。不写 = 整份合约（与 V324 一样）
    milestone_idx: int | None = Field(default=None, ge=1, le=100)


def _party(db: Session, contract_id: int, user: User) -> Contract:
    contract = db.get(Contract, contract_id)
    if not contract:
        raise not_found("合约不存在")
    if user.id not in (contract.requester_id, contract.executor_id):
        raise forbidden("交付文件只对合约双方开放")
    return contract


def _released_idxs(db: Session, c: Contract) -> set[int]:
    return {i for (i,) in db.query(Milestone.idx).filter(Milestone.contract_id == c.id,
                                                          Milestone.status == "released")}


def _original_unlocked(c: Contract, d, viewer_id: int, released: set[int]) -> bool:
    """执行方随时能取；发布方要等合约放款完毕，或者（SC-017）这份文件挂的那一期已经放款。"""
    return (viewer_id == c.executor_id or c.status == "released"
            or (d.milestone_idx is not None and d.milestone_idx in released))


def _deliverable_row(c: Contract, d, viewer_id: int, released: set[int] = frozenset()) -> dict:
    unlocked = d.kind == "preview" or _original_unlocked(c, d, viewer_id, released)
    row = {"id": d.id, "kind": d.kind, "created_at": iso(d.created_at), "locked": not unlocked,
           "url": (f"/api/v1/files/{d.file_name}" if d.kind == "preview"
                   else f"/api/v1/contracts/{c.id}/deliverables/{d.id}/file") if unlocked else None}
    if d.milestone_idx is not None:
        row["milestone_idx"] = d.milestone_idx
    return row


@router.post("/{contract_id}/deliverables", status_code=201)
def add_deliverable(contract_id: int, body: DeliverableIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db, scope="function")):
    """执行方把已上传的图片挂到合约上：预览图发布方马上能看；原图放款完毕前锁着（匿名链接也随之失效）。"""
    from app.modules.files.models import UploadedFile

    from .models import ContractDeliverable

    contract = _party(db, contract_id, user)
    if user.id != contract.executor_id:
        raise forbidden("只有执行方能上传交付文件", "not_party")
    if contract.status != "funded" or contract.frozen:
        raise conflict("合约不在执行中：交付文件要在托管期间上传", "not_active")
    f = db.get(UploadedFile, body.ref)
    if f is None or f.owner_id != user.id:
        raise bad_request("没有找到你上传的这张图：先上传，再挂到合约上", "deliverable_file_not_found")
    if db.query(ContractDeliverable).filter(ContractDeliverable.contract_id == contract.id).count() >= DELIVERABLES_MAX:
        raise bad_request(f"一份合约最多挂 {DELIVERABLES_MAX} 个交付文件", "deliverables_full")
    if body.milestone_idx is not None:
        m = (db.query(Milestone).filter(Milestone.contract_id == contract.id, Milestone.idx == body.milestone_idx)
             .first())
        if m is None:
            raise bad_request(f"这份合约没有第 {body.milestone_idx} 期：刷新一下再选", "milestone_not_found")
        if m.status == "released":
            raise conflict(f"第 {m.idx} 期已经放款了，不能再往上挂文件：挂到还没放款的那一期", "invalid_milestone_state")
    if body.kind == "original":
        f.sensitive = True        # 原图不再走匿名能力链接（CERT-010 的同一道门）
        db.add(f)
    d = ContractDeliverable(contract_id=contract.id, file_name=f.name, kind=body.kind,
                            milestone_idx=body.milestone_idx)
    db.add(d)
    db.flush()
    return _deliverable_row(contract, d, user.id)


@router.get("/{contract_id}/deliverables")
def list_deliverables(contract_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db, scope="function")):
    from .models import ContractDeliverable

    contract = _party(db, contract_id, user)
    rows = (db.query(ContractDeliverable).filter(ContractDeliverable.contract_id == contract.id)
            .order_by(ContractDeliverable.id).all())
    released = _released_idxs(db, contract)
    return [_deliverable_row(contract, d, user.id, released) for d in rows]


@router.get("/{contract_id}/deliverables/{deliverable_id}/file")
def read_deliverable(contract_id: int, deliverable_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db, scope="function")):
    """执行方随时能取；发布方要等合约放款完毕（released）。"""
    from fastapi import Response

    from app.vendors import base as vendor_base
    from app.vendors.registry import get_provider

    from .models import ContractDeliverable

    contract = _party(db, contract_id, user)
    d = db.get(ContractDeliverable, deliverable_id)
    if d is None or d.contract_id != contract.id:
        raise not_found("没有这个交付文件")
    if d.kind == "original" and not _original_unlocked(contract, d, user.id, _released_idxs(db, contract)):
        raise forbidden("原图在验收放款后才能下载：先看预览图，验收没问题就放款", "deliverable_locked")
    name = d.file_name
    vendor_base.release(db)  # CONC-067 读存储前放掉连接
    got = getattr(get_provider("storage"), "read", lambda _n: None)(name)
    if not got:
        raise not_found("文件不存在")
    data, content_type = got
    return Response(content=data, media_type=content_type, headers={
        "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'inline; filename="{name}"', "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.post("/{contract_id}/milestones/{idx}/accept")
def accept_milestone(
    contract_id: int, idx: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    contract = _get(db, contract_id, user)
    service.release_milestone(db, contract, user.id, _milestone(db, contract, idx))
    _close_task_if_released(db, contract)
    return _dump(contract, db)


class BatchReleaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idxs: list[int] = Field(min_length=1, max_length=50)
    expected_total_cents: int = Field(ge=1)


@router.post("/{contract_id}/milestones/release-delivered")
def release_delivered(
    contract_id: int, body: BatchReleaseIn, user: User = Depends(get_current_user),
    db: Session = Depends(get_db, scope="function"), idempotency_key: str = Header(default=""),
):
    """SC-014 只放已交付的那几期（146 号 spec）：一次放掉点名的已交付期，不动没交付的。

    SC-016（225 号 spec）带 `Idempotency-Key` 时走通用幂等（104 号）：网络断了用同一个键重试，
    回放第一次的结果，而不是收到一句「这几期不是待验收」——那句话会让人以为钱没放出去。
    不带键照旧（已经在用的旧版 App 不带）：放过的期状态已变，第二次请求仍会被拒，钱不会放两次。"""
    from app.core.idempotency import replay_or_run

    contract = _get(db, contract_id, user)

    def run():
        service.release_delivered(db, contract, user.id, body.idxs, body.expected_total_cents)
        _close_task_if_released(db, contract)
        return _dump(contract, db)

    return replay_or_run(db, user.id, idempotency_key, "contract.release_delivered", run,
                         {"contract_id": contract_id, "idxs": sorted(body.idxs),
                          "expected_total_cents": body.expected_total_cents})


def _close_task_if_released(db: Session, contract) -> None:
    # 末期放款 → 任务闭环（状态机按白名单两步走）
    if contract.status == "released":
        from app.modules.account import service as credit

        task = db.get(Task, contract.task_id)
        if task and task.status != "completed":
            if task.status == "in_progress":
                transition(db, task, "pending_acceptance")
            if task.status == "pending_acceptance":
                from app.modules.account.models import utcnow

                task.completed_at = utcnow()
                transition(db, task, "completed")
                if task.executor_id:
                    credit.record_task_completed(db, task.executor_id)


# ---------- SC-007 变更单 ----------
@router.post("/{contract_id}/change-orders", status_code=201)
def propose_change(
    contract_id: int, body: ChangeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    contract = _get(db, contract_id, user)
    order = service.propose_change(db, contract, user.id, body.new_amount_cents, body.reason,
                                   new_deadline=body.new_deadline, scope_change=body.scope_change.strip())
    return {"id": order.id, "status": order.status, "new_amount_cents": order.new_amount_cents,
            "new_deadline": iso(order.new_deadline), "scope_change": order.scope_change}


@router.post("/{contract_id}/change-orders/{order_id}/accept")
def accept_change(
    contract_id: int, order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    contract = _get(db, contract_id, user)
    order = db.get(ChangeOrder, order_id)
    if not order or order.contract_id != contract.id:
        raise not_found("变更单不存在")
    service.accept_change(db, contract, user.id, order)
    return _dump(contract, db)


@router.post("/{contract_id}/change-orders/{order_id}/reject")
def reject_change(
    contract_id: int, order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    contract = _get(db, contract_id, user)
    order = db.get(ChangeOrder, order_id)
    if not order or order.contract_id != contract.id:
        raise not_found("变更单不存在")
    if order.status != "pending":
        raise not_found("变更单已处理")
    if user.id == order.proposed_by:
        raise forbidden("提案方不能自行处理")
    order.status = "rejected"
    db.add(order)
    service._notify_change(db, contract, order, proposed=False)
    return {"id": order.id, "status": "rejected"}


@router.get("/{contract_id}/change-orders")
def list_change_orders(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    """SC-007 列出变更单。

    改造前**没有这个接口**：提案建得出来，而对方拿不到 `order_id`，
    于是就算界面上有按钮也点不了。缺的不只是按钮——
    **只补按钮不补列表，按钮点不了。**

    `can_decide` 与服务端 `accept_change` 的准入同源（提案人自己不能接受）——
    客户端不重写这个判断，**第二份实现必然抄漏**（UI-075 / TEAM-021 同一条）。
    """
    contract = _get(db, contract_id, user)
    rows = (
        db.query(ChangeOrder)
        .filter(ChangeOrder.contract_id == contract.id)
        .order_by(ChangeOrder.id.desc())
        .all()
    )
    return [
        {"id": r.id, "contract_id": r.contract_id, "proposed_by": r.proposed_by,
         "new_amount_cents": r.new_amount_cents, "reason": r.reason, "status": r.status,
         "new_deadline": iso(r.new_deadline), "scope_change": r.scope_change,
         "created_at": iso(r.created_at),
         "can_decide": r.status == "pending" and r.proposed_by != user.id}
        for r in rows
    ]


@router.post("/{contract_id}/sign")
def sign_contract(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    contract = _get(db, contract_id, user)
    return _dump(service.sign(db, contract, user.id))


@router.get("/{contract_id}/signatures")
def contract_signatures(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    """LAW-002/040 签署留痕与校验：签署后改条款 → 哈希对不上，篡改自证。

    响应里的 `reliability_note` 会诚实说明当前签名的证明力边界。
    """
    contract = _get(db, contract_id, user)
    return service.verify_signatures(db, contract)


@router.post("/{contract_id}/fund")
def fund_contract(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function"),
    user_coupon_id: int | None = None,
):
    """SC-003 托管；可选带 GRW 优惠券。

    补贴先到账再托管：平台把优惠额打给发布方，发布方再托管全额。
    净效果是发布方少掏钱，而托管口径（Σescrow == Σ未放款合约额）不受影响——
    这是刻意选的形态，避免为了打折去改动托管账目本身。
    """
    from app.modules.growth import service as growth
    from app.modules.legal import consent

    consent.require_current_agreement(db, user.id)  # LAW-030 资金动作前校验协议版本
    contract = _get(db, contract_id, user)
    task = db.get(Task, contract.task_id)
    discount = 0
    if user_coupon_id:
        discount = growth.redeem(db, user_coupon_id, user.id, contract,
                                 task.category if task else "")
    service.fund(db, contract, user.id)
    # 资金托管完成 → 任务进入执行中（03 状态机联动）
    transition(db, task, "in_progress")
    return {**_dump(contract), "coupon_discount_cents": discount}
