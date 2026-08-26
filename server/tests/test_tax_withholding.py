"""TAX-040~047 个税代扣代缴（29 号 spec）。

改造前的事实：`release()` 只有两个收款方——执行者和平台。平台向自然人
支付报酬却一分税没扣、没有任何完税记录。《个人所得税法》第九条
「以支付所得的单位或者个人为扣缴义务人」，《税收征收管理法》第六十九条
对应扣未扣处**应扣未扣税款 50% 至 3 倍的罚款**。

这批测试盯三件事：
1. 四条通向执行者钱包的路（整体/分期/裁决/取消补偿）**一条都不能漏**；
2. 代扣的钱**不与平台收入混同**，且五条不变量全成立；
3. 平台出具的文件**措辞准确**，不冒充税务机关文书。
"""
import pytest

from app.core.db import SessionLocal
from app.modules.tax import service as tax
from app.vendors import registry
from app.vendors.tax import CommissionedCollectionTax, LaborIncomeTax

from .conftest import JOB_HEADERS, auth, register, topup
from .test_task_flow import match_and_fund, publish_task


@pytest.fixture()
def withholding(monkeypatch):
    """切到「平台代扣 + 劳务报酬预扣预缴」。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "TAX_MODE", "withholding")
    monkeypatch.setattr(settings, "TAX_PROVIDER", "labor_income")
    registry.reset()
    yield
    registry.reset()


@pytest.fixture()
def admin(client):
    from app.modules.account.models import User

    user = register(client, "13800040001", "财务")
    with SessionLocal() as db:
        row = db.get(User, user["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return user


def run_loop(client, requester, worker, budget=1000000):
    topup(client, requester, budget * 2)
    task = publish_task(client, requester, budget_cents=budget)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    assert r.status_code == 200, r.text
    return task


def reconcile(client):
    r = client.post("/api/v1/admin/jobs/reconcile", headers=JOB_HEADERS)
    if r.status_code == 404:
        from app.modules.risk import service as risk

        with SessionLocal() as db:
            return risk.reconcile(db)
    return r.json()


# ---------- TAX-042 劳务报酬预扣预缴累进表 ----------
@pytest.mark.parametrize("income_yuan,expected_tax_yuan", [
    (500, 0),        # 500 - 800 < 0 → 应纳税所得额为 0
    (800, 0),        # 恰好减除完
    (2000, 240),     # (2000-800)*20%
    (4000, 640),     # (4000-800)*20%，四千分界线上仍按定额减除
    (5000, 800),     # 5000*80%=4000 → *20%
    (30000, 5200),   # 30000*80%=24000 → *30% - 2000
    (100000, 25000),  # 100000*80%=80000 → *40% - 7000
])
def test_tax042_labor_income_brackets(income_yuan, expected_tax_yuan):
    result = LaborIncomeTax().assess(income_yuan * 100, {})
    assert result.withheld_cents == expected_tax_yuan * 100, result.note
    assert result.rule == "labor_income"


def test_tax042_bracket_boundary_is_not_off_by_one():
    """四千元分界：4000 用定额 800，4000.01 起改按 20% 减除。

    这类分界最容易写反（`<` 写成 `<=`），而写反的后果是每一笔
    四千元上下的报酬都扣错税——量大且难被发现。
    """
    below = LaborIncomeTax().assess(400000, {})
    above = LaborIncomeTax().assess(400100, {})
    assert below.taxable_cents == 400000 - 80000
    assert above.taxable_cents == 400100 * 80 // 100


def test_commissioned_collection_uses_configured_rate():
    result = CommissionedCollectionTax(rate_bps=100).assess(1000000, {})
    assert result.withheld_cents == 10000          # 1%
    assert "委托代征协议" in result.note            # 前提必须写明


# ---------- TAX-040/041 闭环与不变量 ----------
def test_tax040_payout_is_split_three_ways(client, requester, worker, withholding):
    """执行者实收 = 总额 − 佣金 − 税款，且三方分账守恒。"""
    from app.modules.finance.models import SettlementOrder, SettlementSplit

    task = run_loop(client, requester, worker, budget=1000000)  # 1 万元

    gross, fee = 1000000, 80000                    # 8% 佣金
    net = gross - fee                              # 920000 → 计税基数 736000
    expected_tax = LaborIncomeTax().assess(net, {}).withheld_cents
    assert expected_tax > 0

    wallet = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert wallet["available_cents"] == net - expected_tax

    with SessionLocal() as db:
        order = db.query(SettlementOrder).filter(SettlementOrder.kind == "release").one()
        splits = db.query(SettlementSplit).filter(
            SettlementSplit.order_id == order.id
        ).all()
        by_purpose = {s.purpose: s.amount_cents for s in splits}
        assert by_purpose == {"payout": net - expected_tax, "fee": fee, "tax": expected_tax}
        assert sum(by_purpose.values()) == gross          # 分账守恒
        assert tax.account_balance(db) == expected_tax
    assert task["id"]


def test_tax041_all_five_invariants_hold(client, requester, worker, withholding):
    run_loop(client, requester, worker, budget=1000000)
    from app.modules.risk import service as risk

    with SessionLocal() as db:
        result = risk.reconcile(db)
    assert result["mismatches"] == [], result


def test_tax012_withheld_money_is_not_mixed_into_platform_income(
    client, requester, worker, withholding, admin,
):
    """代扣的钱不是平台收入——混进佣金账户，缴库时才发现钱被当成收入结算走了。"""
    run_loop(client, requester, worker, budget=1000000)
    fee = 80000

    finance = client.get("/api/v1/admin/platform-finance", headers=auth(admin)).json()
    assert finance["total_fee_cents"] == fee       # 平台收入只有佣金，不含税款
    assert finance["balance_cents"] == fee

    with SessionLocal() as db:
        assert tax.account_balance(db) == tax.expected_balance(db)
        assert tax.account_balance(db) > 0


def test_executor_ledger_shows_income_then_withholding(
    client, requester, worker, withholding,
):
    """流水要如实反映「他挣了多少、被扣了多少」，按净额直接入账会让人看不到被扣过税。"""
    run_loop(client, requester, worker, budget=1000000)
    entries = client.get("/api/v1/wallet/ledger", headers=auth(worker)).json()
    kinds = [e["kind"] for e in entries]
    assert "escrow_release" in kinds
    assert "tax_withheld" in kinds
    withheld = next(e for e in entries if e["kind"] == "tax_withheld")
    assert withheld["amount_cents"] < 0            # 从执行者账上扣走


# ---------- TAX-047 别的放款路径也要扣 ----------
def test_tax047_milestone_release_also_withholds(client, requester, worker, withholding):
    """只改整体放款，会让所有分期合约悄悄免税——这是本批次最容易漏的路径。"""
    from .test_contract_v1 import _matched_contract, _sign_and_fund

    # 金额要够大：劳务报酬每次收入 ≤4000 元先减除 800 元，
    # 用小额里程碑跑这个用例会「通过」得莫名其妙——那是减除额吃掉了全部收入，
    # 不是代扣逻辑生效了
    contract_id, _ = _matched_contract(client, requester, worker, budget=1000000)
    client.post(f"/api/v1/contracts/{contract_id}/milestones",
                json={"items": [{"title": "首期", "amount_cents": 400000},
                                {"title": "尾期", "amount_cents": 600000}]},
                headers=auth(requester))
    _sign_and_fund(client, requester, worker, contract_id)
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept",
                    headers=auth(requester))
    assert r.status_code == 200, r.text

    with SessionLocal() as db:
        rows = db.query(tax.TaxWithholding).all()
        assert len(rows) == 1
        assert rows[0].settlement_kind == "milestone"
        assert rows[0].withheld_cents > 0
        # 分期的计税基数是这一期的净额，不是整个合约
        assert rows[0].income_cents == 400000 - 400000 * 800 // 10000


def test_verdict_execution_also_withholds(client, requester, worker, withholding, admin):
    """裁决执行同样是向执行者付款，同样要扣。"""
    from app.modules.contract import service as contract_service
    from app.modules.contract.models import Contract

    topup(client, requester, 2000000)
    task = publish_task(client, requester, budget_cents=1000000)
    contract_id = match_and_fund(client, requester, worker, task)
    with SessionLocal() as db:
        contract = db.get(Contract, contract_id)
        contract_service.execute_verdict(db, contract, 7000)
        db.commit()
        rows = db.query(tax.TaxWithholding).all()
        assert len(rows) == 1
        assert rows[0].settlement_kind == "verdict"
        assert rows[0].withheld_cents > 0
    assert task["id"]


# ---------- TAX-043 向后兼容 ----------
def test_tax043_none_mode_behaves_exactly_as_before(client, requester, worker):
    """默认 none 模式：不扣税、两方分账——向后兼容不能靠嘴说。"""
    from app.modules.finance.models import SettlementOrder, SettlementSplit

    run_loop(client, requester, worker, budget=1000000)
    wallet = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert wallet["available_cents"] == 1000000 - 80000

    with SessionLocal() as db:
        order = db.query(SettlementOrder).filter(SettlementOrder.kind == "release").one()
        purposes = {
            s.purpose for s in db.query(SettlementSplit).filter(
                SettlementSplit.order_id == order.id
            )
        }
        assert purposes == {"payout", "fee"}
        assert db.query(tax.TaxWithholding).count() == 0
        assert tax.account_balance(db) == 0


def test_self_declared_mode_does_not_withhold(client, requester, worker, monkeypatch):
    """执行方自行申报开票时平台不扣——但这与「没人想过这件事」是两回事。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "TAX_MODE", "self_declared")
    registry.reset()
    run_loop(client, requester, worker, budget=1000000)
    with SessionLocal() as db:
        assert db.query(tax.TaxWithholding).count() == 0
    registry.reset()


