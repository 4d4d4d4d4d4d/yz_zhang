"""CONC-067 外部调用挪出事务之后，失败与不明结果的语义（113 号 spec）。

把「调供应商」从事务里挪出来不是换个位置那么简单：原来靠「失败就整笔回滚」得到的保证，
现在每一条都要显式地重新给出来。这里一条一条钉住：
- 出款：明确失败 → 解冻、出款单 failed、不记流水；结果不明 → 钱留在冻结、出款单 sending、
  补偿 job 按同一个单号重试成功；每一步之后五条资金不变量都成立；
- 充值：渠道失败后同一个幂等键能真的重试（占键不会卡住 24 小时）；
- 推送：业务回滚了就不推（此前回滚的那笔照样推一条）；提交之后推；投递挂了 drain 补；
- 存管分账：指令在业务提交之后下达；超时没下达的进日终对账；
- 删文件：处置回滚了就不删。
"""
import pytest

from app.core.db import SessionLocal
from app.vendors import registry
from app.vendors.base import VendorError
from tests.conftest import auth, bind_payout, make_admin, money, register, topup, verify_user


def _reconcile_clean():
    from app.modules.risk import service as risk

    with SessionLocal() as db:
        out = risk.reconcile(db)
    assert out.get("ok", not out.get("mismatches")), out


def _payment(monkeypatch, method: str, fn):
    inner = registry.get_provider("payment").unwrapped
    monkeypatch.setattr(inner, method, fn)


@pytest.fixture()
def payer(client):
    u = register(client, "13800180001", "提现人")
    verify_user(client, u, name="张三")
    topup(client, u, 500000)
    bind_payout(client, u)
    return u


def _wallet(client, u):
    return client.get("/api/v1/wallet", headers=auth(u)).json()


def _requests(user_id):
    from app.modules.wallet.models import LedgerEntry, WithdrawRequest

    with SessionLocal() as db:
        reqs = [(r.status, r.amount_cents) for r in db.query(WithdrawRequest).filter_by(user_id=user_id)]
        outs = db.query(LedgerEntry).filter_by(user_id=user_id, kind="withdraw").count()
    return reqs, outs


# ------------------------------------------------------------------ 出款
def test_instant_payout_happy_path_is_unchanged(client, payer):
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=money(auth(payer)))
    assert r.status_code == 200 and r.json()["status"] == "done", r.text
    w = _wallet(client, payer)
    assert w["available_cents"] == 490000 and w["frozen_cents"] == 0
    assert _requests(payer["id"]) == ([("paid", 10000)], 1)
    _reconcile_clean()


def test_a_bank_that_definitely_refused_leaves_the_money_where_it_was(client, payer, monkeypatch):
    def refuse(*a, **k):
        raise VendorError("account_invalid", "收款账户无效", retryable=False)

    _payment(monkeypatch, "create_payout", refuse)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=money(auth(payer)))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "vendor_account_invalid"
    w = _wallet(client, payer)
    assert w["available_cents"] == 500000 and w["frozen_cents"] == 0, "明确失败要解冻退回"
    assert _requests(payer["id"]) == ([("failed", 10000)], 0), "出款单留痕为 failed，不记出账流水"
    _reconcile_clean()


def test_an_unknown_bank_outcome_keeps_the_money_frozen_and_the_job_finishes_it(client, payer, monkeypatch):
    """银行超时 = 不知道打没打。不能当失败退回（那等于让他再提一次），留在冻结、交给补偿。"""
    calls = []

    def timeout(*a, **k):
        calls.append(1)
        raise VendorError("timeout", "银行超时", retryable=True)

    _payment(monkeypatch, "create_payout", timeout)
    key = money(auth(payer))
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=key)
    assert r.status_code == 200 and r.json()["status"] == "processing", r.text
    w = _wallet(client, payer)
    assert w["available_cents"] == 490000 and w["frozen_cents"] == 10000
    assert _requests(payer["id"]) == ([("sending", 10000)], 0)
    _reconcile_clean()
    # 同一个键重放：还是「处理中」，不会再打一次
    again = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=key)
    assert again.json()["status"] == "processing" and len(calls) == 1

    monkeypatch.undo()
    from app.modules.wallet import service as wallet

    with SessionLocal() as db:
        out = wallet.resolve_stuck_payouts(db, older_than_seconds=0)
        db.commit()
    assert out["paid"] == 1
    w = _wallet(client, payer)
    assert w["available_cents"] == 490000 and w["frozen_cents"] == 0
    assert _requests(payer["id"]) == ([("paid", 10000)], 1)
    _reconcile_clean()


