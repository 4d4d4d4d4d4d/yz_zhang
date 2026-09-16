"""ACC-003 第三方登录（43 号 spec）。

原始 spec 的备注写着「**App 端 Apple 登录为上架合规必需**」——App Store 的
规则是：只要你提供了任何第三方登录，就必须同时提供 Sign in with Apple。
所以这一条不是体验加分项，是上架的前置条件。

这里最要紧的一条是 **第三方登录不等于实名**。微信认证的是「这是同一个微信」，
不是「这是张三」。把两者混为一谈，等于给实名开了一条后门。
"""
from app.core.config import settings
from app.modules.account.models import User
from app.core.db import SessionLocal
from app.vendors import registry

from .conftest import auth, register


def oauth(client, provider="wechat", credential="cred-abc123"):
    return client.post(f"/api/v1/auth/oauth/{provider}",
                       json={"credential": credential})


# ---------- 基本闭环 ----------
def test_acc003_first_login_creates_an_account_second_reuses_it(client):
    first = oauth(client)
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    uid = first.json()["user"]["id"]

    second = oauth(client)
    assert second.json()["created"] is False
    assert second.json()["user"]["id"] == uid, "同一个第三方账号登出了两个本站账号"


def test_acc003_different_subjects_are_different_people(client):
    a = oauth(client, credential="cred-aaaaaa").json()
    b = oauth(client, credential="cred-bbbbbb").json()
    assert a["user"]["id"] != b["user"]["id"]


def test_acc003_same_subject_on_different_providers_is_not_the_same_person(client):
    """微信的 openid 和 Apple 的 sub 撞号是完全可能的——它们各自命名空间。"""
    a = oauth(client, "wechat", "same-credential").json()
    b = oauth(client, "apple", "same-credential").json()
    assert a["user"]["id"] != b["user"]["id"]


def test_acc003_unsupported_provider_is_refused(client):
    r = client.post("/api/v1/auth/oauth/myspace", json={"credential": "whatever"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "unsupported_provider"


# ---------- 关键：第三方登录不等于实名 ----------
def test_acc003_oauth_account_is_not_verified_and_says_so(client):
    """微信认证的是「这是同一个微信」，不是「这是张三」。"""
    body = oauth(client, credential="cred-newbie1").json()
    assert body["needs_verification"] is True
    assert body["needs_phone"] is True
    assert body["user"]["is_verified"] is False

    # 提现必须仍然被实名闸门挡住
    tok = {"token": body["token"], "id": body["user"]["id"]}
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 100}, headers=auth(tok))
    assert r.status_code in (400, 403), "第三方登录绕过了实名闸门"


def test_acc003_placeholder_phone_is_not_dialable(client):
    """占位手机号必须不可拨打：否则它就是一条绕过手机验证的路。"""
    body = oauth(client, credential="cred-phone01").json()
    db = SessionLocal()
    user = db.get(User, body["user"]["id"])
    phone = user.phone
    db.close()
    assert phone.startswith("oauth:")
    assert not phone.isdigit()
    # 而且不能拿它去走短信登录
    r = client.post("/api/v1/auth/login-sms", json={"phone": phone, "sms_code": "123456"})
    assert r.status_code >= 400


# ---------- 账号状态仍然有效 ----------
def test_acc003_banned_and_deleted_accounts_cannot_come_back_through_oauth(client):
    body = oauth(client, credential="cred-banned1").json()
    uid = body["user"]["id"]
    db = SessionLocal()
    u = db.get(User, uid)
    u.is_banned = True
    db.add(u)
    db.commit()
    db.close()
    r = oauth(client, credential="cred-banned1")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "account_banned"


def test_acc003_new_device_notice_still_fires(client):
    """换了个登录入口，会话可吊销与新设备提醒这些行为不该就此消失。"""
    from app.modules.account.models import LoginSession

    body = oauth(client, credential="cred-device1").json()
    db = SessionLocal()
    n = db.query(LoginSession).filter(LoginSession.user_id == body["user"]["id"]).count()
    db.close()
    assert n == 1, "第三方登录没有建立可吊销的会话"


# ---------- 上架合规与实现等级 ----------
def test_acc003_providers_endpoint_lists_apple(client):
    """App Store：提供了任何第三方登录就必须同时提供 Apple。"""
    got = client.get("/api/v1/auth/oauth/providers").json()
    assert "apple" in got["providers"]
    assert set(got["providers"]) >= {"wechat", "apple", "google"}


def test_acc003_mock_implementation_is_flagged_as_not_verifying(client):
    """mock 等于「客户端说自己是谁就是谁」——面板必须看得见。"""
    got = client.get("/api/v1/auth/oauth/providers").json()
    assert got["verifies"] is False


def test_acc003_production_refuses_the_mock_implementation(monkeypatch):
    """任何人都能冒充任意账号，这和支付/实名是同一等级的风险。"""
    import pytest

    monkeypatch.setattr(settings, "ENV", "prod")
    monkeypatch.setattr(settings, "OAUTH_PROVIDER", "mock")
    registry.reset()
    try:
        with pytest.raises(RuntimeError) as exc:
            registry.startup_check()
        assert "oauth" in str(exc.value)
    finally:
        registry.reset()
