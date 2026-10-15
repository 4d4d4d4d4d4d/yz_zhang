"""API-050 开放 API 按 API Key 独立限流（145 号 spec）。

此前开放 API 只走全站的「按 IP + 按账号」限流：一个集成写了个死循环，耗光的是**同一出口 IP 后面所有人**的写额度，
而它自己没有任何单独的上限；超限回的还是 400，集成方的 HTTP 客户端认不出该退避。
"""
from app.core.config import settings
from tests.conftest import auth, register
from tests.test_open_api_webhooks import api, make_key

OPEN = "/api/v1/open/v1/tasks"


def test_each_key_has_its_own_minute_budget_with_a_real_429(client, requester, monkeypatch):
    monkeypatch.setattr(settings, "API_KEY_RATE_PER_MINUTE", 3)
    a, b = make_key(client, requester)["key"], make_key(client, requester, name="另一把")["key"]
    for _ in range(3):
        r = client.get(OPEN, headers=api(a))
        assert r.status_code == 200 and r.headers["X-RateLimit-Limit"] == "3"
    over = client.get(OPEN, headers=api(a))
    assert over.status_code == 429 and over.json()["detail"]["code"] == "api_key_rate_limited"
    assert int(over.headers["Retry-After"]) >= 1 and "每分钟最多 3 次" in over.json()["detail"]["message"]
    assert client.get(OPEN, headers=api(b)).status_code == 200, "另一把 Key 的额度不受影响"


def test_owner_can_lower_but_not_raise_and_rotation_keeps_it(client, requester, monkeypatch):
    monkeypatch.setattr(settings, "API_KEY_RATE_PER_MINUTE", 50)
    k = make_key(client, requester)
    url = f"/api/v1/developer/api-keys/{k['id']}/rate-limit"
    r = client.put(url, json={"rate_per_minute": 1}, headers=auth(requester))
    assert r.json() == {"id": k["id"], "rate_per_minute": 1, "effective_rate_per_minute": 1}
    assert client.get(OPEN, headers=api(k["key"])).status_code == 200
    assert client.get(OPEN, headers=api(k["key"])).status_code == 429
    high = client.put(url, json={"rate_per_minute": 51}, headers=auth(requester))
    assert high.status_code == 400 and high.json()["detail"]["code"] == "api_key_rate_above_cap"
    other = register(client, "13800250001", "别人")
    assert client.put(url, json={"rate_per_minute": 2}, headers=auth(other)).status_code == 404
    listed = next(x for x in client.get("/api/v1/developer/api-keys", headers=auth(requester)).json() if x["id"] == k["id"])
    assert (listed["rate_per_minute"], listed["effective_rate_per_minute"]) == (1, 1)
    new = client.post(f"/api/v1/developer/api-keys/{k['id']}/rotate", headers=auth(requester)).json()
    rows = {x["id"]: x for x in client.get("/api/v1/developer/api-keys", headers=auth(requester)).json()}
    assert rows[new["id"]]["rate_per_minute"] == 1, "轮换不改额度"
    assert client.put(f"/api/v1/developer/api-keys/{new['id']}/rate-limit", json={"rate_per_minute": 0},
                      headers=auth(requester)).json()["effective_rate_per_minute"] == 50, "0 = 恢复平台默认"


def test_open_api_writes_do_not_eat_the_shared_ip_write_budget(client, requester, monkeypatch):
    from app.core import ratelimit

    ratelimit.reset()   # 夹具里注册、实名的写请求不算进这条用例
    monkeypatch.setattr(settings, "WRITE_RATE_PER_MINUTE", 2)
    for _ in range(2):   # 一个跑飞的集成：写请求打满它自己的那个 IP 池
        client.post(OPEN, json={}, headers=api("pk_bogus"))
    r = client.post(OPEN, json={}, headers=api("pk_bogus"))
    assert r.status_code == 429, "开放 API 自己的池仍然有上限"
    # 同一出口 IP 后面的真人照常写
    ok = client.post("/api/v1/auth/login", json={"phone": "13800250002", "password": "x"})
    assert ok.status_code != 429, ok.text


def test_shape(client, requester):
    from tests.test_client_shape_alignment import _assert_shape

    k = make_key(client, requester)
    rows = client.get("/api/v1/developer/api-keys", headers=auth(requester)).json()
    first = rows[0]
    _assert_shape(first, "ApiKeyView")
    r = client.put(f"/api/v1/developer/api-keys/{k['id']}/rate-limit", json={"rate_per_minute": 5}, headers=auth(requester)).json()
    _assert_shape(r, "ApiKeyRate")