def test_the_payout_job_is_scheduled_and_guarded(client):
    from app.core.jobs import JOBS

    assert any(j.path == "/wallet/jobs/resolve-payouts" for j in JOBS)
    assert client.post("/api/v1/wallet/jobs/resolve-payouts").status_code in (401, 403)


def test_reconcile_counts_money_frozen_while_waiting_for_the_second_approver(client, monkeypatch):
    """PAY-042 一审通过、等第二位管理员的那段时间，钱还在冻结里——对账此前只数 pending，会误报。"""
    from app.core.config import settings

    u = register(client, "13800180002", "大额")
    verify_user(client, u, name="张三")
    topup(client, u, 6000000)
    bind_payout(client, u)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 3000000}, headers=money(auth(u)))
    assert r.json()["status"] == "pending_review", r.text
    rid = r.json()["request_id"]
    admin = make_admin(client, "13800180003")
    assert 3000000 > settings.WITHDRAW_DUAL_APPROVAL_CENTS
    first = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    assert first.json()["status"] == "awaiting_second", first.text
    _reconcile_clean()


def test_a_reviewed_payout_the_bank_refuses_goes_back_to_review(client, monkeypatch):
    u = register(client, "13800180004", "人审")
    verify_user(client, u, name="张三")
    topup(client, u, 3000000)
    bind_payout(client, u)
    rid = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1500000},
                      headers=money(auth(u))).json()["request_id"]
    admin = make_admin(client, "13800180005")

    def refuse(*a, **k):
        raise VendorError("account_invalid", "收款账户无效", retryable=False)

    _payment(monkeypatch, "create_payout", refuse)
    r = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    assert r.status_code == 400
    assert _requests(u["id"]) == ([("pending", 1500000)], 0), "回到待审，钱还在冻结，管理员可以再批"
    assert _wallet(client, u)["frozen_cents"] == 1500000
    _reconcile_clean()


# ------------------------------------------------------------------ 充值
def test_a_failed_charge_does_not_lock_the_idempotency_key(client, monkeypatch):
    u = register(client, "13800180006", "充值")
    calls = []

    def flaky(order_no, amount, subject):
        calls.append(order_no)
        if len(calls) == 1:
            raise VendorError("channel_down", "渠道不可用", retryable=False)
        return original(order_no, amount, subject)

    original = registry.get_provider("payment").unwrapped.create_charge
    _payment(monkeypatch, "create_charge", flaky)
    key = money(auth(u))
    first = client.post("/api/v1/wallet/topup", json={"amount_cents": 5000}, headers=key)
    assert first.status_code == 400
    second = client.post("/api/v1/wallet/topup", json={"amount_cents": 5000}, headers=key)
    assert second.status_code == 200, "失败不缓存：同一个键重试要真的再试一次，不能 409 卡 24 小时"
    assert len(calls) == 2
    from app.vendors.models import PaymentOrder

    with SessionLocal() as db:
        assert sorted(o.status for o in db.query(PaymentOrder).filter_by(user_id=u["id"])) == \
            ["failed", "succeeded"], "渠道明确拒绝的订单留痕为 failed，不是永远 pending"
    _reconcile_clean()


# ------------------------------------------------------------------ 推送 / 存管 / 删文件
def _push_spy(monkeypatch):
    sent = []

    class Push:
        name = "spy"
        delivers = True

        def send(self, tokens, title, body, data):
            from app.vendors.base import VendorResult

            sent.append(title)
            return VendorResult(ok=True, data={"delivered": len(tokens)})

    from app.core.txguard import Guarded

    monkeypatch.setitem(registry._instances, "push", Guarded("push", Push()))
    return sent


def _device(user_id):
    from app.modules.notification.models_device import DeviceToken

    with SessionLocal() as db:
        db.add(DeviceToken(user_id=user_id, token=f"tok-{user_id}", platform="ios"))
        db.commit()


def test_push_goes_out_after_commit_and_never_for_a_rolled_back_transaction(client, monkeypatch):
    from app.modules.notification.service import notify

    sent = _push_spy(monkeypatch)
    u = register(client, "13800180007", "收通知")
    _device(u["id"])
    with SessionLocal() as db:
        notify(db, u["id"], "funds", "回滚的到账", "这一笔最后没成")
        assert sent == [], "推送不在业务事务里发"
        db.rollback()
    assert sent == [], "业务回滚了就不推：此前回滚的那笔放款也会推一条「已到账」"
    with SessionLocal() as db:
        notify(db, u["id"], "funds", "真的到账", "这一笔成了")
        db.commit()
    assert sent == ["真的到账"]


