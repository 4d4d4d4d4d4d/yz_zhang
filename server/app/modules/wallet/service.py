"""钱包核心操作。所有资金变动必须走这里并落流水（12.A 审计要求）。"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
})

# transfer() 允许的科目前缀（会各自拼出 _in / _out 两条）
TRANSFER_KINDS: frozenset[str] = frozenset(
    {"adjust", "subsidy", "agent_payout", "coop_distribution", "team_spend"})


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
        .filter(WithdrawRequest.user_id == user_id, WithdrawRequest.status == "pending",
                WithdrawRequest.created_at >= day_start)
        .scalar()
    )
    return int(done) + int(pending)


def _send_payout(db: Session, user_id: int, amount: int, ref: str) -> str:
    """VND-013 打款出账：供应商失败直接抛出，由 get_db 整体回滚——
    宁可提现失败重来，也不能出现「账扣了钱没打出去」。"""
    from app.vendors import payment_service
    from app.vendors.base import VendorError

    try:
        return payment_service.send_payout(db, user_id, amount, ref)
    except VendorError as exc:
        raise exc.as_http() from exc


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
    acct.available_cents -= amount
    entry_ref = f"wd-{user_id}-{int(utcnow().timestamp() * 1000)}"
    payout_ref = _send_payout(db, user_id, amount, entry_ref)
    _log(db, user_id, "withdraw", -amount, memo=f"提现打款 {payout_ref}")
    return {"status": "done", "available_cents": acct.available_cents,
            "frozen_cents": acct.frozen_cents, "payout_ref": payout_ref}


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
    lock_wallets(db, req.user_id)  # CONC-012
    acct = get_or_create(db, req.user_id)
    acct.frozen_cents -= req.amount_cents
    if approve:
        payout_ref = _send_payout(db, req.user_id, req.amount_cents, f"wdreq-{req.id}")
        _log(db, req.user_id, "withdraw", -req.amount_cents,
             memo=f"大额提现批准 #{req.id} 打款 {payout_ref}")
        req.status = "approved"
    else:
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
