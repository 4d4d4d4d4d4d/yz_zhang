"""ACC-004 密码管理 + TASK-012 报名撤回（业界安全/交易标配）。

密码：改密验旧密码、重置走短信码，两者都吊销全部旧会话（防被盗号后旧 token 续命）。
报名撤回：pending 可撤、撤后可重报；撤回的报名不可被发布者成交（防替人签约）。
"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import publish_task


# ---------- ACC-004 密码 ----------
def test_change_password_revokes_old_sessions(client):
    u = register(client, "23000000001", "改密者")
    old_token = u["token"]

    # 错误旧密码被拒
    r = client.post("/api/v1/auth/change-password",
                    json={"old_password": "wrong-pass", "new_password": "newpass123"},
                    headers=auth(u))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_old_password"

    r = client.post("/api/v1/auth/change-password",
                    json={"old_password": "pass123456", "new_password": "newpass123"},
                    headers=auth(u))
    assert r.status_code == 200
    new_token = r.json()["token"]

    # 旧会话已吊销
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {old_token}"})
    assert r.status_code == 403
    # 新 token 可用；新密码可登录，旧密码不可
    assert client.get("/api/v1/users/me",
                      headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"phone": "23000000001", "password": "newpass123"}).status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"phone": "23000000001", "password": "pass123456"}).status_code == 400


def test_reset_password_via_sms_revokes_sessions(client):
    u = register(client, "23000000002", "忘密者")
    old_token = u["token"]

    # 错误验证码被拒
    r = client.post("/api/v1/auth/reset-password",
                    json={"phone": "23000000002", "sms_code": "000000",
                          "new_password": "resetpass1"})
    assert r.status_code == 400

    r = client.post("/api/v1/auth/reset-password",
                    json={"phone": "23000000002", "sms_code": "123456",
                          "new_password": "resetpass1"})
    assert r.status_code == 200
    # 全部旧会话吊销，需重新登录
    assert client.get("/api/v1/users/me",
                      headers={"Authorization": f"Bearer {old_token}"}).status_code == 403
    assert client.post("/api/v1/auth/login",
                       json={"phone": "23000000002", "password": "resetpass1"}).status_code == 200


# ---------- TASK-012 报名撤回 ----------
def test_withdraw_application_and_reapply(client, requester, worker):
    task = publish_task(client, requester)
    app_id = client.post(f"/api/v1/tasks/{task['id']}/applications", json={},
                         headers=auth(worker)).json()["id"]

    # 他人不能撤别人的报名
    stranger = register(client, "23000000003", "路人")
    r = client.post(f"/api/v1/applications/{app_id}/withdraw", headers=auth(stranger))
    assert r.status_code == 403

    r = client.post(f"/api/v1/applications/{app_id}/withdraw", headers=auth(worker))
    assert r.json()["status"] == "withdrawn"

    # 撤回的报名不可被成交（防替人签约）
    r = client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "application_closed"

    # 撤回后可重新报名，新报名可正常成交
    topup(client, requester, 40000)
    new_id = client.post(f"/api/v1/tasks/{task['id']}/applications", json={},
                         headers=auth(worker)).json()["id"]
    assert new_id != app_id
    r = client.post(f"/api/v1/applications/{new_id}/accept", headers=auth(requester))
    assert r.status_code == 200

    # 已成交的报名不可再撤
    r = client.post(f"/api/v1/applications/{new_id}/withdraw", headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "application_closed"
