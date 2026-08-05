"""OPS-013 封禁影响面：爆炸半径可见 + 对手方被通知 + 托管资金有出路。

封禁此前是「盲拍开关」：管理员看不到在途合约与涉险托管，对手方也无人告知——
被封用户永远无法交付/验收，对方的托管资金被无限期困住。
"""
import sqlalchemy as sa

from app.core.db import SessionLocal, engine
from app.modules.risk.service import reconcile

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _assert_conserved():
    with SessionLocal() as db:
        r = reconcile(db)
    assert r["ok"], f"资金守恒被打破：{r['mismatches']}"


def _make_admin(client, phone):
    admin = register(client, phone, "管理员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def test_ban_impact_preview_and_response(client, requester, worker):
    admin = _make_admin(client, "33000000000")
    topup(client, requester, 40000)
    task = publish_task(client, requester, title="封禁影响单", budget_cents=20000)
    match_and_fund(client, requester, worker, task)

    # 预览：不产生副作用，能看到在途合约与涉险托管
    pre = client.get(f"/api/v1/admin/users/{worker['id']}/ban-impact", headers=auth(admin)).json()
    assert pre["in_flight_count"] == 1
    assert pre["escrow_at_risk_cents"] == 20000
    assert pre["in_flight_contracts"][0]["counterparty_id"] == requester["id"]
    # 预览不封禁
    assert client.get("/api/v1/users/me", headers=auth(worker)).status_code == 200

    # 封禁：响应带影响面
    r = client.post(f"/api/v1/admin/users/{worker['id']}/ban", headers=auth(admin))
    assert r.json()["impact"]["in_flight_count"] == 1
    # 审计留下涉险金额
    log = client.get("/api/v1/admin/audit-log?action=ban_user", headers=auth(admin)).json()
    assert "20000" in log[0]["detail"]


def test_counterparty_notified_and_can_recover_escrow(client, requester, worker):
    admin = _make_admin(client, "33000000010")
    topup(client, requester, 40000)
    task = publish_task(client, requester, title="对手方自救单", budget_cents=20000)
    match_and_fund(client, requester, worker, task)

    client.post(f"/api/v1/admin/users/{worker['id']}/ban", headers=auth(admin))

    # 对手方收到封禁通知
    notices = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any("已被封禁" in n["title"] for n in notices)

    # 被封用户无法操作（登录态即被拒）
    assert client.get("/api/v1/users/me", headers=auth(worker)).status_code == 403

    # 关键：对手方仍可取消任务，托管资金不被困死
    r = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(requester))
    assert r.status_code == 200
    assert client.get("/api/v1/wallet", headers=auth(requester)).json()["escrow_cents"] == 0
    _assert_conserved()


def test_impact_zero_for_clean_user_and_admin_only(client, requester):
    admin = _make_admin(client, "33000000020")
    clean = register(client, "33000000021", "干净用户")
    impact = client.get(f"/api/v1/admin/users/{clean['id']}/ban-impact", headers=auth(admin)).json()
    assert impact["in_flight_count"] == 0 and impact["escrow_at_risk_cents"] == 0

    # 非管理员不可预览
    assert client.get(f"/api/v1/admin/users/{clean['id']}/ban-impact",
                      headers=auth(requester)).status_code == 403
