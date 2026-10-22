"""钱包核心操作。所有资金变动必须走这里并落流水（12.A 审计要求）。"""
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from sqlalchemy.orm import Session

import logging
from app.core.errors import bad_request
from app.core.locks import lock_wallets

from .models import LedgerEntry, WalletAccount

PLATFORM_USER_ID = 0  # 平台佣金账户

# SYNC-002 账本科目全集。**这是一份声明，不是注释**——`_log()` 会拒绝不在其中的科目。
#
# 为什么要显式声明而不是靠扫代码凑：`transfer()` 写的是 `_log(db, id, f"{kind}_out", …)`，
# 科目是拼出来的，静态扫描只能看到后缀 `_out`，前半截只能靠猜调用方传了什么。
# 靠猜的闸门不是闸门。
#
# 每加一条科目，必须同时在 packages/core/src/ledger.ts 的 LEDGER_KIND_LABEL 里
# 给它一个中文名，否则 tests/test_shared_contract_drift.py 会红——
# 因为没有中文名的科目，在用户的账单流水里就是一行英文标识符。
LEDGER_KINDS: frozenset[str] = frozenset({
    "topup", "withdraw", "withdraw_hold", "withdraw_refund",
    "escrow_hold", "escrow_release", "refund", "fee",
    "deposit_hold", "deposit_return", "deposit_forfeit",
    "dispute_split",
    "platform_topup", "platform_settle",
    "tax_withheld", "tax_remit",
    "adjust_in", "adjust_out", "subsidy_in", "subsidy_out",
    "agent_payout_in", "agent_payout_out",
    "verify_hold", "verify_payout", "verify_refund",
    "coop_distribution_in", "coop_distribution_out",
    "team_spend_in", "team_spend_out",
    "team_return_in", "team_return_out",     # TEAM-070（226 号 spec）
})

# transfer() 允许的科目前缀（会各自拼出 _in / _out 两条）
TRANSFER_KINDS: frozenset[str] = frozenset(
    {"adjust", "subsidy", "agent_payout", "coop_distribution", "team_spend",
     "team_return"})   # TEAM-070（226 号 spec）成员把没用完的团队拨款退回团队


def get_or_create(db: Session, user_id: int) -> WalletAccount:
    """取钱包账户，没有就建一个。

    PAY-046：这里原来是 check-then-insert，**两个并发请求会同时看到「没有」**，
    于是都插入，后一个撞上 `wallet_accounts.user_id` 的唯一约束 → 500。
    探针：新用户并发 12 次 `GET /wallet`，稳定出 1 次 500。

    这不是理论上的竞态。真实触发路径至少两条：

    - 客户端首屏**同时**发两个请求（web 与 App 都登着、或者手抖点两下）；
    - 放款后的事件处理与用户自己的请求并发——用户刚收到到账通知就点开钱包，
      正是最可能撞上的那一刻。

    而它 500 的那个页面是**钱包**：用户看到的是「服务器错误」，
    而他刚刚被告知有一笔钱到账。**在钱的页面上报 500，比在别处报 500 更贵。**

    修法用 SAVEPOINT 而不是「先查再插」加锁：
    `begin_nested()` 让插入失败只回滚这一步，**不把外层事务一起带走**——
    这个函数的调用方常常正在做放款/托管这种多步写入，
    外层事务被毒化的代价远大于这一行。
    """
    acct = db.get(WalletAccount, user_id)
    if acct:
        return acct
    try:
        with db.begin_nested():
            acct = WalletAccount(user_id=user_id)
            db.add(acct)
            db.flush()
        return acct
    except IntegrityError:
        # 别人刚建好了：重读一次。读不到才是真的坏了，那就让它抛。
        acct = db.get(WalletAccount, user_id)
        if acct is None:
            raise
        return acct


def _log(db: Session, user_id: int, kind: str, amount: int, contract_id=None, memo=""):
    # SYNC-002 在**写入点**拦住未声明的科目。这里抛异常是有意的：
    # 一笔科目没有中文名就写进账本，之后在用户账单里永远是一行英文，
    # 而且没有任何东西会报错——只能靠肉眼发现。在写入点炸掉便宜得多。
    # 这是编码错误而非用户输入错误，所以不走 bad_request（那是 4xx）。
    if kind not in LEDGER_KINDS:
        raise ValueError(
            f"未声明的账本科目 {kind!r}：请加进 wallet.service.LEDGER_KINDS，"
            f"并在 packages/core/src/ledger.ts 的 LEDGER_KIND_LABEL 里给它中文名"
        )
    db.add(
        LedgerEntry(
            user_id=user_id, kind=kind, amount_cents=amount, contract_id=contract_id, memo=memo
        )
    )


def topup(db: Session, user_id: int, amount: int) -> WalletAccount:
    if amount <= 0:
        raise bad_request("充值金额必须为正", "invalid_amount")
    acct = get_or_create(db, user_id)
    acct.available_cents += amount
    _log(db, user_id, "topup", amount)
    return acct


def _today_withdrawn(db: Session, user_id: int) -> int:
    """当日已提现（含出账流水与待审冻结）总额，用于日限额（PAY-007）。"""
    from sqlalchemy import func

    from app.modules.account.models import utcnow

    from .models import WithdrawRequest

    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    done = -(
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == user_id, LedgerEntry.kind == "withdraw",
                LedgerEntry.created_at >= day_start)
        .scalar()
    )
    pending = (
        db.query(func.coalesce(func.sum(WithdrawRequest.amount_cents), 0))
        # 冻结着的都算：待审、等第二人确认、正在出款（CONC-067）——漏掉任何一种，日限额就能被绕过
        .filter(WithdrawRequest.user_id == user_id, WithdrawRequest.status.in_(FROZEN_WITHDRAW_STATUSES),
                WithdrawRequest.created_at >= day_start)
        .scalar()
    )
    return int(done) + int(pending)


