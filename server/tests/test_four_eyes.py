"""DSP-030 / PAY-042 一个人不能把不可逆的钱决定做完（74 号 spec）。

探针：同一个管理员，先做一审处理决定（执行方分成 50%），
再受理并裁决自己的申诉（改成 90%）——**钱跟着二审动了**。

而 V82 的豁免表里这条规则是被明确写下来的：

    "/disputes/{x}/appeal-verdict": "二审裁决也由平台仲裁岗做，且必须与一审不是同一个人"

这是 V96 那件事的第二次：**豁免表的理由里写着一个承诺，而没有任何东西
核对它**。上次承诺的是「在管理后台做」（后台里没有），
这次承诺的是一条控制规则（代码里没有实现）。
"""
from app.core.config import settings
from app.core.db import SessionLocal
from tests.conftest import auth, make_admin, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task


def _disputed(client, requester, phone: str):
    """造一个「已答辩、可裁决」的纠纷。

    两造兼听（V61）是既有规则且是对的：被诉方没答辩且答辩期未过时不可裁决。
    所以这里先让被诉方说话。
    """
    worker = register(client, phone, "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付不符约定"}, headers=auth(requester)).json()
    client.post(f"/api/v1/disputes/{d['id']}/statements",
                json={"content": "我已按约定交付，附证据"}, headers=auth(worker))
    return worker, task, d


# ------------------------------------------------- DSP-030 二审必须换人
def test_dsp030_original_arbiter_cannot_hear_the_appeal(client, requester):
    """申诉的全部意义在于**换一个人再看一遍**。"""
    _worker, _task, d = _disputed(client, requester, "13800090001")
    admin = make_admin(client, "13800090009")
    assert client.post(f"/api/v1/disputes/{d['id']}/verdict",
                       json={"executor_share_bps": 5000, "reason": "一审：各担一半"},
                       headers=auth(admin)).status_code == 200
    assert client.post(f"/api/v1/disputes/{d['id']}/appeal",
                       headers=auth(requester)).status_code == 200

    r = client.post(f"/api/v1/disputes/{d['id']}/appeal-verdict",
                    json={"executor_share_bps": 9000, "reason": "二审：还是我"},
                    headers=auth(admin))
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "same_arbiter"
    # 拒绝理由要说清「需要第二个人」，别让运营以为是权限不够
    assert "第二个人" in r.json()["detail"]["message"]


def test_dsp030_a_second_admin_can_review_and_money_follows(client, requester):
    """换个人就能正常复核，且差额划转与原逻辑一致。"""
    worker, task, d = _disputed(client, requester, "13800090010")
    first = make_admin(client, "13800090018")
    second = make_admin(client, "13800090019")
    client.post(f"/api/v1/disputes/{d['id']}/verdict",
                json={"executor_share_bps": 5000, "reason": "一审：各担一半"},
                headers=auth(first))
    client.post(f"/api/v1/disputes/{d['id']}/appeal", headers=auth(requester))

    before = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    r = client.post(f"/api/v1/disputes/{d['id']}/appeal-verdict",
                    json={"executor_share_bps": 9000, "reason": "二审：证据充分，改判九成"},
                    headers=auth(second))
    assert r.status_code == 200, r.text
    after = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert after > before, "复核提高了分成，钱却没跟着动"

    with SessionLocal() as db:
        from app.modules.dispute.models import Dispute

        row = db.get(Dispute, d["id"])
        assert row.arbiter_id == second["id"], "最终仲裁人应记为复核的那个人"
    # 资金不变量不因纠正性划转而破
    assert client.post("/api/v1/admin/jobs/reconcile",
                       headers=auth(second)).json()["ok"] is True