def test_a_push_that_never_went_out_is_picked_up_by_drain(client, monkeypatch):
    """业务提交之后、投递之前进程挂了：投递记录停在 deferred，drain 过一阵子补。"""
    from datetime import timedelta

    from app.core import events
    from app.modules.notification.service import notify

    sent = _push_spy(monkeypatch)
    u = register(client, "13800180008", "收通知")
    _device(u["id"])
    monkeypatch.setattr(events, "_deliver_deferred", lambda *a, **k: None)  # 模拟「提交后进程挂了」
    with SessionLocal() as db:
        notify(db, u["id"], "funds", "挂掉之前", "x")
        db.commit()
    assert sent == []
    monkeypatch.undo()
    sent = _push_spy(monkeypatch)
    with SessionLocal() as db:
        for row in db.query(events.EventDelivery).filter_by(status="deferred"):
            row.updated_at = events._utcnow() - timedelta(seconds=events.DEFERRED_GRACE_SECONDS + 5)
        db.commit()
        events.drain(db)
    assert sent == ["挂掉之前"]


def test_after_commit_handlers_must_be_retryable_and_not_critical():
    from app.core.events import subscribe

    with pytest.raises(ValueError):
        subscribe("x.y", lambda db, p: None, retry=False, after_commit=True)
    with pytest.raises(ValueError):
        subscribe("x.y", lambda db, p: None, retry=True, critical=True, after_commit=True)


def test_custody_instructions_go_out_after_commit_and_overdue_ones_are_flagged(client):
    from datetime import timedelta

    from app.modules.account.models import utcnow
    from app.modules.finance.models import SettlementOrder
    from app.modules.finance.service import CUSTODY_OVERDUE_MINUTES, verify_conservation

    with SessionLocal() as db:
        db.add(SettlementOrder(contract_id=1, kind="release", total_cents=0, backend="custody",
                               status="pending", created_at=utcnow() - timedelta(minutes=1)))
        db.add(SettlementOrder(contract_id=2, kind="release", total_cents=0, backend="custody",
                               status="pending", created_at=utcnow() - timedelta(minutes=CUSTODY_OVERDUE_MINUTES + 1)))
        db.commit()
        issues = [b.get("issue") for b in verify_conservation(db)]
    assert issues.count("custody_instruction_overdue") == 1, "刚下单的还在下达途中，不算；超时的算"


def test_a_rolled_back_rejection_does_not_delete_the_file(client, monkeypatch):
    from app.core.events import on_commit

    deleted = []
    with SessionLocal() as db:
        on_commit(db, "x", lambda: deleted.append(1))
        db.rollback()
    assert deleted == []
    with SessionLocal() as db:
        on_commit(db, "x", lambda: deleted.append(1))
        db.commit()
    assert deleted == [1]


def test_an_interrupted_settlement_is_processing_never_a_second_withdrawal(client, payer, monkeypatch):
    """V138 第一版的「一次意图、两次打款」：过了提交点之后的意外如果报错，
    客户端用同一个键重试会变成第二笔提现，而第一笔的出款单还会被补偿 job 打出去。"""
    from app.modules.wallet import service as wallet

    real = wallet._finish_payout
    calls = {"n": 0}

    def boom(db, req, ref):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("结账时撞上并发修改")
        return real(db, req, ref)

    monkeypatch.setattr(wallet, "_finish_payout", boom)
    key = money(auth(payer))
    first = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=key)
    assert first.status_code == 200 and first.json()["status"] == "processing", first.text
    retry = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=key)
    assert retry.json() == first.json(), "同一个键重试回放「处理中」，不是第二笔提现"
    assert _requests(payer["id"]) == ([("sending", 10000)], 0)
    with SessionLocal() as db:
        wallet.resolve_stuck_payouts(db, older_than_seconds=0)
        db.commit()
    assert _requests(payer["id"]) == ([("paid", 10000)], 1), "只打了一次"
    w = _wallet(client, payer)
    assert w["available_cents"] == 490000 and w["frozen_cents"] == 0
    _reconcile_clean()


def test_a_push_queued_inside_a_handlers_savepoint_goes_out_after_the_outer_commit(client, monkeypatch):
    """事件 handler 跑在保存点里，它发的通知也在保存点里排队。SQLAlchemy 的 after_commit
    在保存点释放时也会触发——那时外层事务还开着，新会话看不见投递记录，推送就悄悄丢了。"""
    from app.modules.notification.service import notify

    sent = _push_spy(monkeypatch)
    u = register(client, "13800180009", "收通知")
    _device(u["id"])
    with SessionLocal() as db:
        sp = db.begin_nested()
        notify(db, u["id"], "funds", "保存点里排的", "x")
        sp.commit()
        assert sent == [], "保存点释放不是业务提交"
        db.commit()
    assert sent == ["保存点里排的"]