# ── CONC-067 出款两阶段（113 号 spec）───────────────────────────────
#
# 改造前：在**钱包行锁里**调银行出款，失败靠 get_db 整体回滚——「宁可提现失败重来，
# 也不能账扣了钱没打出去」。那只护住了一个方向：银行那边打出去了、而我们的提交失败
# （或者超时、根本不知道打没打），就是**钱出去了账没扣**；而银行慢的那几秒里，
# 这个人的钱包锁与一条池连接一直陪着银行等。
#
# 现在：冻结并记下出款单（`sending`）→ 提交 → 事务外调银行（按出款单号幂等）→
#   成功：另开事务划出冻结、记 withdraw 流水；
#   明确失败：另开事务解冻（即时提现）或退回待审（人审提现），提交后再报错；
#   结果不明（超时 / 网络）：留在 `sending`，由 `/wallet/jobs/resolve-payouts` 按同一个单号重试——
#   银行侧与 VendorCall 都按单号去重，重试不会打两次。
FROZEN_WITHDRAW_STATUSES = ("pending", "awaiting_second", "sending")


def _payout_ref(req) -> str:
    return f"wdreq-{req.id}"


def settle_payout(db: Session, req, on_failure: str) -> dict:
    """调银行并落结果。调用前 `req` 已是 `sending`、钱已在冻结里、事务已提交。

    `on_failure`：明确失败时怎么办——`refund`（即时提现：解冻退回可用）或
    `back_to_review`（人审提现：回到待审，管理员可以再批）。
    """
    from app.vendors import payment_service
    from app.vendors.base import VendorError, checkpoint

    try:
        payout_ref = payment_service.send_payout(db, req.user_id, req.amount_cents, _payout_ref(req))
    except VendorError as exc:
        if exc.retryable:
            # 结果不明：钱还在冻结里，出款单留在 sending，交给补偿 job。不能当失败退回——
            # 银行那边可能已经打出去了，这时再退回可用就是让他能再提一次
            return {"status": "processing", "request_id": req.id,
                    "message": "提现已提交银行处理，结果确认后会通知你"}
        lock_wallets(db, req.user_id)
        acct = get_or_create(db, req.user_id)
        db.refresh(acct)  # 提交点之前读到的版本号已经过时：重新加锁之后按库里的读
        db.refresh(req)
        if req.status == "sending":
            if on_failure == "refund":
                acct.frozen_cents -= req.amount_cents
                acct.available_cents += req.amount_cents
                req.status = "failed"
            else:
                req.status = "pending"
            db.add_all([acct, req])
        checkpoint(db, "出款明确失败：解冻 / 退回待审先落库，再把错误还给调用方")
        raise exc.as_http() from exc
    return _finish_payout(db, req, payout_ref)


def _settle_or_processing(db: Session, req) -> dict:
    """提交点之后：钱已冻结、出款单已落库。从这一刻起，**除了银行明确拒绝**之外的任何意外
    都只能是「处理中」，不能是一个报错——

    报错会让客户端用同一个幂等键重试，而幂等占键在失败时会被放掉（失败不缓存），
    于是重试变成**第二笔**提现；与此同时第一笔的出款单还停在 sending，补偿 job 会把它打出去。
    一次提现意图，打了两次款。V138 的并发测试就是这样撞出来的（一笔在结账时撞上并发修改 409）。
    """
    from fastapi import HTTPException

    from app.vendors.base import checkpoint

    req_id, user_id = req.id, req.user_id  # 失败分支里会话可能处于「待回滚」，不能再碰 ORM 属性
    try:
        res = settle_payout(db, req, on_failure="refund")
        # 结账也在这里提交：留到请求结束时再提交的话，那一刻撞上并发修改（SQLite 没有行锁，靠版本号）
        # 会变成一个报错——而银行那边钱已经打出去了
        checkpoint(db, "出款结账：银行已确认，划出冻结与流水当场落库，失败也只能是「处理中」")
        return res
    except HTTPException:
        raise  # 银行明确拒绝：settle_payout 已经解冻并落库，这个错是真的
    except Exception:  # noqa: BLE001
        db.rollback()  # 先回滚：会话可能因为 flush 失败处于「待回滚」，之后任何读都会再抛一次
        logging.getLogger("app.wallet").exception("payout_settlement_interrupted",
                                                  extra={"user_id": user_id})
        return {"status": "processing", "request_id": req_id,
                "message": "提现已提交银行处理，结果确认后会通知你"}


def _finish_payout(db: Session, req, payout_ref: str) -> dict:
    from app.modules.account.models import utcnow

    lock_wallets(db, req.user_id)
    acct = get_or_create(db, req.user_id)
    db.refresh(acct)  # 提交点之前读到的版本号已经过时：重新加锁之后按库里的读
    db.refresh(req)
    if req.status != "sending":  # 补偿 job 与请求并发时，先到的那个已经落过了
        return {"status": "done", "request_id": req.id, "payout_ref": payout_ref,
                "available_cents": acct.available_cents, "frozen_cents": acct.frozen_cents}
    acct.frozen_cents -= req.amount_cents
    memo = (f"提现打款 {payout_ref}" if req.decided_by is None and req.first_approved_by is None
            else f"大额提现批准 #{req.id} 打款 {payout_ref}")
    _log(db, req.user_id, "withdraw", -req.amount_cents, memo=memo)
    req.status = "paid" if req.decided_by is None and req.first_approved_by is None else "approved"
    req.decided_at = req.decided_at or utcnow()
    db.add_all([acct, req])
    return {"status": "done", "request_id": req.id, "payout_ref": payout_ref,
            "available_cents": acct.available_cents, "frozen_cents": acct.frozen_cents}


def resolve_stuck_payouts(db: Session, older_than_seconds: int = 120, limit: int = 50) -> dict:
    """补偿：结果不明的出款单按同一个单号重试（银行与 VendorCall 都按单号去重）。"""
    from datetime import timedelta

    from app.modules.account.models import utcnow
    from app.vendors.base import release

    from .models import WithdrawRequest

    cutoff = utcnow() - timedelta(seconds=older_than_seconds)
    ids = [r.id for r in db.query(WithdrawRequest)
           .filter(WithdrawRequest.status == "sending", WithdrawRequest.created_at < cutoff)
           .order_by(WithdrawRequest.id).limit(limit)]
    release(db)
    out = {"checked": len(ids), "paid": 0, "still_unknown": 0, "failed": 0}
    for rid in ids:
        req = db.get(WithdrawRequest, rid)
        release(db)
        try:
            res = settle_payout(db, req, on_failure="refund" if req.first_approved_by is None
                                and req.decided_by is None else "back_to_review")
        except Exception:  # noqa: BLE001 - 明确失败已在 settle_payout 里落库
            out["failed"] += 1
            continue
        if res["status"] == "done":
            out["paid"] += 1
            db.commit()
        else:
            out["still_unknown"] += 1
    return out


