"""V20 批判性扫描批次：收藏 / 接单开关 / 新设备提醒 / 对账告警闭环。

- TASK-013 收藏：幂等添加、列表、移除（业界标配的需求侧留存入口）；
- ACC-014 接单开关（滴滴「下线」模式）：关闭后不进推荐、不可被邀约，
  但主动报名不受限（用户自主行为）；
- ACC-007 新设备登录提醒：陌生 UA 登录触发站内通知，已知设备不打扰；
- PAY-008 对账告警闭环：不变量校验失败必须自动开工单+告警，而非仅返回结果。
"""
import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, register, topup, verify_user
from .test_task_flow import publish_task


# ---------- TASK-013 收藏 ----------
def test_bookmark_add_list_remove(client, requester, worker):
    t1 = publish_task(client, requester, title="收藏目标一")
    t2 = publish_task(client, requester, title="收藏目标二")

    client.post(f"/api/v1/tasks/{t1['id']}/bookmark", headers=auth(worker))
    client.post(f"/api/v1/tasks/{t2['id']}/bookmark", headers=auth(worker))
    # 幂等重复收藏
    r = client.post(f"/api/v1/tasks/{t1['id']}/bookmark", headers=auth(worker))
    assert r.json().get("already") is True

    rows = client.get("/api/v1/users/me/bookmarks", headers=auth(worker)).json()
    assert [x["title"] for x in rows] == ["收藏目标二", "收藏目标一"]  # 倒序

    client.delete(f"/api/v1/tasks/{t1['id']}/bookmark", headers=auth(worker))
    rows = client.get("/api/v1/users/me/bookmarks", headers=auth(worker)).json()
    assert len(rows) == 1 and rows[0]["id"] == t2["id"]


# ---------- ACC-014 接单开关 ----------
def test_accepting_orders_off_hides_from_recommend_and_blocks_invite(client, requester, worker):
    client.patch("/api/v1/users/me", json={"skills": ["保洁"]}, headers=auth(worker))
    task = publish_task(client, requester, title="开关测试单")

    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(requester)).json()
    assert any(r["user_id"] == worker["id"] for r in recs)  # 默认在推荐里

    # 下线
    client.patch("/api/v1/users/me", json={"accepting_orders": False}, headers=auth(worker))
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(requester)).json()
    assert not any(r["user_id"] == worker["id"] for r in recs)  # 推荐排除
    r = client.post(f"/api/v1/tasks/{task['id']}/invitations",
                    json={"user_id": worker["id"], "message": "来"}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invitee_unavailable"
    # 主动报名不受限（用户自主）
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 201

    # 重新上线 → 恢复
    client.patch("/api/v1/users/me", json={"accepting_orders": True}, headers=auth(worker))
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(requester)).json()
    assert any(r["user_id"] == worker["id"] for r in recs)


# ---------- ACC-007 新设备提醒 ----------
def test_new_device_login_alerts_known_device_silent(client):
    register(client, "24000000001", "设备哥")

    def unread_alerts(u):
        rows = client.get("/api/v1/notifications", headers=auth(u)).json()
        return [n for n in rows if n["title"] == "新设备登录提醒"]

    # 同设备（TestClient 默认 UA）再登录：不提醒
    r = client.post("/api/v1/auth/login",
                    json={"phone": "24000000001", "password": "pass123456"})
    u = {"id": r.json()["user"]["id"], "token": r.json()["token"]}
    assert unread_alerts(u) == []

    # 陌生设备登录：提醒一次
    r = client.post("/api/v1/auth/login",
                    json={"phone": "24000000001", "password": "pass123456"},
                    headers={"User-Agent": "EvilPhone/9.9"})
    u2 = {"id": r.json()["user"]["id"], "token": r.json()["token"]}
    alerts = unread_alerts(u2)
    assert len(alerts) == 1 and "EvilPhone" in alerts[0]["body"]

    # 该设备已知后再登录：不再重复提醒
    client.post("/api/v1/auth/login",
                json={"phone": "24000000001", "password": "pass123456"},
                headers={"User-Agent": "EvilPhone/9.9"})
    assert len(unread_alerts(u2)) == 1


# ---------- PAY-008 对账告警闭环 ----------
def test_reconcile_mismatch_opens_ticket_and_alerts(client, requester):
    admin = register(client, "24000000010", "风控管理员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})

    topup(client, requester, 10000)
    # 平账时：不开工单
    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin))
    assert r.json()["ok"] is True
    tickets = client.get("/api/v1/admin/tickets", headers=auth(admin)).json()
    assert not any("对账差错" in t["subject"] for t in tickets)

    # 人为制造差错（凭空多出 999 分）
    with engine.begin() as conn:
        conn.execute(sa.text(
            "UPDATE wallet_accounts SET available_cents = available_cents + 999 WHERE user_id = :u"
        ), {"u": requester["id"]})

    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin))
    assert r.json()["ok"] is False
    tickets = client.get("/api/v1/admin/tickets", headers=auth(admin)).json()
    assert any("对账差错" in t["subject"] for t in tickets)  # 自动开差错工单
    notices = client.get("/api/v1/notifications", headers=auth(admin)).json()
    assert any(n["title"] == "对账差错告警" for n in notices)  # 管理员收到告警
