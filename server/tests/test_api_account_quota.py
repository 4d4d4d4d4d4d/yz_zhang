"""API-054 按账号的总配额 / API-053 每分钟剩余次数（158 号 spec）。

152 号的每日配额是「每把 Key」的：一个人建五把 Key，就有五倍的配额。
"""
from app.core import ratelimit
from app.core.config import settings
from tests.conftest import auth
from tests.test_open_api_webhooks import api, make_key

OPEN = "/api/v1/open/v1/tasks"


def test_rate_limit_remaining_header_counts_down(client, requester, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_RATE_PER_MINUTE", 3)
    k = make_key(client, requester)["key"]
    seen = [client.get(OPEN, headers=api(k)).headers["X-RateLimit-Remaining"] for _ in range(3)]
    assert seen == ["2", "1", "0"]


def test_more_keys_do_not_add_up_to_more_quota(client, requester, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 100)
    monkeypatch.setattr(settings, "API_ACCOUNT_DAILY_QUOTA", 3)
    a = make_key(client, requester)
    b = make_key(client, requester, name="第二把")
    assert client.get(OPEN, headers=api(a["key"])).status_code == 200
    assert client.get(OPEN, headers=api(b["key"])).status_code == 200
    r = client.get(OPEN, headers=api(b["key"]))
    assert r.status_code == 200 and r.headers["X-Account-Quota-Remaining"] == "0"
    over = client.get(OPEN, headers=api(a["key"]))
    assert over.status_code == 429 and over.json()["detail"]["code"] == "api_account_quota_exceeded"
    assert "所有 API Key" in over.json()["detail"]["message"] and int(over.headers["Retry-After"]) >= 1
    v = client.get(f"/api/v1/developer/api-keys/{a['id']}/usage", headers=auth(requester)).json()
    assert v["account_today_used"] == 3 and v["account_daily_quota"] == 3 and v["account_today_remaining"] == 0
    assert v["today_used"] == 1 and v["days"][0]["rejected"] == 1, "被账号配额挡回去的不算这把 Key 的用量"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(v, "ApiKeyUsageView")


def test_revoked_keys_still_count_towards_the_account_today(client, requester, monkeypatch):
    """吊销一把再建一把，账号当天的合计不清零。"""
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_ACCOUNT_DAILY_QUOTA", 2)
    a = make_key(client, requester)
    client.get(OPEN, headers=api(a["key"]))
    client.get(OPEN, headers=api(a["key"]))
    client.delete(f"/api/v1/developer/api-keys/{a['id']}", headers=auth(requester))
    b = make_key(client, requester, name="新的一把")
    assert client.get(OPEN, headers=api(b["key"])).status_code == 429


def test_other_accounts_are_not_affected(client, requester, worker, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_ACCOUNT_DAILY_QUOTA", 1)
    a = make_key(client, requester)
    client.get(OPEN, headers=api(a["key"]))
    assert client.get(OPEN, headers=api(a["key"])).status_code == 429
    w = make_key(client, worker)
    assert client.get(OPEN, headers=api(w["key"])).status_code == 200