def withdraw(db: Session, user_id: int, amount: int) -> dict:
    """PAY-005/007 提现：须先绑收款账户；日限额硬拒；大额冻结进人审；小额即时出账。"""
    from app.core.config import settings
    from app.modules.account.models import utcnow

    from .models import PayoutAccount, WithdrawRequest

    if not db.get(PayoutAccount, user_id):  # PAY-005 提现前置：必须已绑收款账户
        raise bad_request("请先绑定收款账户", "no_payout_account")
    lock_wallets(db, user_id)  # CONC-012 并发提现必须串行，否则日限额与余额都能被绕过
    acct = get_or_create(db, user_id)
    if amount <= 0 or amount > acct.available_cents:
        raise bad_request("可用余额不足", "insufficient_balance")
    today = _today_withdrawn(db, user_id)
    if today + amount > settings.WITHDRAW_DAILY_LIMIT_CENTS:
        raise bad_request(
            f"超出单日提现限额（{settings.WITHDRAW_DAILY_LIMIT_CENTS / 100:.0f} 元）",
            "daily_limit_exceeded",
        )
    # AML-001/003 风控判定必须在**这个锁里**做：并发提现各自读到「还没超」
    # 再分别放行，和拆分是同一个洞的两种利用姿势
    from app.modules.aml import service as aml

    verdict = aml.assess_withdrawal(db, user_id, amount, today)
    if verdict["needs_review"]:
        # 大额或累计达标：可用 → 冻结，生成人审申请（批准划出 / 驳回解冻）
        acct.available_cents -= amount
        acct.frozen_cents += amount
        req = WithdrawRequest(user_id=user_id, amount_cents=amount)
        db.add(req)
        db.flush()
        _log(db, user_id, "withdraw_hold", -amount, memo=f"提现待审 #{req.id}")
        aml.record_withdrawal_flags(db, user_id, verdict["reasons"], req.id)
        # AML-030/031 tipping-off：给用户的话必须中性。
        # 这里**绝不能**回 verdict["reasons"]——那等于告诉他「你哪条触发了风控」，
        # 既违反《反洗钱法》第五条的保密义务，也直接教会他下次怎么规避。
        return {"status": "pending_review", "request_id": req.id,
                "message": aml.NEUTRAL_REVIEW_MESSAGE,
                "available_cents": acct.available_cents, "frozen_cents": acct.frozen_cents}
    # CONC-067 两阶段：先冻结并记下出款单，提交后再调银行（见 settle_payout）
    from app.vendors.base import checkpoint

    acct.available_cents -= amount
    acct.frozen_cents += amount
    req = WithdrawRequest(user_id=user_id, amount_cents=amount, status="sending")
    db.add_all([acct, req])
    db.flush()
    checkpoint(db, "提现两阶段：冻结并记下出款单之后再调银行，钱包锁与连接不陪银行等")
    return _settle_or_processing(db, req)


def decide_withdraw(db: Session, req, approve: bool, admin_id: int | None,
                    timeout: bool = False) -> dict:
    """PAY-007 人审裁决：批准=冻结划出（落 withdraw 流水），驳回=解冻退回。

    PAY-042 超过 `WITHDRAW_DUAL_APPROVAL_CENTS` 的出款要**两个不同管理员**
    先后确认（maker-checker）：第一次批准只记下「谁、什么时候」，**钱不动**；
    第二个人确认后才真的打出去。

    刻意不改既有语义：门槛以下仍然一人批准即放款，行为与改造前一致。

    PAY-044 `timeout=True` 是**系统超时关闭**（75 号 spec）：走的是与人工驳回
    完全相同的解冻路径，只有 `decided_by`（留空）和通知文案不同——
    另写一份解冻逻辑迟早会漏掉其中一步（第二份实现必然抄漏）。
    """
    from app.core.config import settings
    from app.modules.account.models import utcnow

    if timeout and approve:
        # 超时只能往可逆方向兜。自动放款会让「等 7 天」变成绕过四眼原则的办法，
        # 而攻击者需要做的只是等——这条在代码里也要拦住，不能只写在 spec 里。
        raise ValueError("超时兜底不得放款，只能退回可用余额")
    if req.status not in ("pending", "awaiting_second"):
        raise bad_request("该提现申请已处理", "request_closed")

    dual = req.amount_cents > settings.WITHDRAW_DUAL_APPROVAL_CENTS
    if approve and dual:
        if req.status == "pending":
            # 第一次批准：只记人和时间，钱一分不动
            req.first_approved_by = admin_id
            req.first_approved_at = utcnow()
            req.status = "awaiting_second"
            db.add(req)
            _notify_withdraw_first_pass(db, req)
            return {"status": req.status, "amount_cents": req.amount_cents,
                    "first_approved_by": admin_id,
                    "message": "已记录你的复核意见，需另一位管理员确认后才会打款"}
        if req.first_approved_by == admin_id:
            # 同一个人点两次，等于没有这条规则
            raise bad_request(
                f"超过 ¥{settings.WITHDRAW_DUAL_APPROVAL_CENTS / 100:.2f} 的出款需要"
                "两个不同管理员先后确认。第一次复核就是你——请转交另一位管理员确认",
                "same_approver",
            )
        # SEC-061f / PAY-042c（155 号 spec）：大额的第二人要超级管理员；第二人级别不低于第一人
        if admin_id is not None:
            from app.core.admin_roles import check_second_approver
            from app.modules.account.models import User

            check_second_approver(db.get(User, req.first_approved_by) if req.first_approved_by else None,
                                  db.get(User, admin_id), req.amount_cents)
    lock_wallets(db, req.user_id)  # CONC-012
    acct = get_or_create(db, req.user_id)
    if approve:
        # CONC-067 两阶段：批准记下来、出款单置 sending 并提交，再调银行
        from app.vendors.base import checkpoint

        req.decided_by = admin_id
        req.decided_at = utcnow()
        req.status = "sending"
        db.add(req)
        checkpoint(db, "人审提现批准：批准与出款单先落库，再调银行")
        res = settle_payout(db, req, on_failure="back_to_review")
        if res["status"] == "done":
            _notify_withdraw_decision(db, req, True, timeout=timeout)
        return {"status": req.status if res["status"] == "done" else "sending",
                "amount_cents": req.amount_cents, "first_approved_by": req.first_approved_by}
    else:
        acct.frozen_cents -= req.amount_cents
        acct.available_cents += req.amount_cents
        why = "超时关闭退回" if timeout else "驳回退回"
        _log(db, req.user_id, "withdraw_refund", req.amount_cents,
             memo=f"大额提现{why} #{req.id}")
        req.status = "rejected"
    req.decided_by = admin_id
    req.decided_at = utcnow()
    db.add_all([acct, req])
    _notify_withdraw_decision(db, req, approve, timeout=timeout)
    return {"status": req.status, "amount_cents": req.amount_cents,
            "first_approved_by": req.first_approved_by}


