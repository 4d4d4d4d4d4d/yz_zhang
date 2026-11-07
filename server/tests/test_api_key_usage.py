"""API-052 API Key 用量与每日配额（152 号 spec）。

V173 有了每分钟限流，但集成方看不到自己用了多少；一个跑飞的循环在限流之内照样能一天打几十万次。
"""
from datetime import datetime

from app.core import ratelimit
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.openapi import usage
from app.modules.openapi.models import ApiKeyUsage
from tests.conftest import auth, register
from tests.test_open_api_webhooks import api, make_key

OPEN = "/api/v1/open/v1/tasks"


def _usage(client, user, key_id, days=14):
    return client.get(f"/api/v1/developer/api-keys/{key_id}/usage", params={"days": days}, headers=auth(user))


def test_beijing_day_and_reset_time():
    # UTC 10-14 16:30 = 北京 10-15 00:30
    assert usage.day_of(datetime(2026, 10, 14, 16, 30)) == "2026-10-15"
    assert usage.day_of(datetime(2026, 10, 14, 15, 59)) == "2026-10-14"
    # 北京 10-14 23:59 的下一个零点是北京 10-15 00:00 = UTC 10-14 16:00
    assert usage.next_reset(datetime(2026, 10, 14, 15, 59)) == datetime(2026, 10, 14, 16, 0)


def test_each_request_is_counted_and_reported_with_headers(client, requester, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 100)
    k = make_key(client, requester)
    for i in range(3):
        r = client.get(OPEN, headers=api(k["key"]))
        assert r.status_code == 200
        assert r.headers["X-Quota-Limit"] == "100" and r.headers["X-Quota-Remaining"] == str(100 - i - 1)
    v = _usage(client, requester, k["id"]).json()
    assert v["today_used"] == 3 and v["today_remaining"] == 97 and v["effective_daily_quota"] == 100
    assert v["days"][0] == {"day": v["today"], "count": 3, "rejected": 0} and len(v["days"]) == 14
    assert v["time_zone"] == "北京时间 UTC+8" and v["resets_at"].endswith("Z")
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(v, "ApiKeyUsageView")


def test_quota_exhausted_gives_429_until_beijing_midnight_and_counts_rejections(client, requester, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 2)
    k = make_key(client, requester)
    other = make_key(client, requester, name="另一把")
    assert client.get(OPEN, headers=api(k["key"])).status_code == 200
    assert client.get(OPEN, headers=api(k["key"])).status_code == 200
    over = client.get(OPEN, headers=api(k["key"]))
    assert over.status_code == 429 and over.json()["detail"]["code"] == "api_key_quota_exceeded"
    assert "明天 0 点恢复" in over.json()["detail"]["message"] and over.headers["X-Quota-Remaining"] == "0"
    assert 1 <= int(over.headers["Retry-After"]) <= 86400
    client.get(OPEN, headers=api(k["key"]))
    v = _usage(client, requester, k["id"]).json()
    assert v["today_used"] == 2 and v["days"][0]["rejected"] == 2, "被挡回去的不算用量，但要记下来"
    assert client.get(OPEN, headers=api(other["key"])).status_code == 200, "另一把 Key 的配额不受影响"


def test_rate_limited_requests_are_recorded_as_rejected(client, requester, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_RATE_PER_MINUTE", 1)
    k = make_key(client, requester)
    assert client.get(OPEN, headers=api(k["key"])).status_code == 200
    assert client.get(OPEN, headers=api(k["key"])).status_code == 429
    day = _usage(client, requester, k["id"]).json()["days"][0]
    assert (day["count"], day["rejected"]) == (1, 1)


def test_owner_can_lower_but_not_raise_quota_and_only_sees_own_usage(client, requester, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 50)
    k = make_key(client, requester)
    url = f"/api/v1/developer/api-keys/{k['id']}/quota"
    r = client.put(url, json={"daily_quota": 1}, headers=auth(requester))
    assert r.json() == {"id": k["id"], "daily_quota": 1, "effective_daily_quota": 1}
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "ApiKeyQuota")
    assert client.get(OPEN, headers=api(k["key"])).status_code == 200
    assert client.get(OPEN, headers=api(k["key"])).status_code == 429
    high = client.put(url, json={"daily_quota": 51}, headers=auth(requester))
    assert high.status_code == 400 and high.json()["detail"]["code"] == "api_key_quota_above_cap"
    stranger = register(client, "13800270001", "别人")
    assert client.put(url, json={"daily_quota": 2}, headers=auth(stranger)).status_code == 404
    assert _usage(client, stranger, k["id"]).status_code == 404
    listed = next(x for x in client.get("/api/v1/developer/api-keys", headers=auth(requester)).json() if x["id"] == k["id"])
    assert (listed["daily_quota"], listed["effective_daily_quota"]) == (1, 1)
    assert client.put(url, json={"daily_quota": 0}, headers=auth(requester)).json()["effective_daily_quota"] == 50


def test_rotation_keeps_quota_and_does_not_reset_todays_usage(client, requester, monkeypatch):
    """轮换一次就清零的话，每日配额等于没有。"""
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 3)
    k = make_key(client, requester)
    client.put(f"/api/v1/developer/api-keys/{k['id']}/quota", json={"daily_quota": 2}, headers=auth(requester))
    assert client.get(OPEN, headers=api(k["key"])).status_code == 200
    assert client.get(OPEN, headers=api(k["key"])).status_code == 200
    new = client.post(f"/api/v1/developer/api-keys/{k['id']}/rotate", headers=auth(requester)).json()
    rows = {x["id"]: x for x in client.get("/api/v1/developer/api-keys", headers=auth(requester)).json()}
    assert rows[new["id"]]["daily_quota"] == 2
    assert client.get(OPEN, headers=api(new["key"])).status_code == 429
    assert _usage(client, requester, new["id"]).json()["today_used"] == 2


def test_old_days_are_reported_newest_first_with_zeros_filled(client, requester):
    k = make_key(client, requester)
    with SessionLocal() as db:
        today = usage.day_of(usage.utcnow())
        from datetime import date, timedelta

        two_ago = (date.fromisoformat(today) - timedelta(days=2)).isoformat()
        db.add(ApiKeyUsage(key_id=k["id"], day=two_ago, count=7, rejected=1))
        db.commit()
    days = _usage(client, requester, k["id"], days=3).json()["days"]
    assert [d["day"] for d in days][2] == two_ago and days[2] == {"day": two_ago, "count": 7, "rejected": 1}
    assert days[1]["count"] == 0 and len(days) == 3


def test_platform_cap_lowered_later_still_wins(client, requester, monkeypatch):
    """Key 自己设的配额是「更低」的上限：平台默认后来调得比它还低时，按平台的算。"""
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 50)
    k = make_key(client, requester)
    client.put(f"/api/v1/developer/api-keys/{k['id']}/quota", json={"daily_quota": 40}, headers=auth(requester))
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 10)
    assert _usage(client, requester, k["id"]).json()["effective_daily_quota"] == 10
