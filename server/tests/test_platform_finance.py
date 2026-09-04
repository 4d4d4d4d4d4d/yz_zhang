"""SC-009/OPS-010 平台佣金收入：实收口径 + 结算 + 对账不变量。

批判性发现的真实缺陷：admin/metrics 的 fee_income 按 Σ(released×费率) 估算，
既漏计纠纷/取消场景的佣金（那些不走 released_cents），又有逐笔取整漂移。
本套件钉住：以平台账户实收为唯一事实来源，纠纷佣金计入，结算后守恒仍成立。
"""
import sqlalchemy as sa

from app.core.db import SessionLocal, engine
from app.modules.risk.service import reconcile

from .conftest import auth, register, respond_dispute, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _assert_conserved():
    with SessionLocal() as db:
        r = reconcile(db)
    assert r["ok"], f"资金守恒被打破：{r['mismatches']}"


def _make_admin(client, phone):
    admin = register(client, phone, "财务")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def test_dispute_fee_counted_in_platform_revenue(client, requester, worker):
    """纠纷裁决产生的佣金必须计入平台收入（老公式会漏计）。"""
    admin = _make_admin(client, "27000000000")
    topup(client, requester, 100000)

    # 正常闭环：20000 放款，佣金 1600
    t1 = publish_task(client, requester, budget_cents=20000)
    match_and_fund(client, requester, worker, t1)
    client.post(f"/api/v1/tasks/{t1['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{t1['id']}/accept-delivery", headers=auth(requester))

    # 纠纷裁决：执行者拿 50% → 佣金只对其所得部分收取（老 released×费率 公式漏计此项）
    t2 = publish_task(client, requester, budget_cents=20000)
    match_and_fund(client, requester, worker, t2)
    d = client.post(f"/api/v1/tasks/{t2['id']}/disputes",
                    json={"reason": "交付质量有争议需仲裁"}, headers=auth(requester)).json()
    respond_dispute(client, d["id"], worker)
    client.post(f"/api/v1/disputes/{d['id']}/verdict",
                json={"executor_share_bps": 5000, "reason": "各担一半"}, headers=auth(admin))

    fin = client.get("/api/v1/admin/platform-finance", headers=auth(admin)).json()
    # 佣金 = 1600（正常单）+ 10000×8%（纠纷单执行者所得 10000）= 1600 + 800 = 2400
    assert fin["total_fee_cents"] == 2400
    assert fin["balance_cents"] == 2400 and fin["fee_count"] == 2
    # metrics 已改为实收口径，两者一致
    metrics = client.get("/api/v1/admin/metrics", headers=auth(admin)).json()
    assert metrics["fee_income_cents"] == 2400
    _assert_conserved()


def test_platform_settlement_and_conservation(client, requester, worker):
    admin = _make_admin(client, "27000000010")
    topup(client, requester, 100000)
    t = publish_task(client, requester, budget_cents=50000)
    match_and_fund(client, requester, worker, t)
    client.post(f"/api/v1/tasks/{t['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{t['id']}/accept-delivery", headers=auth(requester))

    fin = client.get("/api/v1/admin/platform-finance", headers=auth(admin)).json()
    assert fin["balance_cents"] == 4000  # 50000×8%
    _assert_conserved()

    # 结算 3000（模拟对公划出）→ 余额减少，全局守恒把结算记为出账
    r = client.post("/api/v1/admin/platform-finance/settle",
                    json={"amount_cents": 3000}, headers=auth(admin))
    assert r.json()["balance_cents"] == 1000
    _assert_conserved()
    fin = client.get("/api/v1/admin/platform-finance", headers=auth(admin)).json()
    assert fin["total_fee_cents"] == 4000 and fin["settled_cents"] == 3000 and fin["balance_cents"] == 1000

    # 超额结算被拒
    r = client.post("/api/v1/admin/platform-finance/settle",
                    json={"amount_cents": 99999}, headers=auth(admin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "insufficient_platform_balance"
    _assert_conserved()


def test_platform_finance_admin_only(client, requester):
    r = client.get("/api/v1/admin/platform-finance", headers=auth(requester))
    assert r.status_code == 403
    r = client.post("/api/v1/admin/platform-finance/settle",
                    json={"amount_cents": 100}, headers=auth(requester))
    assert r.status_code == 403