def _notify_withdraw_first_pass(db: Session, req) -> None:
    """PAY-042 第一次复核通过时也要告诉用户一句——他的钱还在冻结里。

    不说的话，他看到的是「等 1 个工作日」之后什么都没发生；
    而措辞仍然中性：**不解释为什么要两个人看**（AML-030/031 同一条）。
    """
    from app.modules.notification.service import notify

    notify(db, req.user_id, "funds", "提现复核进行中",
           f"你的提现 ¥{req.amount_cents / 100:.2f} 已完成初次复核，"
           f"按规定需再经一位负责人确认后打款。")


def _notify_withdraw_decision(db: Session, req, approve: bool, timeout: bool = False) -> None:
    """PAY-041 裁决要告诉用户——而**驳回不能说原因**。

    改造前这里一个字都不发：用户看到「通常 1 个工作日内处理完成」，
    然后钱要么回来要么不回来，平台全程静音。三万块。

    驳回文案刻意中性。不给原因不是敷衍：AML-030/031（《反洗钱法》第五条的
    保密义务）不允许告诉他命中了什么，而且说了就等于教他下次怎么规避。

    归 `funds` 类——`notify()` 的既有规则里 funds 本来就不可被开关关掉，
    所以**不需要进 `MUST_REACH`**（那张表是给「本该可关却不能关」的用的）。
    """
    from app.modules.notification.service import notify

    yuan = f"¥{req.amount_cents / 100:.2f}"
    if approve:
        notify(db, req.user_id, "funds", "提现已通过复核",
               f"你的提现 {yuan} 已通过复核并发起打款，到账时间取决于银行处理。")
    elif timeout:
        # PAY-044 超时关闭的原因**可以说清楚**：它不涉及任何风控命中信息，
        # 而人工驳回必须中性（AML-030/031）。含糊其辞反而会让用户
        # 以为自己被拒了，从此不敢再提。
        from app.core.config import settings

        notify(db, req.user_id, "funds", "提现申请已超时关闭",
               f"你的提现 {yuan} 因超过 {settings.WITHDRAW_REVIEW_TIMEOUT_DAYS} 天"
               f"未完成复核已自动关闭，款项已退回可用余额，你可以重新发起。")
    else:
        notify(db, req.user_id, "funds", "提现未通过复核",
               f"你的提现 {yuan} 未通过复核，款项已退回可用余额，你可以重新发起。")