# ------------------------------------------------- PAY-042 大额出款双人确认
def _big_withdraw(client, phone: str, admin_phone: str, amount: int | None = None):
    amount = amount if amount is not None else settings.WITHDRAW_DUAL_APPROVAL_CENTS + 100000
    u = register(client, phone, "提现的人")
    verify_user(client, u, name="提现")
    topup(client, u, amount + 1000000)
    client.put("/api/v1/wallet/payout-account",
               json={"kind": "bank", "account_no": f"6222{phone[-8:]}11", "holder_name": "提现"},
               headers=auth(u))
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": amount}, headers=auth(u))
    assert r.status_code == 200, r.text
    return u, make_admin(client, admin_phone), r.json()["request_id"], amount


def test_pay042_first_approval_does_not_move_money(client):
    """第一次批准只记意见——**钱一分不动**。"""
    u, admin, rid, amount = _big_withdraw(client, "13800090020", "13800090029")
    before = client.get("/api/v1/wallet", headers=auth(u)).json()

    r = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "awaiting_second"

    after = client.get("/api/v1/wallet", headers=auth(u)).json()
    assert after["frozen_cents"] == before["frozen_cents"], "第一次批准就把钱动了"
    assert after["available_cents"] == before["available_cents"]


def test_pay042_same_admin_cannot_confirm_his_own_approval(client):
    """同一个人点两次，等于没有这条规则。"""
    _u, admin, rid, _amount = _big_withdraw(client, "13800090030", "13800090039")
    client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))

    r = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "same_approver"
    # 门槛数字取自配置（V61/V90：文案里的数字不许是字面量）
    assert f"{settings.WITHDRAW_DUAL_APPROVAL_CENTS / 100:.2f}" in r.json()["detail"]["message"]


def test_pay042_second_admin_confirms_and_money_goes_out(client):
    _u, admin, rid, amount = _big_withdraw(client, "13800090040", "13800090049")
    client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    second = make_admin(client, "13800090048")

    r = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(second))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    w = client.get("/api/v1/wallet", headers=auth(_u)).json()
    assert w["frozen_cents"] == 0, "二次确认后钱应该已划出冻结"


def test_pay042_threshold_is_configurable_and_small_amounts_stay_one_step(client, monkeypatch):
    """门槛以下一人批准即放款——**现状不变**。

    新规则只针对大额：把每一笔都做成双人，运营会绕过它（或者干脆不处理），
    那比没有这条规则更糟。
    """
    # 同一笔金额：按默认门槛要两个人，把门槛调高后只要一个人。
    # 金额仍要低于单日提现限额（那是另一条既有规则，不该被这条测试撞上）。
    amount = settings.WITHDRAW_DUAL_APPROVAL_CENTS + 100000
    monkeypatch.setattr(settings, "WITHDRAW_DUAL_APPROVAL_CENTS", amount + 1)
    u, admin, rid, _amount = _big_withdraw(client, "13800090050", "13800090059", amount)
    r = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    assert r.json()["status"] == "approved", "门槛以下不该要第二个人"
    assert client.get("/api/v1/wallet", headers=auth(u)).json()["frozen_cents"] == 0


def test_pay042_rejection_still_takes_one_person(client):
    """驳回是**可逆**的（钱退回可用余额），不必两个人。

    把拒绝也做成双人只会让积压更久，而积压本身就是用户的钱被冻着。
    """
    u, admin, rid, amount = _big_withdraw(client, "13800090060", "13800090069")
    r = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/reject", headers=auth(admin))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    assert client.get("/api/v1/wallet", headers=auth(u)).json()["available_cents"] >= amount


def test_pay042_queue_tells_the_second_reviewer_who_gave_the_first_opinion(client):
    """第二个人必须知道自己在确认谁的意见——也才看得出这是不是自己刚批的那笔。"""
    _u, admin, rid, _amount = _big_withdraw(client, "13800090070", "13800090079")
    client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))

    rows = client.get("/api/v1/wallet/withdraw-requests?status=awaiting_second",
                      headers=auth(admin)).json()
    assert rows, "等二次确认的申请在队列里查不到——那它就等于消失了"
    assert rows[0]["first_approved_by"] == admin["id"]
