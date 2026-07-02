"""02 账户与信用：ACC-001/002/010/011/020, CRED-001/006"""
from .conftest import auth, register, verify_user


def test_acc001_register_and_sms_code(client):
    # 验证码错误被拒
    r = client.post(
        "/api/v1/auth/register",
        json={"phone": "13900000001", "password": "pass123456", "sms_code": "000000"},
    )
    assert r.status_code == 400
    user = register(client, "13900000001", "小明")
    assert user["id"] > 0
    # 重复注册冲突
    r = client.post(
        "/api/v1/auth/register",
        json={"phone": "13900000001", "password": "pass123456", "sms_code": "123456"},
    )
    assert r.status_code == 409


def test_acc002_password_login(client):
    register(client, "13900000002", password="secret6666")
    r = client.post("/api/v1/auth/login", json={"phone": "13900000002", "password": "secret6666"})
    assert r.status_code == 200 and r.json()["token"]
    r = client.post("/api/v1/auth/login", json={"phone": "13900000002", "password": "wrong"})
    assert r.status_code == 400


def test_acc001_sms_login_auto_register(client):
    r = client.post("/api/v1/auth/login-sms", json={"phone": "13900000003", "sms_code": "123456"})
    assert r.status_code == 200
    assert r.json()["user"]["nickname"].startswith("用户")


def test_acc010_011_profile_and_skills(client):
    user = register(client, "13900000004")
    r = client.patch(
        "/api/v1/users/me",
        json={"nickname": "阿保", "city": "上海", "skills": ["保洁", "收纳"], "lat": 31.2, "lng": 121.4},
        headers=auth(user),
    )
    assert r.status_code == 200
    me = client.get("/api/v1/users/me", headers=auth(user)).json()
    assert me["skills"] == ["保洁", "收纳"] and me["city"] == "上海"
    # 手机号脱敏展示
    assert "****" in me["phone"]


def test_acc020_verify_and_cred001_initial_score(client):
    user = register(client, "13900000005")
    me = client.get("/api/v1/users/me", headers=auth(user)).json()
    assert me["is_verified"] is False and me["credit_score"] == 100
    verify_user(client, user)
    me = client.get("/api/v1/users/me", headers=auth(user)).json()
    assert me["is_verified"] is True


def test_cred006_public_profile_desensitized(client):
    user = register(client, "13900000006", "公开用户")
    r = client.get(f"/api/v1/users/{user['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["nickname"] == "公开用户"
    assert "phone" not in body  # 公开页不暴露手机号