def remind_withdraw_reviews(db: Session, now=None) -> dict:
    """PAY-044 人审提现的催办与超时兜底（75 号 spec）。

    探针：一审通过后把 `first_approved_at` 推到 30 天前，跑一遍全部 job——
    状态还是 `awaiting_second`，用户的两万一**一直冻着**，没有人被提醒过。
    V99 加了一道控制，同时加了一个新的卡点；**卡点没有兜底，
    它就是一个新的「钱能进不能出」**。

    兜底方向只有一个：退回可用余额。超时是「没有人看」的证据，
    不是「可以放行」的授权（见 `decide_withdraw` 里的那道拦截）。
    """
    from datetime import timedelta

    from app.core.config import settings
    from app.modules.account.models import User, utcnow
    from app.modules.notification.service import notify

    from .models import WithdrawRequest

    now = now or utcnow()
    interval = timedelta(hours=max(settings.WITHDRAW_REVIEW_REMIND_HOURS, 1))
    deadline = timedelta(days=max(settings.WITHDRAW_REVIEW_TIMEOUT_DAYS, 1))
    rows = (
        db.query(WithdrawRequest)
        .filter(WithdrawRequest.status.in_(("pending", "awaiting_second")))
        .all()
    )
    if not rows:
        return {"reminded": 0, "closed": 0}
    admin_ids = [u.id for u in db.query(User).filter(User.is_admin.is_(True)).all()]

    reminded = closed = 0
    for req in rows:
        if now - req.created_at >= deadline:
            decide_withdraw(db, req, approve=False, admin_id=None, timeout=True)
            from app.modules.admin.router import record_audit

            # admin_id=0 表示「系统」：审计表只增不改，一笔动了钱的操作
            # 不能因为没有操作人就不留痕
            record_audit(db, 0, "withdraw_timeout_close", "withdraw_request", req.id,
                         f"超过 {settings.WITHDRAW_REVIEW_TIMEOUT_DAYS} 天无人完成复核，"
                         f"自动退回 {req.amount_cents} 分")
            closed += 1
            continue
        last = req.review_reminded_at or req.first_approved_at or req.created_at
        if now - last < interval:
            continue
        hours = int((now - req.created_at).total_seconds() // 3600)
        yuan = f"¥{req.amount_cents / 100:.2f}"
        if req.status == "awaiting_second":
            # 收到的人必须知道自己是第一个还是第二个，否则他会以为
            # 「已经有人在处理了」而放过去——那正是它卡住的原因
            body = (f"提现申请 #{req.id}（{yuan}）已完成初次复核，正在等待"
                    f"**另一位**管理员二次确认，已等待 {hours} 小时。"
                    f"超过 {settings.WITHDRAW_REVIEW_TIMEOUT_DAYS} 天将自动退回用户余额。")
        else:
            body = (f"提现申请 #{req.id}（{yuan}）等待人工复核已 {hours} 小时。"
                    f"用户的这笔钱在此期间是冻结的；超过 "
                    f"{settings.WITHDRAW_REVIEW_TIMEOUT_DAYS} 天将自动退回。")
        for uid in admin_ids:
            notify(db, uid, "funds", "提现复核待处理", body)
        req.review_reminded_at = now
        db.add(req)
        reminded += 1
    return {"reminded": reminded, "closed": closed}


def escrow_hold(db: Session, user_id: int, amount: int, contract_id: int):
    """SC-003 资金托管：可用 → 托管。"""
    acct = get_or_create(db, user_id)
    if acct.available_cents < amount:
        raise bad_request("可用余额不足，请先充值", "insufficient_balance")
    acct.available_cents -= amount
    acct.escrow_cents += amount
    _log(db, user_id, "escrow_hold", -amount, contract_id, "合约资金托管")


def escrow_release(
    db: Session, payer_id: int, payee_id: int, amount: int, fee: int, contract_id: int
):
    """SC-005/SC-009 验收放款：托管 → 执行者可用（扣佣金）。"""
    payer = get_or_create(db, payer_id)
    if payer.escrow_cents < amount:
        raise bad_request("托管余额异常", "escrow_mismatch")
    payer.escrow_cents -= amount
    payee = get_or_create(db, payee_id)
    payee.available_cents += amount - fee
    _log(db, payee_id, "escrow_release", amount - fee, contract_id, "任务验收放款")
    if fee > 0:
        platform = get_or_create(db, PLATFORM_USER_ID)
        platform.available_cents += fee
        _log(db, PLATFORM_USER_ID, "fee", fee, contract_id, "平台佣金")


def escrow_refund(db: Session, payer_id: int, amount: int, contract_id: int, memo="托管退款"):
    """SC-006 取消/违约退款：托管 → 发布者可用（原路退回的模拟）。"""
    payer = get_or_create(db, payer_id)
    if payer.escrow_cents < amount:
        raise bad_request("托管余额异常", "escrow_mismatch")
    payer.escrow_cents -= amount
    payer.available_cents += amount
    _log(db, payer_id, "refund", amount, contract_id, memo)


def platform_finance(db: Session) -> dict:
    """SC-009/OPS-010 平台收入：以平台账户实际入账为唯一事实来源。

    佣金按每笔放款/裁决分账整数向下取整实收（含纠纷/取消场景），
    与「Σ released×费率」的估算口径不同——后者会漏计纠纷/取消佣金且有取整漂移。
    """
    from sqlalchemy import func

    platform = get_or_create(db, PLATFORM_USER_ID)
    # fee 流水为正数入账（见 escrow_release/dispute_split），直接求和即累计佣金
    total_fee = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "fee")
        .scalar()
    )
    settled = -(
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "platform_settle")
        .scalar()
    )
    fee_count = (
        db.query(func.count(LedgerEntry.id))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "fee")
        .scalar()
    )
    return {
        "balance_cents": platform.available_cents,      # 可结算余额
        "total_fee_cents": int(total_fee),              # 累计佣金收入（实收）
        "settled_cents": int(settled),                  # 已结算提走
        "fee_count": int(fee_count),
    }


def settle_platform(db: Session, amount: int, memo: str = "平台收入结算") -> dict:
    """OPS-010 平台收入结算：把平台账户余额划出（模拟对公结算/提现）。"""
    lock_wallets(db, PLATFORM_USER_ID)  # CONC-012
    platform = get_or_create(db, PLATFORM_USER_ID)
    if amount <= 0 or amount > platform.available_cents:
        raise bad_request("结算金额超出平台可用余额", "insufficient_platform_balance")
    platform.available_cents -= amount
    _log(db, PLATFORM_USER_ID, "platform_settle", -amount, memo=memo)
    return {"settled_cents": amount, "balance_cents": platform.available_cents}


def transfer(db: Session, from_id: int, to_id: int, amount: int, contract_id=None, memo="",
             kind: str = "adjust"):
    """可用余额间转账（申诉纠正性结算、GRW 补贴等平台内部调整）。

    `kind` 决定流水科目：`adjust`（默认，内部调整）/ `subsidy`（GRW 补贴）。
    补贴单独成科目的理由是对账口径不同——补贴会减少平台账户余额，
    必须计入平台账户不变量，否则日终对账会报「平台佣金不符」。
    """
    # SYNC-002 拼科目之前先验前缀。不验的话 `kind="foo"` 要等到 _log() 才炸，
    # 而那时钱已经从 src 扣掉了——同一个事务里会回滚，但报错指向的是拼好的
    # "foo_out" 而不是调用方传的 "foo"，排查时多绕一圈。
    if kind not in TRANSFER_KINDS:
        raise ValueError(f"未声明的转账科目前缀 {kind!r}：请加进 wallet.service.TRANSFER_KINDS")
    if amount <= 0:
        raise bad_request("金额必须为正", "invalid_amount")
    lock_wallets(db, from_id, to_id)  # CONC-011 按 user_id 升序加锁，避免对向转账死锁
    src = get_or_create(db, from_id)
    if src.available_cents < amount:
        raise bad_request("余额不足以执行调整", "insufficient_balance")
    src.available_cents -= amount
    _log(db, from_id, f"{kind}_out", -amount, contract_id, memo)
    dst = get_or_create(db, to_id)
    dst.available_cents += amount
    _log(db, to_id, f"{kind}_in", amount, contract_id, memo)


def fund_platform(db: Session, amount: int, memo: str = "平台补贴金注资") -> dict:
    """GRW-003 平台补贴池注资：从平台外部注入资金到平台账户。

    冷启动时平台还没有佣金收入，补贴池必须先注资才能发券——
    这笔钱同样进账本（`platform_topup`），因此全局守恒与平台账户不变量
    都能继续成立，补贴永远能追到出资方。
    """
    if amount <= 0:
        raise bad_request("注资金额必须为正", "invalid_amount")
    lock_wallets(db, PLATFORM_USER_ID)
    platform = get_or_create(db, PLATFORM_USER_ID)
    platform.available_cents += amount
    _log(db, PLATFORM_USER_ID, "platform_topup", amount, memo=memo)
    return {"balance_cents": platform.available_cents, "funded_cents": amount}


