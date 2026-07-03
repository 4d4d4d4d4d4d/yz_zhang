"""11 法律 / 12 管理后台 / MATCH-004 邀约 / TASK-042 订阅"""
import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def make_admin(client, phone="13300000000"):
    admin = register(client, phone, "管理员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


# ---------- 法律（LAW-001/005） ----------
def test_law001_answer_with_disclaimer(client, requester):
    r = client.post("/api/v1/legal/ask", json={"question": "平台上的电子合约有法律效力吗"}, headers=auth(requester))
    body = r.json()
    assert body["refused"] is False and "民法典" in body["answer"]
    assert "不构成法律意见" in body["disclaimer"]  # 合规底线


def test_law001_refuses_high_risk_and_unknown(client, requester):
    r = client.post("/api/v1/legal/ask", json={"question": "有人威胁我人身安全怎么办"}, headers=auth(requester))
    assert r.json()["refused"] is True and "110" in r.json()["answer"]
    r = client.post("/api/v1/legal/ask", json={"question": "外星法适用吗"}, headers=auth(requester))
    assert r.json()["refused"] is True  # 超范围拒答不编造


def test_law005_evidence_export_with_hash(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    dispute = client.post(
        f"/api/v1/tasks/{task['id']}/disputes", json={"reason": "质量不合格"}, headers=auth(requester)
    ).json()
    r = client.get(f"/api/v1/legal/disputes/{dispute['id']}/evidence-export", headers=auth(worker))
    body = r.json()
    assert body["package"]["task_id"] == task["id"] and len(body["sha256"]) == 64
    # 非当事人不可导出
    outsider = register(client, "13300000009")
    r = client.get(f"/api/v1/legal/disputes/{dispute['id']}/evidence-export", headers=auth(outsider))
    assert r.status_code == 403


# ---------- 管理后台（OPS/RISK） ----------
def test_risk007_report_and_resolve_removes_content(client, requester, worker):
    admin = make_admin(client)
    c = client.post("/api/v1/contents", json={"body": "低俗擦边内容"}, headers=auth(worker)).json()
    r = client.post(
        "/api/v1/reports",
        json={"target_type": "content", "target_id": c["id"], "reason": "低俗"},
        headers=auth(requester),
    )
    report_id = r.json()["id"]
    # 非管理员看不到队列
    assert client.get("/api/v1/admin/reports", headers=auth(requester)).status_code == 403
    queue = client.get("/api/v1/admin/reports", headers=auth(admin)).json()
    assert any(item["id"] == report_id for item in queue)
    client.post(
        f"/api/v1/admin/reports/{report_id}/resolve", json={"action": "remove_content"}, headers=auth(admin)
    )
    r = client.get(f"/api/v1/contents/{c['id']}", headers=auth(requester))
    assert r.status_code == 404  # 已下架


def test_risk006_ban_blocks_all_actions(client, worker):
    admin = make_admin(client)
    client.post(f"/api/v1/admin/users/{worker['id']}/ban", headers=auth(admin))
    r = client.get("/api/v1/users/me", headers=auth(worker))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "account_banned"
    client.post(f"/api/v1/admin/users/{worker['id']}/unban", headers=auth(admin))
    assert client.get("/api/v1/users/me", headers=auth(worker)).status_code == 200


def test_ops007_metrics_north_star(client, requester, worker):
    admin = make_admin(client)
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    m = client.get("/api/v1/admin/metrics", headers=auth(admin)).json()
    assert m["completed_tasks"] == 1 and m["gmv_cents"] == 20000
    assert m["closed_loop_rate"] == 1.0
    assert m["fee_income_cents"] == 1600  # 8%


# ---------- 定向邀约（MATCH-004） ----------
def test_match004_invite_accept_creates_contract(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    r = client.post(
        f"/api/v1/tasks/{task['id']}/invitations",
        json={"user_id": worker["id"], "message": "看过你的案例，来做这单"},
        headers=auth(requester),
    )
    assert r.status_code == 201
    # 被邀请人收到通知
    notes = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any("邀约" in n["title"] for n in notes)
    # 接受 → 直接成交生成合约
    inv = client.get("/api/v1/invitations", headers=auth(worker)).json()[0]
    r = client.post(f"/api/v1/invitations/{inv['id']}/accept", headers=auth(worker))
    assert r.status_code == 200 and r.json()["contract_id"]
    detail = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(worker)).json()
    assert detail["status"] == "matched" and detail["executor_id"] == worker["id"]
    # 重复接受被拒
    r = client.post(f"/api/v1/invitations/{inv['id']}/accept", headers=auth(worker))
    assert r.status_code == 409


def test_match004_decline_and_duplicate_guard(client, requester, worker):
    task = publish_task(client, requester)
    client.post(f"/api/v1/tasks/{task['id']}/invitations", json={"user_id": worker["id"]}, headers=auth(requester))
    r = client.post(f"/api/v1/tasks/{task['id']}/invitations", json={"user_id": worker["id"]}, headers=auth(requester))
    assert r.status_code == 409  # 不能重复邀请
    inv = client.get("/api/v1/invitations", headers=auth(worker)).json()[0]
    r = client.post(f"/api/v1/invitations/{inv['id']}/decline", headers=auth(worker))
    assert r.json()["status"] == "declined"


# ---------- 任务订阅（TASK-042） ----------
def test_task042_subscription_notifies_on_publish(client, requester, worker):
    client.post("/api/v1/subscriptions", json={"category": "保洁", "city": "上海"}, headers=auth(worker))
    # 城市不匹配的订阅者不收
    other = register(client, "13300000010", "北京订阅者")
    client.post("/api/v1/subscriptions", json={"category": "保洁", "city": "北京"}, headers=auth(other))
    publish_task(client, requester, title="新保洁单")
    worker_notes = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any("订阅类目有新任务" == n["title"] for n in worker_notes)
    other_notes = client.get("/api/v1/notifications", headers=auth(other)).json()
    assert all(n["title"] != "订阅类目有新任务" for n in other_notes)
    # 退订后不再通知
    sub = client.get("/api/v1/subscriptions", headers=auth(worker)).json()[0]
    client.delete(f"/api/v1/subscriptions/{sub['id']}", headers=auth(worker))
    publish_task(client, requester, title="又一保洁单")
    worker_notes = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert sum(1 for n in worker_notes if n["title"] == "订阅类目有新任务") == 1