# ---------- TAX-044 上线红线 ----------
def test_tax044_production_refuses_to_start_without_a_tax_decision(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "prod")
    monkeypatch.setattr(settings, "TAX_MODE", "none")
    with pytest.raises(RuntimeError) as exc:
        registry.startup_check()
    assert "PLATFORM_TAX_MODE" in str(exc.value)
    assert "扣缴义务人" in str(exc.value)


def test_declaring_withholding_without_a_rule_is_also_refused(monkeypatch):
    """声明了要代扣却没配规则，等于没扣——这种「配了一半」比没配更危险。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "prod")
    monkeypatch.setattr(settings, "TAX_MODE", "withholding")
    monkeypatch.setattr(settings, "TAX_PROVIDER", "none")
    with pytest.raises(RuntimeError) as exc:
        registry.startup_check()
    assert "PLATFORM_TAX_PROVIDER=none" in str(exc.value)


def test_self_declared_passes_the_gate(monkeypatch):
    """允许选择不扣，只要是**显式**选择。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "prod")
    monkeypatch.setattr(settings, "TAX_MODE", "self_declared")
    try:
        registry.startup_check()
    except RuntimeError as exc:
        assert "PLATFORM_TAX_MODE" not in str(exc)  # 别的项没配是另一回事


# ---------- TAX-045 缴库 ----------
def test_tax045_remit_zeroes_the_account_and_is_not_double_counted(
    client, requester, worker, withholding,
):
    run_loop(client, requester, worker, budget=1000000)
    with SessionLocal() as db:
        before = tax.account_balance(db)
    assert before > 0

    first = client.post("/api/v1/finance/jobs/remit-tax", headers=JOB_HEADERS).json()
    assert first["remitted_cents"] == before
    second = client.post("/api/v1/finance/jobs/remit-tax", headers=JOB_HEADERS).json()
    assert second["remitted_cents"] == 0

    from app.modules.risk import service as risk

    with SessionLocal() as db:
        assert tax.account_balance(db) == 0
        assert tax.expected_balance(db) == 0
        # 缴库把钱划出了系统，全局守恒必须把它算进去，否则每缴一次库就误报一次
        assert risk.reconcile(db)["mismatches"] == []


