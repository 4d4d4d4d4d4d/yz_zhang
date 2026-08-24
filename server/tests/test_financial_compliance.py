"""FIN-060~065 资金合规验证（25 号 spec）。

两条主线：
1. **分账指令守恒且可审计**——任一笔钱都能回溯到「谁付的 → 指令 → 谁收的」；
2. **分利模式红线在发布环节就拦住**——收益分成、股权对价、保本承诺
   属于涉众性金融，非持牌不得做，不能只写在用户协议里指望没人踩。
"""
import pytest

from app.core.db import SessionLocal
from app.modules.finance import compliance
from app.modules.finance.service import Split

from .conftest import auth, register, respond_dispute, topup
from .test_task_flow import match_and_fund, publish_task


def _settlements(client, user, contract_id):
    r = client.get(f"/api/v1/contracts/{contract_id}/settlements", headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def _contract_id(client, user, task_id):
    return client.get(f"/api/v1/contracts/by-task/{task_id}", headers=auth(user)).json()["id"]


def make_admin(client, phone="13800009001"):
    from app.modules.account.models import User

    admin = register(client, phone, "财务管理员")
    with SessionLocal() as db:
        row = db.get(User, admin["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return admin


# ---------- FIN-010/060 分账指令守恒 ----------
def test_release_produces_conserved_settlement(client, requester, worker):
    """验收放款 → 一条指令，收款方之和等于总额，且能看出谁收了多少。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=50000)
    cid = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    body = _settlements(client, requester, cid)
    orders = body["settlements"]
    assert len(orders) == 1
    order = orders[0]
    assert order["kind"] == "release"
    assert order["total_cents"] == 50000
    assert sum(s["amount_cents"] for s in order["splits"]) == order["total_cents"]

    by_purpose = {s["purpose"]: s for s in order["splits"]}
    fee = 50000 * 800 // 10000
    assert by_purpose["payout"]["payee_user_id"] == worker["id"]
    assert by_purpose["payout"]["amount_cents"] == 50000 - fee
    assert by_purpose["fee"]["payee_user_id"] == 0  # 平台账户
    assert by_purpose["fee"]["amount_cents"] == fee


def test_refund_settlement_on_cancel(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=40000)
    cid = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(worker))

    orders = _settlements(client, requester, cid)["settlements"]
    assert orders and orders[-1]["kind"] == "refund"
    assert sum(s["amount_cents"] for s in orders[-1]["splits"]) == orders[-1]["total_cents"]
    assert orders[-1]["splits"][0]["payee_user_id"] == requester["id"]


def test_verdict_settlement_splits_three_ways(client, requester, worker):
    """FIN-061 反向/分割指令同样守恒：执行方报酬 + 平台佣金 + 退回发布方。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=50000)
    cid = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "成果与约定不符，要求部分退款"}, headers=auth(requester))
    dispute_id = r.json()["id"]
    respond_dispute(client, dispute_id, worker)

    admin = make_admin(client)
    r = client.post(f"/api/v1/disputes/{dispute_id}/verdict",
                    json={"executor_share_bps": 6000, "reason": "部分达标"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text

    order = _settlements(client, requester, cid)["settlements"][-1]
    assert order["kind"] == "verdict"
    assert sum(s["amount_cents"] for s in order["splits"]) == order["total_cents"]
    purposes = {s["purpose"] for s in order["splits"]}
    assert {"payout", "fee", "refund"} <= purposes


def test_milestone_settlements_accumulate(client, requester, worker):
    """分期放款每期一条指令，逐期可审计。"""
    topup(client, requester, 200000)
    task = publish_task(client, requester, budget_cents=60000)
    r = client.post(f"/api/v1/tasks/{task['id']}/applications",
                    json={"message": "我来"}, headers=auth(worker))
    app_id = r.json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/milestones", json={"items": [
        {"title": "一期", "amount_cents": 20000},
        {"title": "二期", "amount_cents": 40000},
    ]}, headers=auth(requester))
    for u in (requester, worker):
        client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(u))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))

    for idx in (1, 2):
        client.post(f"/api/v1/contracts/{cid}/milestones/{idx}/deliver", headers=auth(worker))
        client.post(f"/api/v1/contracts/{cid}/milestones/{idx}/accept", headers=auth(requester))

    orders = _settlements(client, requester, cid)["settlements"]
    milestones = [o for o in orders if o["kind"] == "milestone"]
    assert len(milestones) == 2
    assert sum(o["total_cents"] for o in milestones) == 60000
    for o in orders:
        assert sum(s["amount_cents"] for s in o["splits"]) == o["total_cents"]


def test_settlement_conservation_in_reconcile(client, requester, worker):
    """FIN-060 分账守恒并入日终对账：不守恒说明钱凭空出现或消失。"""
    admin = make_admin(client)
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    assert client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()["ok"] is True
    assert client.get("/api/v1/admin/settlements/verify",
                      headers=auth(admin)).json()["ok"] is True


def test_broken_settlement_is_detected(client, requester, worker):
    """人为篡改一条 split → 对账必须报出来，而不是悄悄放过。"""
    admin = make_admin(client)
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    from app.modules.finance.models import SettlementSplit

    with SessionLocal() as db:
        row = db.query(SettlementSplit).first()
        row.amount_cents += 1  # 凭空多出一分钱
        db.add(row)
        db.commit()

    verify = client.get("/api/v1/admin/settlements/verify", headers=auth(admin)).json()
    assert verify["ok"] is False
    assert verify["problems"][0]["splits_sum"] != verify["problems"][0]["total_cents"]
    recon = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert any(m["invariant"] == "settlement_conservation" for m in recon["mismatches"])


