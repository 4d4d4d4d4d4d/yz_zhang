"""API-056 开放 API 账号配额按客户单独调整（235 号 spec，V262）。

158 号的账号总配额是一个全局配置：付费接入方的量比默认大，只能把所有人一起调高。
现在运营可以给某个账号单独调（高或低）、写理由、可设天数，过期自动回到默认；进审计、通知对方。
"""
from datetime import timedelta

from app.core import ratelimit
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.admin.models import AdminAudit
from app.modules.openapi.models import ApiAccountQuota
from tests.conftest import auth
from tests.test_open_api_webhooks import api, make_key
from tests.test_ticket_assign_reply import _admin, _titles

OPEN = "/api/v1/open/v1/tasks"
API = "/api/v1"


def test_ops_raises_one_account_and_it_takes_effect_only_there(client, requester, worker, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 100)
    monkeypatch.setattr(settings, "API_ACCOUNT_DAILY_QUOTA", 1)
    ops = _admin(client, "13800335001", ["ops"])
    k = make_key(client, requester)
    other = make_key(client, worker)
    r = client.put(f"{API}/admin/api-accounts/{requester['id']}/quota", json={"daily_quota": 3, "reason": "签了企业接入合同", "days": 30},
                   headers=auth(ops))
    assert r.status_code == 200, r.text
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "ApiAccountQuotaRow")
    assert [client.get(OPEN, headers=api(k["key"])).status_code for _ in range(4)] == [200, 200, 200, 429]
    assert [client.get(OPEN, headers=api(other["key"])).status_code for _ in range(2)] == [200, 429], "别的账号照旧"
    v = client.get(f"{API}/developer/api-keys/{k['id']}/usage", headers=auth(requester)).json()
    assert v["account_daily_quota"] == 3 and v["account_quota_custom"] is True and v["account_quota_expires_at"]
    _assert_shape(v, "ApiKeyUsageView")
    rows = client.get(f"{API}/admin/api-accounts/quotas", headers=auth(ops)).json()
    assert [(x["user_id"], x["daily_quota"], x["default_quota"], x["today_used"], x["active"]) for x in rows] == [(requester["id"], 3, 1, 3, True)]
    assert any("账号每日配额已调整" in t for t in _titles(client, requester))
    with SessionLocal() as db:
        assert db.query(AdminAudit).filter(AdminAudit.action == "api_account_quota").one().detail == "3/天，30 天：签了企业接入合同"


def test_expiry_reset_and_permissions(client, requester, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 100)
    monkeypatch.setattr(settings, "API_ACCOUNT_DAILY_QUOTA", 1)
    ops = _admin(client, "13800335002", ["ops"])
    support = _admin(client, "13800335003", ["support"])
    url = f"{API}/admin/api-accounts/{requester['id']}/quota"
    body = {"daily_quota": 5, "reason": "压测一周"}
    assert client.put(url, json=body, headers=auth(support)).status_code == 403
    assert client.get(f"{API}/admin/api-accounts/quotas", headers=auth(support)).status_code == 403
    assert client.put(url, json={**body, "reason": "短"}, headers=auth(ops)).status_code == 422
    assert client.put(f"{API}/admin/api-accounts/999999/quota", json=body, headers=auth(ops)).status_code == 404
    assert client.put(url, json={**body, "days": 7}, headers=auth(ops)).status_code == 200
    k = make_key(client, requester)
    with SessionLocal() as db:
        db.query(ApiAccountQuota).one().expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert [client.get(OPEN, headers=api(k["key"])).status_code for _ in range(2)] == [200, 429], "过期自动回到默认"
    assert client.get(f"{API}/admin/api-accounts/quotas", headers=auth(ops)).json()[0]["active"] is False
    r = client.delete(url, params={"reason": "合同到期"}, headers=auth(ops))
    assert r.status_code == 200 and r.json() == {"user_id": requester["id"], "daily_quota": 1, "custom": False}
    again = client.delete(url, params={"reason": "合同到期"}, headers=auth(ops))
    assert again.status_code == 404 and again.json()["detail"]["code"] == "api_account_quota_not_set"
    assert client.get(f"{API}/admin/api-accounts/quotas", headers=auth(ops)).json() == []
