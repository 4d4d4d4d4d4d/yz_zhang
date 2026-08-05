"""OPS-012 管理员操作审计：高权限动作（封禁/裁决/结算/提现审批）不可抵赖留痕。"""
import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, bind_payout, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _make_admin(client, phone):
    admin = register(client, phone, "管理员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def test_ban_and_verdict_and_settle_audited(client, requester, worker):
    admin = _make_admin(client, "32000000000")

    # 封禁 → 审计
    victim = register(client, "32000000001", "被封")
    client.post(f"/api/v1/admin/users/{victim['id']}/ban", headers=auth(admin))

    # 裁决 → 审计（同时平台产生佣金余额，供随后结算）
    topup(client, requester, 20000)
    task = publish_task(client, requester, title="审计纠纷单")
    match_and_fund(client, requester, worker, task)
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付质量有争议需仲裁"}, headers=auth(requester)).json()
    client.post(f"/api/v1/disputes/{d['id']}/verdict",
                json={"executor_share_bps": 5000, "reason": "各担一半"}, headers=auth(admin))

    # 平台结算 → 审计
    client.post("/api/v1/admin/platform-finance/settle",
                json={"amount_cents": 100}, headers=auth(admin))

    log = client.get("/api/v1/admin/audit-log", headers=auth(admin)).json()
    actions = {e["action"] for e in log}
    assert {"ban_user", "dispute_verdict", "platform_settle"} <= actions
    # 每条都带 admin_id
    assert all(e["admin_id"] == admin["id"] for e in log)
    ban_entry = next(e for e in log if e["action"] == "ban_user")
    assert ban_entry["target_type"] == "user" and ban_entry["target_id"] == victim["id"]


def test_audit_log_filter_and_admin_only(client, requester):
    admin = _make_admin(client, "32000000010")
    v1 = register(client, "32000000011", "甲")
    v2 = register(client, "32000000012", "乙")
    client.post(f"/api/v1/admin/users/{v1['id']}/ban", headers=auth(admin))
    client.post(f"/api/v1/admin/users/{v2['id']}/ban", headers=auth(admin))
    client.post(f"/api/v1/admin/users/{v1['id']}/unban", headers=auth(admin))

    bans = client.get("/api/v1/admin/audit-log?action=ban_user", headers=auth(admin)).json()
    assert len(bans) == 2 and all(e["action"] == "ban_user" for e in bans)

    # 非管理员不可读审计日志
    assert client.get("/api/v1/admin/audit-log", headers=auth(requester)).status_code == 403


def test_withdraw_approval_audited(client):
    admin = _make_admin(client, "32000000020")
    from app.core.config import settings

    rich = register(client, "32000000021", "有钱人")
    verify_user(client, rich, "富户")
    bind_payout(client, rich, holder="富户")
    topup(client, rich, 20_000_000)
    req_id = client.post("/api/v1/wallet/withdraw",
                         json={"amount_cents": settings.LARGE_WITHDRAW_CENTS},
                         headers=auth(rich)).json()["request_id"]
    client.post(f"/api/v1/wallet/withdraw-requests/{req_id}/approve", headers=auth(admin))

    log = client.get("/api/v1/admin/audit-log?action=withdraw_approve", headers=auth(admin)).json()
    assert len(log) == 1 and log[0]["target_id"] == req_id