def test_settlement_trail_requires_party_or_admin(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)
    outsider = register(client, "13800009050", "路人")
    assert client.get(f"/api/v1/contracts/{cid}/settlements",
                      headers=auth(outsider)).status_code == 403
    assert client.get(f"/api/v1/contracts/{cid}/settlements",
                      headers=auth(worker)).status_code == 200


def test_split_conservation_enforced_at_build_time():
    """守恒不是「事后发现」，构建指令时金额为负就直接拒绝。"""
    from app.modules.finance import service as finance

    class FakeContract:
        id = 1
        task_id = 1

    with SessionLocal() as db:
        with pytest.raises(Exception) as exc:
            finance.record(db, FakeContract(), "release", [Split(1, -100, "payout")])
        assert exc.value.detail["code"] == "invalid_split_amount"

        with pytest.raises(Exception) as exc:
            finance.record(db, FakeContract(), "not_a_kind", [Split(1, 100, "payout")])
        assert exc.value.detail["code"] == "invalid_settlement_kind"

        with pytest.raises(Exception) as exc:
            finance.record(db, FakeContract(), "release", [Split(1, 100, "bogus")])
        assert exc.value.detail["code"] == "invalid_split_purpose"


# ---------- FIN-062/063 分利模式红线 ----------
def test_pricing_whitelist_rejects_revenue_share(client, requester):
    topup(client, requester, 100000)
    r = client.post("/api/v1/tasks",
                    json={"title": "长期合作项目", "description": "按月推进",
                          "category": "软件开发", "budget_cents": 50000,
                          "city": "杭州", "is_remote": True,
                          "pricing": "revenue_share"},
                    headers=auth(requester))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "pricing_not_allowed"


@pytest.mark.parametrize("text", [
    "项目完成后按利润分红给执行者",
    "参与即赠原始股，上市后回报可观",
    "保本保收益，年化不低于 12%",
    "众筹开发一款 App，募资 50 万",
    "以股权支付部分报酬，干股 5%",
])
def test_finance_offer_blocked_at_publish(client, requester, text):
    """FIN-063 涉众性金融不是「内容不当」，是平台根本不能做的业务。"""
    topup(client, requester, 100000)
    r = client.post("/api/v1/tasks",
                    json={"title": "项目合作", "description": text,
                          "category": "软件开发", "budget_cents": 50000,
                          "city": "杭州", "is_remote": True},
                    headers=auth(requester))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "finance_offer_forbidden"
    # 拒绝理由必须说清楚为什么，否则发布者改个词还会再发一次
    assert "劳务" in r.json()["detail"]["message"]


def test_normal_task_not_falsely_blocked(client, requester):
    """正常劳务任务不能被误杀——风控过严和过松一样是失败。"""
    topup(client, requester, 100000)
    for desc in ("按里程碑付款，共三期", "计件结算，每件 20 元", "投资人对接会务支持"):
        r = client.post("/api/v1/tasks",
                        json={"title": "正常任务", "description": desc,
                              "category": "软件开发", "budget_cents": 50000,
                              "city": "杭州", "is_remote": True},
                        headers=auth(requester))
        assert r.status_code == 201, f"{desc} 被误拦：{r.text}"


def test_invest_only_blocked_with_return_promise():
    """「投资」在正常语境里也会出现，只有与回报承诺连用才构成问题。"""
    assert compliance.scan_finance_terms("投资人对接与会务支持") is None
    assert compliance.scan_finance_terms("投资即有回报") == "投资回报承诺"


def test_contract_terms_state_the_nature(client, requester, worker):
    """FIN-022 定性写进合同才有对抗力，只写在平台规则里没用。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)
    contract = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()
    assert "承揽/服务合同" in contract["terms"]
    assert "不构成任何投资" in contract["terms"]
    assert "不成立劳动关系" in contract["terms"]


# ---------- FIN-064/065 后端切换与沙箱标识 ----------
def test_production_refuses_internal_ledger(monkeypatch):
    """FIN-064 平台自建账本托管资金涉嫌资金池与二清 → 生产环境拒绝启动。

    这不是配置疏忽，是业务不能这样做，所以拦截理由必须写明白。
    """
    from app.vendors import registry

    monkeypatch.setattr(registry.settings, "ENV", "prod")
    monkeypatch.setattr(registry.settings, "LEDGER_BACKEND", "internal")
    with pytest.raises(RuntimeError) as exc:
        registry.startup_check()
    message = str(exc.value)
    assert "LEDGER_BACKEND" in message
    assert "资金池" in message and "二清" in message


def test_sandbox_flag_visible(client):
    """FIN-065 未接存管即沙箱，API 显式标注，避免误以为是真实资金。"""
    body = client.get("/version").json()
    assert body["sandbox"] is True
    assert body["ledger_backend"] == "internal"


def test_custody_backend_requires_provider_support(monkeypatch):
    """切到 custody 但支付供应商没实现分账 → 明确报错，不静默退回内部账本。"""
    from app.vendors import ledger
    from app.vendors.base import VendorError

    monkeypatch.setattr(ledger.settings, "LEDGER_BACKEND", "custody")
    ledger.reset()
    try:
        backend = ledger.get_ledger()
        assert backend.is_custody is True
        assert ledger.is_sandbox() is False
        with SessionLocal() as db:
            with pytest.raises(VendorError) as exc:
                backend.execute(db, type("O", (), {"id": 1})(), [])
        assert exc.value.code == "custody_unsupported"
    finally:
        ledger.reset()