def test_remit_requires_job_token(client):
    assert client.post("/api/v1/finance/jobs/remit-tax").status_code == 403


# ---------- TAX-021/046 代扣明细的措辞 ----------
def test_tax046_executor_sees_detail_and_it_does_not_claim_to_be_a_tax_certificate(
    client, requester, worker, withholding,
):
    run_loop(client, requester, worker, budget=1000000)
    body = client.get("/api/v1/finance/my-tax", headers=auth(worker)).json()

    assert body["mode"] == "withholding"
    assert len(body["items"]) == 1
    assert body["items"][0]["withheld_cents"] > 0
    assert body["yearly"][0]["count"] == 1
    # 措辞：预扣预缴不是完税，让用户以为能直接抵扣是在帮他犯错
    assert "不是税务机关的完税证明" in body["disclaimer"]
    assert "汇算清缴" in body["disclaimer"]
    assert "预扣预缴" in body["items"][0]["note"]


def test_tax_ledger_requires_admin(client, requester, admin, withholding):
    assert client.get("/api/v1/finance/tax-ledger",
                      headers=auth(requester)).status_code == 403
    body = client.get("/api/v1/finance/tax-ledger", headers=auth(admin)).json()
    assert body["mode"] == "withholding"
    assert body["provider"] == "labor_income"


# ---------- TAX-022 平台服务费发票 ----------
def test_tax022_invoice_covers_only_the_platform_fee(client, requester, worker):
    """平台没有为劳务报酬开票的资格，含糊其辞地开全额发票是虚开，不是服务。"""
    run_loop(client, requester, worker, budget=1000000)
    r = client.post("/api/v1/finance/invoices",
                    json={"contract_id": 1, "title": "某某科技有限公司",
                          "tax_no": "91110000000000000X"}, headers=auth(requester))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["amount_cents"] == 80000          # 只有佣金，不是 1000000
    assert "不含执行方劳务报酬" in body["scope_note"] or "仅覆盖平台服务费" in body["scope_note"]


def test_invoice_only_for_the_paying_party_and_only_once(client, requester, worker):
    run_loop(client, requester, worker, budget=1000000)
    payload = {"contract_id": 1, "title": "某某科技有限公司"}
    assert client.post("/api/v1/finance/invoices", json=payload,
                       headers=auth(worker)).status_code == 403
    assert client.post("/api/v1/finance/invoices", json=payload,
                       headers=auth(requester)).status_code == 201
    dup = client.post("/api/v1/finance/invoices", json=payload, headers=auth(requester))
    assert dup.status_code == 400
    assert dup.json()["detail"]["code"] == "already_requested"


def test_invoice_rejected_before_settlement(client, requester, worker):
    topup(client, requester, 2000000)
    task = publish_task(client, requester, budget_cents=1000000)
    match_and_fund(client, requester, worker, task)
    r = client.post("/api/v1/finance/invoices",
                    json={"contract_id": 1, "title": "某某科技有限公司"},
                    headers=auth(requester))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "not_settled"