def freeze_deposit(db: Session, user_id: int, amount: int, contract_id: int):
    """CRED-005 保证金冻结：可用 → 冻结。"""
    acct = get_or_create(db, user_id)
    if acct.available_cents < amount:
        raise bad_request("可用余额不足以缴纳保证金", "insufficient_deposit")
    acct.available_cents -= amount
    acct.frozen_cents += amount
    _log(db, user_id, "deposit_hold", -amount, contract_id, "任务保证金冻结")


def unfreeze_deposit(db: Session, user_id: int, amount: int, contract_id: int):
    """保证金退还：冻结 → 可用。"""
    acct = get_or_create(db, user_id)
    if acct.frozen_cents < amount:
        raise bad_request("冻结余额异常", "frozen_mismatch")
    acct.frozen_cents -= amount
    acct.available_cents += amount
    _log(db, user_id, "deposit_return", amount, contract_id, "保证金退还")


def forfeit_deposit(db: Session, executor_id: int, requester_id: int, amount: int, contract_id: int):
    """执行者违约：保证金罚没给发布者。"""
    acct = get_or_create(db, executor_id)
    if acct.frozen_cents < amount:
        raise bad_request("冻结余额异常", "frozen_mismatch")
    acct.frozen_cents -= amount
    _log(db, executor_id, "deposit_forfeit", -amount, contract_id, "违约保证金罚没")
    payee = get_or_create(db, requester_id)
    payee.available_cents += amount
    _log(db, requester_id, "deposit_forfeit", amount, contract_id, "对方违约保证金赔付")


def dispute_split(
    db: Session, payer_id: int, payee_id: int, total: int, payee_share: int, fee: int, contract_id: int
):
    """SC-008/DSP-007 仲裁分割：托管按裁决比例分给双方（佣金只对执行者所得部分收取）。"""
    payer = get_or_create(db, payer_id)
    if payer.escrow_cents < total:
        raise bad_request("托管余额异常", "escrow_mismatch")
    payer.escrow_cents -= total
    refund_part = total - payee_share
    if refund_part > 0:
        payer.available_cents += refund_part
        _log(db, payer_id, "dispute_split", refund_part, contract_id, "仲裁退回")
    if payee_share > 0:
        payee = get_or_create(db, payee_id)
        payee.available_cents += payee_share - fee
        _log(db, payee_id, "dispute_split", payee_share - fee, contract_id, "仲裁获得")
        if fee > 0:
            platform = get_or_create(db, PLATFORM_USER_ID)
            platform.available_cents += fee
            _log(db, PLATFORM_USER_ID, "fee", fee, contract_id, "平台佣金(仲裁)")


# ------------------------------------------------------------------ FIN-061 按期间的平台财务（144 号 spec）
PERIOD_MAX = 24   # 一次最多 24 个期间（两年的月报 / 六年的季报）
# 平台账户上的科目怎么归到报表的几栏。没列出来的科目归「其他调整」，不会被悄悄漏掉
PERIOD_COLUMNS = {"fee": "fee_cents", "platform_settle": "settled_cents", "subsidy_out": "subsidy_cents"}


