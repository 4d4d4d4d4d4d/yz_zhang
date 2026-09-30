"""AML-040~047 反洗钱：拆分、快进快出、账户聚集与不得泄露（30 号 spec）。

改造前用探针跑过一遍：同一账号连续提现 5 笔 ¥9,999——

    五笔 ¥9999 提现结果： [(200,'done'), (200,'done'), (200,'done'), (200,'done'), (200,'done')]
    进入人审的笔数： 0

**¥49,995 出账，零人审**，因为门槛判的是「单笔」。把金额减 1 元多点几次
就能绕过，这是最古老最简单的手法（structuring），恰恰是反洗钱监测的头号目标。

除了堵洞，这批还盯一件容易做反的事：**不得泄露**（AML-030 tipping-off）。
《反洗钱法》第五条要求对反洗钱工作信息保密，所以给用户的话必须中性——
写得再对，一句手滑的错误提示就前功尽弃。
"""
import pytest

from app.core.db import SessionLocal
from app.modules.aml.models import SuspiciousActivity

from .conftest import auth, bind_payout, register, topup, verify_user


@pytest.fixture()
def admin(client):
    from app.modules.account.models import User

    user = register(client, "13800050001", "合规官")
    with SessionLocal() as db:
        row = db.get(User, user["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return user


def funded_user(client, phone, name="张三", amount=5000000):
    user = register(client, phone, name)
    verify_user(client, user, name)
    bind_payout(client, user, name)
    topup(client, user, amount)
    return user


def withdraw(client, user, cents):
    return client.post("/api/v1/wallet/withdraw", json={"amount_cents": cents},
                       headers=auth(user))


def flags(user_id=None, pattern=None):
    with SessionLocal() as db:
        q = db.query(SuspiciousActivity)
        if user_id:
            q = q.filter(SuspiciousActivity.user_id == user_id)
        if pattern:
            q = q.filter(SuspiciousActivity.pattern == pattern)
        return q.all()


# ---------- AML-040 拆分不再能绕过人审（探针的反面） ----------
def test_aml040_structuring_no_longer_slips_through(client):
    """五笔 ¥9,999：改造前全部即时出账，现在从第二笔起进人审。"""
    user = funded_user(client, "13900010001")
    statuses = [withdraw(client, user, 999900).json()["status"] for _ in range(5)]

    assert statuses[0] == "done"            # 第一笔累计未达线，正常放行
    assert statuses[1:] == ["pending_review"] * 4
    # 改造前这里是 0
    with SessionLocal() as db:
        from app.modules.wallet.models import WithdrawRequest

        assert db.query(WithdrawRequest).count() == 4


def test_aml010_structuring_pattern_is_identified_with_numbers(client):
    """光转人审不够——要说清「为什么」，否则复核的人无从判断。"""
    user = funded_user(client, "13900010002")
    for _ in range(4):
        withdraw(client, user, 999900)

    rows = flags(user["id"], "structuring")
    assert rows, "拆分形态应被识别"
    detail = rows[0].detail
    assert "笔提现金额在" in detail
    assert "低于单笔人审门槛" in detail
    assert "8000" in detail or "10000" in detail   # 带出具体数值区间


def test_every_held_withdrawal_carries_a_reviewable_reason(client):
    """被扣下的提现必须带着理由——这条是实现过程中补的一个真实缺口。

    最初只有「拆分」和「大额报告线」两种形态会留痕，而单纯因为累计达到
    人审门槛被扣下的提现**什么都不写**。复核的人打开队列看到一堆没有说明的
    条目，只能全部放行：那等于风控没做，还平白让用户等了一天。
    """
    from app.modules.wallet.models import WithdrawRequest

    user = funded_user(client, "13900010030")
    withdraw(client, user, 999900)
    withdraw(client, user, 999900)      # 这一笔仅因累计达线被扣

    with SessionLocal() as db:
        held = db.query(WithdrawRequest).all()
        assert held
        flagged_refs = {
            (r.ref_type, r.ref_id) for r in db.query(SuspiciousActivity).all()
        }
        for req in held:
            assert ("withdraw_request", req.id) in flagged_refs, \
                f"提现 #{req.id} 被扣下却没有任何可复核的理由"


def test_aml001_single_large_withdrawal_still_reviewed(client):
    """原有的单笔门槛不能因为加了累计口径就失效。"""
    user = funded_user(client, "13900010003")
    assert withdraw(client, user, 1500000).json()["status"] == "pending_review"


# ---------- AML-047 不能误伤正常用户 ----------
def test_aml047_ordinary_withdrawals_are_not_held(client):
    """风控做得太紧等于停业：小额提现必须照常即时到账。"""
    user = funded_user(client, "13900010004", amount=200000)
    for _ in range(3):
        r = withdraw(client, user, 20000)      # 每笔 200 元，累计 600 元
        assert r.json()["status"] == "done", r.text
    assert flags(user["id"]) == []


# ---------- AML-030/031 不得泄露（最容易做错的一条） ----------
def test_aml045_user_facing_message_is_neutral(client):
    """提示里不能出现「可疑」「反洗钱」「拆分」——那既违反保密义务，
    也直接教会对方下次怎么规避。
    """
    user = funded_user(client, "13900010005")
    withdraw(client, user, 999900)
    body = withdraw(client, user, 999900).json()

    assert body["status"] == "pending_review"
    assert body["message"] == "该笔提现需人工复核，通常 1 个工作日内处理完成"
    blob = str(body)
    for word in ("可疑", "反洗钱", "拆分", "structuring", "洗钱", "风控"):
        assert word not in blob, f"用户可见响应里泄露了「{word}」"
    # 更不能把触发依据整包回给用户
    assert "reasons" not in body


def test_aml044_suspicious_flags_do_not_leak_into_data_export(client):
    """LAW-032 的导出权在这里让位：可疑记录属反洗钱工作信息，不得泄露。"""
    user = funded_user(client, "13900010006")
    withdraw(client, user, 999900)
    withdraw(client, user, 999900)
    assert flags(user["id"]), "前置条件：这个用户确实已被标记"

    export = client.get("/api/v1/users/me/export", headers=auth(user)).json()
    blob = str(export)
    assert "suspicious" not in blob.lower()
    assert "structuring" not in blob
    assert "可疑" not in blob


def test_aml046_only_admins_can_read_the_suspicious_list(client, requester):
    for path in ("/api/v1/admin/aml/activities", "/api/v1/admin/aml/stats"):
        assert client.get(path, headers=auth(requester)).status_code == 403
        assert client.get(path).status_code == 403


# ---------- AML-011 快进快出 ----------
def test_aml042_passthrough_is_detected(client):
    """充值后原样提现、中间没有任何成交——平台被当成了通道。"""
    user = register(client, "13900010007", "过账")
    verify_user(client, user, "过账")
    bind_payout(client, user, "过账")
    topup(client, user, 500000)
    withdraw(client, user, 500000)

    rows = flags(user["id"], "passthrough")
    assert rows, "快进快出应被识别"
    assert "无任何任务收入" in rows[0].detail


def test_passthrough_not_flagged_when_the_money_was_earned(client, requester, worker):
    """钱是挣来的就不是过账——有真实成交的提现不该被标记。"""
    from .test_task_flow import match_and_fund, publish_task

    topup(client, requester, 200000)
    task = publish_task(client, requester, budget_cents=100000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    bind_payout(client, worker, "李四")
    r = withdraw(client, worker, 90000)
    assert r.json()["status"] == "done", r.text
    assert flags(worker["id"], "passthrough") == []


# ---------- AML-013 收款账户聚集 ----------
def test_aml043_shared_payout_account_is_flagged_but_not_blocked(client):
    """十个实名账号把钱打到同一张卡，是最朴素的资金归集。

    但只标记不拦截：夫妻共用一张卡、帮父母代收都是真实场景，
    硬拦截会误伤他们，交给人复核才分得清。
    """
    card = "6222020000999888"
    for i, phone in enumerate(("13900010011", "13900010012")):
        user = register(client, phone, f"用户{i}")
        verify_user(client, user, f"用户{i}")
        r = client.put("/api/v1/wallet/payout-account",
                       json={"kind": "bank", "account_no": card,
                             "holder_name": f"用户{i}"}, headers=auth(user))
        assert r.status_code == 200, r.text     # 不拦截

    rows = flags(pattern="account_clustering")
    assert len(rows) == 1                        # 第二个绑定时才发现聚集
    assert "2 个账号" in rows[0].detail


# ---------- AML-020~022 复核流程 ----------
def test_compliance_officer_reviews_and_records_the_conclusion(client, admin):
    user = funded_user(client, "13900010008")
    withdraw(client, user, 999900)
    withdraw(client, user, 999900)

    listing = client.get("/api/v1/admin/aml/activities", headers=auth(admin)).json()
    assert listing["items"]
    assert "不得向客户或其他无关人员泄露" in listing["note"]
    # 平台不自动报送——这句必须写在明面上
    assert "不自动对外报送" in listing["note"]

    first = listing["items"][0]
    assert first["pattern_label"]                # 管理端才展开形态说明
    r = client.post(f"/api/v1/admin/aml/activities/{first['id']}/review",
                    json={"decision": "to_report", "note": "已核实，报合规官"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "to_report"

    stats = client.get("/api/v1/admin/aml/stats", headers=auth(admin)).json()
    assert stats["by_status"].get("to_report") == 1


def test_review_decision_is_validated(client, admin):
    user = funded_user(client, "13900010009")
    withdraw(client, user, 999900)
    withdraw(client, user, 999900)
    row_id = client.get("/api/v1/admin/aml/activities",
                        headers=auth(admin)).json()["items"][0]["id"]
    r = client.post(f"/api/v1/admin/aml/activities/{row_id}/review",
                    json={"decision": "ignore"}, headers=auth(admin))
    assert r.status_code == 422        # pattern 校验在 pydantic 层就拦下


def test_flags_are_not_duplicated_for_the_same_trigger(client):
    """同一主体+形态+关联对象只记一条，否则复核队列会被同一件事刷屏。"""
    user = funded_user(client, "13900010010")
    withdraw(client, user, 999900)
    withdraw(client, user, 999900)
    rows = flags(user["id"], "structuring")
    ids = {(r.ref_type, r.ref_id) for r in rows}
    assert len(rows) == len(ids)


# ---------- AML-003 阈值判定在锁内 ----------
def test_aml041_concurrent_withdrawals_cannot_dodge_the_cumulative_threshold(client):
    """并发提现各自读到「还没超」再分别放行，和拆分是同一个洞的两种姿势。"""
    import threading

    user = funded_user(client, "13900010020")
    results = []
    lock = threading.Lock()

    def one():
        r = withdraw(client, user, 999900)
        with lock:
            results.append(r.json().get("status"))

    threads = [threading.Thread(target=one) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 至多一笔能在累计达线前即时出账，其余必须转人审
    assert results.count("done") <= 1, results
    assert len(results) == 4