def period_bounds(granularity: str, start: str, end: str, limit: int = PERIOD_MAX) -> list[tuple[str, datetime, datetime]]:
    """北京时间的自然月 / 自然季度，返回 [(标签, UTC 起, UTC 止)]。start / end 形如 2026-07（季度按所在季度）。"""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Shanghai")

    def first(label: str) -> tuple[int, int]:
        y, m = (int(x) for x in label.split("-"))
        if not (1 <= m <= 12):
            raise ValueError(label)
        return y, (m - 1) // 3 * 3 + 1 if granularity == "quarter" else m

    y, m = first(start)
    ey, em = first(end)
    step = 3 if granularity == "quarter" else 1
    out = []
    while (y, m) <= (ey, em):
        ny, nm = (y + (m - 1 + step) // 12, (m - 1 + step) % 12 + 1)
        lo = datetime(y, m, 1, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
        hi = datetime(ny, nm, 1, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
        label = f"{y}-Q{(m - 1) // 3 + 1}" if granularity == "quarter" else f"{y}-{m:02d}"
        out.append((label, lo, hi))
        if len(out) > limit:
            raise bad_request(f"一次最多看 {PERIOD_MAX} 个期间：请缩短起止范围", "period_range_too_long")
        y, m = ny, nm
    if not out:
        raise bad_request("结束期间不能早于开始期间", "period_range_invalid")
    return out


def platform_finance_periods(db: Session, granularity: str, start: str, end: str) -> dict:
    """FIN-061 按期间的报表；FIN-063（223 号 spec）有锁账的月份时，已锁的月份读快照、补记记到第一个未锁月份。
    一个月都没锁时与锁账之前完全一样（同一段计算），只多几个恒为默认值的字段。"""
    from .models import FinancePeriodLock

    locks = {x.period: x for x in db.query(FinancePeriodLock).all()}
    if not locks:
        out = _live_periods(db, granularity, start, end)
        for r in out["periods"]:
            r.update(_LOCK_DEFAULTS)
        return {**out, "locked_through": None, "locked_at": None}
    bounds = period_bounds(granularity, start, end)      # 先按请求的粒度校验范围与上限
    months = period_bounds("month", f"{bounds[0][0][:4]}-{_first_month(bounds[0][0])}", _last_month(bounds[-1][0]),
                           limit=PERIOD_MAX * 3)
    rows = _locked_month_rows(db, months, locks)
    if granularity == "quarter":
        rows = [_sum_months(label, lo, hi, [r for r in rows if lo <= r["start"] < hi]) for label, lo, hi in bounds]
    top = max(locks.values(), key=lambda x: x.period)
    return {"granularity": granularity, "periods": rows, "locked_through": top.period, "locked_at": top.locked_at}


_LOCK_DEFAULTS = {"closed": False, "late_cents": 0, "late_count": 0, "carried_in_cents": 0, "carried_in_count": 0}
_RAW_COLS = ("fee_cents", "settled_cents", "subsidy_cents", "other_cents")


def _first_month(label: str) -> str:
    return f"{(int(label[-1]) - 1) * 3 + 1:02d}" if "-Q" in label else label[5:7]


def _last_month(label: str) -> str:
    return f"{label[:4]}-{int(label[-1]) * 3:02d}" if "-Q" in label else label


def _next_month(label: str) -> str:
    y, m = int(label[:4]), int(label[5:7])
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def _raw(db: Session, *conds) -> dict:
    """按报表栏目的原始合计（出账为负）与笔数、佣金笔数。"""
    from sqlalchemy import func

    out = {c: 0 for c in _RAW_COLS} | {"count": 0, "fee_count": 0}
    for kind, amount, n in (db.query(LedgerEntry.kind, func.coalesce(func.sum(LedgerEntry.amount_cents), 0),
                                     func.count(LedgerEntry.id))
                            .filter(LedgerEntry.user_id == PLATFORM_USER_ID, *conds).group_by(LedgerEntry.kind).all()):
        out[PERIOD_COLUMNS.get(kind, "other_cents")] += int(amount)
        out["count"] += int(n)
        if kind == "fee":
            out["fee_count"] += int(n)
    return out


def _row(label: str, lo: datetime, hi: datetime, raw: dict, opening: int, closing: int) -> dict:
    net = sum(raw[c] for c in _RAW_COLS)
    return {"period": label, "start": lo, "end": hi, "fee_cents": raw["fee_cents"], "fee_count": raw["fee_count"],
            "settled_cents": -raw["settled_cents"], "subsidy_cents": -raw["subsidy_cents"],
            "other_cents": raw["other_cents"], "net_cents": net, "opening_cents": opening, "closing_cents": closing,
            "balanced": closing - opening == net}


def _locked_month_rows(db: Session, months: list, locks: dict) -> list[dict]:
    """已锁的月份：锁账时的快照，另报「锁账后又记进这个月的」合计与笔数（late），它们已记到 late_to 那个月。
    锁到 W 月时，W 月以前（含）都按已锁处理；W 的下一个月是第一个未锁月份，补记全记在这里（carried_in）：
    本期多出这些、期初少这些——于是它的期初正好等于 W 月快照的期末，已出的数一分不变。"""
    top = max(locks)
    target = _next_month(top)
    rows = []
    for label, lo, hi in months:
        if label <= top:
            lock = locks.get(label)
            live = _raw(db, LedgerEntry.created_at >= lo, LedgerEntry.created_at < hi)
            if lock is not None:
                row = {**lock.snapshot, "start": lo, "end": hi}
                late, late_n = sum(live[c] for c in _RAW_COLS) - lock.in_month_cents, live["count"] - lock.in_month_count
            else:   # 锁到 W 时还没有流水的更早月份
                row = _row(label, lo, hi, {c: 0 for c in _RAW_COLS} | {"fee_count": 0}, 0, 0)
                late, late_n = sum(live[c] for c in _RAW_COLS), live["count"]
            rows.append({**row, **_LOCK_DEFAULTS, "closed": True, "late_cents": late, "late_count": late_n})
            continue
        raw = _raw(db, LedgerEntry.created_at >= lo, LedgerEntry.created_at < hi)
        opening = sum(_raw(db, LedgerEntry.created_at < lo)[c] for c in _RAW_COLS)
        closing = sum(_raw(db, LedgerEntry.created_at < hi)[c] for c in _RAW_COLS)
        carried, carried_n = 0, 0
        if label == target:
            lock = locks[top]
            now_cum = _raw(db, LedgerEntry.created_at < lo)
            for c in _RAW_COLS:
                d = now_cum[c] - int(lock.cumulative.get(c, 0))
                raw[c] += d
                carried += d
            raw["fee_count"] += now_cum["fee_count"] - int(lock.cumulative.get("fee_count", 0))
            carried_n = now_cum["count"] - int(lock.cumulative.get("count", 0))
            opening -= carried
        rows.append({**_row(label, lo, hi, raw, opening, closing), **_LOCK_DEFAULTS,
                     "carried_in_cents": carried, "carried_in_count": carried_n})
    return rows


def _sum_months(label: str, lo: datetime, hi: datetime, months: list[dict]) -> dict:
    raw = {"fee_cents": sum(m["fee_cents"] for m in months), "settled_cents": -sum(m["settled_cents"] for m in months),
           "subsidy_cents": -sum(m["subsidy_cents"] for m in months), "other_cents": sum(m["other_cents"] for m in months),
           "fee_count": sum(m["fee_count"] for m in months)}
    row = _row(label, lo, hi, raw, months[0]["opening_cents"], months[-1]["closing_cents"])
    return {**row, "closed": all(m["closed"] for m in months),
            **{k: sum(m[k] for m in months) for k in ("late_cents", "late_count", "carried_in_cents", "carried_in_count")}}


def lock_periods(db: Session, through: str, admin_id: int, now: datetime) -> list[str]:
    """FIN-063 锁账到 through 月（含）：从上次锁到的下一个月（第一次锁则从有流水的第一个月）起逐月存快照。
    只能锁已经过完的月份；锁过的不能再锁、不能解锁——要改已出的数，在当期记一笔调整。"""
    from sqlalchemy import func

    from app.modules.workbench.service import local

    from .models import FinancePeriodLock

    _, lo, hi = period_bounds("month", through, through)[0]
    if hi > now:
        raise bad_request(f"{through} 还没过完：只能锁已经结束的月份（北京时间）", "period_not_ended")
    locks = {x.period: x for x in db.query(FinancePeriodLock).all()}
    top = max(locks) if locks else None
    if top and through <= top:
        raise bad_request(f"已经锁到 {top}：锁过的月份不能再锁，要更正请在当期记调整", "period_already_closed")
    if top:
        start = _next_month(top)
    else:
        first = db.query(func.min(LedgerEntry.created_at)).filter(LedgerEntry.user_id == PLATFORM_USER_ID).scalar()
        start = min(through, f"{local(first).year}-{local(first).month:02d}") if first else through
    done = []
    for label, mlo, mhi in period_bounds("month", start, through, limit=10_000):
        row = _locked_month_rows(db, [(label, mlo, mhi)], locks)[0] if locks else \
            {**_live_periods(db, "month", label, label)["periods"][0]}
        live = _raw(db, LedgerEntry.created_at >= mlo, LedgerEntry.created_at < mhi)
        snap = {k: v for k, v in row.items() if k not in ("start", "end", *_LOCK_DEFAULTS)}
        lock = FinancePeriodLock(period=label, snapshot=snap, in_month_cents=sum(live[c] for c in _RAW_COLS),
                                 in_month_count=live["count"], cumulative=_raw(db, LedgerEntry.created_at < mhi),
                                 locked_by=admin_id, locked_at=now)
        db.add(lock)
        db.flush()
        locks[label] = lock
        done.append(label)
    return done


def _live_periods(db: Session, granularity: str, start: str, end: str) -> dict:
    """平台账户按期间的收支：佣金（实收）、结算划出、补贴支出、其他调整，期初 / 期末余额，
    以及一条自检：期末 − 期初 = 本期净额。数字全部来自平台账户流水（与累计口径同一个事实来源）。"""
    from sqlalchemy import func

    rows = []
    for label, lo, hi in period_bounds(granularity, start, end):
        opening = db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).filter(
            LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.created_at < lo).scalar()
        by_kind = dict(db.query(LedgerEntry.kind, func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
                       .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.created_at >= lo,
                               LedgerEntry.created_at < hi).group_by(LedgerEntry.kind).all())
        fee_count = db.query(func.count(LedgerEntry.id)).filter(
            LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "fee",
            LedgerEntry.created_at >= lo, LedgerEntry.created_at < hi).scalar()
        cols = {"fee_cents": 0, "settled_cents": 0, "subsidy_cents": 0, "other_cents": 0}
        for kind, amount in by_kind.items():
            cols[PERIOD_COLUMNS.get(kind, "other_cents")] += int(amount)
        net = sum(cols.values())
        # 期末余额单独查一次，不由期初加净额推出来——这样「期末 − 期初 = 本期净额」才是一条真的自检
        closing = db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).filter(
            LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.created_at < hi).scalar()
        rows.append({
            "period": label, "start": lo, "end": hi,
            "fee_cents": cols["fee_cents"], "fee_count": int(fee_count),
            # 出账在流水里是负数；报表里写成正数「划出 / 支出了多少」，人读起来不绕
            "settled_cents": -cols["settled_cents"], "subsidy_cents": -cols["subsidy_cents"],
            "other_cents": cols["other_cents"], "net_cents": net,
            "opening_cents": int(opening), "closing_cents": int(closing),
            "balanced": int(closing) - int(opening) == net,
        })
    return {"granularity": granularity, "periods": rows}


# FIN-062（242 号 spec）按期间的成交额与代扣税额：与平台收支（144 号）分开出表
GMV_TAX_BASIS = [
    "成交额（GMV）按放款算：期间内验收放款给执行者的金额加上同一笔里扣的平台佣金（即发布方托管里放出去的总额）；"
    "未放款的托管不算，退回发布方的另列「退款」，纠纷裁决分给执行者的另列「纠纷分账」，都不计入成交额。",
    "代扣税额按税款专户的流水算：期间内代扣进专户的金额与笔数、缴库划出的金额；「期末待缴」是专户到期末的余额。",
    "被代扣人数与对应收入取自每笔代扣的完税明细（只记扣了税的支付）。",
    "期间按北京时间自然月 / 季度、按流水记账时间归属；本表不受锁账影响（锁账只管平台收支表）。",
]
GMV_TAX_DRAFT_NOTE = "口径草稿：对外申报、报送前请财税负责人确认口径（钱与申报的事 AI 只出草稿，人确认）。"


def gmv_tax_periods(db: Session, granularity: str, start: str, end: str) -> dict:
    from sqlalchemy import func

    from app.modules.tax.models import TaxWithholding
    from app.modules.tax.service import TAX_USER_ID

    bounds = period_bounds(granularity, start, end)
    rows = []
    for label, lo, hi in bounds:
        in_range = (LedgerEntry.created_at >= lo, LedgerEntry.created_at < hi)
        sums: dict[tuple[str, bool], tuple[int, int]] = {}
        for kind, is_platform, amount, n in (
                db.query(LedgerEntry.kind, LedgerEntry.user_id == PLATFORM_USER_ID,
                         func.coalesce(func.sum(LedgerEntry.amount_cents), 0), func.count(LedgerEntry.id))
                .filter(*in_range, LedgerEntry.user_id != TAX_USER_ID,
                        LedgerEntry.kind.in_(("escrow_release", "fee", "dispute_split", "refund")))
                .group_by(LedgerEntry.kind, LedgerEntry.user_id == PLATFORM_USER_ID).all()):
            a, c = sums.get((kind, bool(is_platform)), (0, 0))
            sums[(kind, bool(is_platform))] = (a + int(amount), c + int(n))
        tax = {k: (int(a), int(n)) for k, a, n in (
            db.query(LedgerEntry.kind, func.coalesce(func.sum(LedgerEntry.amount_cents), 0), func.count(LedgerEntry.id))
            .filter(*in_range, LedgerEntry.user_id == TAX_USER_ID).group_by(LedgerEntry.kind).all())}
        pending = int(db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
                      .filter(LedgerEntry.user_id == TAX_USER_ID, LedgerEntry.created_at < hi).scalar() or 0)
        people, income = db.query(func.count(func.distinct(TaxWithholding.user_id)),
                                  func.coalesce(func.sum(TaxWithholding.income_cents), 0)).filter(
            TaxWithholding.created_at >= lo, TaxWithholding.created_at < hi).one()
        net, release_n = sums.get(("escrow_release", False), (0, 0))
        fee, _fee_n = sums.get(("fee", True), (0, 0))
        rows.append({
            "period": label, "start": lo, "end": hi,
            "gmv_cents": net + fee, "release_count": release_n, "executor_net_cents": net, "fee_cents": fee,
            "dispute_split_cents": sums.get(("dispute_split", False), (0, 0))[0],
            "refund_cents": sums.get(("refund", False), (0, 0))[0],
            "withheld_cents": tax.get("tax_withheld", (0, 0))[0], "withheld_count": tax.get("tax_withheld", (0, 0))[1],
            "withheld_people": int(people), "withheld_income_cents": int(income),
            "remitted_cents": -tax.get("tax_remit", (0, 0))[0], "tax_pending_cents": pending,
        })
    return {"granularity": granularity, "periods": rows, "basis": GMV_TAX_BASIS, "draft_note": GMV_TAX_DRAFT_NOTE}
