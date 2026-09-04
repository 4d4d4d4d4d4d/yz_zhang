"""TASK-003 任务广场分页：offset/limit 可翻至任意页，页间不重不漏。

原实现只有 limit（≤100）+ 硬性 500 上限，无 offset——超过窗口的旧任务永远
翻不到，且非地理场景先拉 500 再切片。补 DB 层 offset 分页。
"""
from .conftest import auth


def _make_tasks(client, requester, n):
    ids = []
    for i in range(n):
        t = client.post("/api/v1/tasks", json={
            "title": f"分页任务{i:02d}", "category": "跑腿", "budget_cents": 10000,
            "is_remote": True, "publish_now": True,
        }, headers=auth(requester)).json()
        ids.append(t["id"])
    return ids


def test_offset_pagination_no_overlap(client, requester):
    ids = _make_tasks(client, requester, 25)  # 倒序返回：最新在前

    page1 = client.get("/api/v1/tasks?limit=10&offset=0").json()
    page2 = client.get("/api/v1/tasks?limit=10&offset=10").json()
    page3 = client.get("/api/v1/tasks?limit=10&offset=20").json()

    assert len(page1) == 10 and len(page2) == 10 and len(page3) == 5  # 25 条共 3 页
    seen = [t["id"] for t in page1 + page2 + page3]
    assert len(seen) == len(set(seen)) == 25  # 无重复无遗漏
    # 与全量倒序一致
    assert seen == sorted(ids, reverse=True)


def test_limit_capped_and_offset_beyond_end(client, requester):
    _make_tasks(client, requester, 5)
    # limit 上限 100（超过被 422 拒绝）
    assert client.get("/api/v1/tasks?limit=101").status_code == 422
    # offset 越界 → 空列表而非报错
    assert client.get("/api/v1/tasks?offset=999").json() == []


def test_geo_pagination(client, requester):
    # 地理检索路径也支持 offset（按距离排序后分页）
    for i in range(6):
        client.post("/api/v1/tasks", json={
            "title": f"附近任务{i}", "category": "跑腿", "budget_cents": 10000,
            "is_remote": False, "city": "上海", "lat": 31.23 + i * 0.001, "lng": 121.47,
            "address_hint": "浦东", "publish_now": True,
        }, headers=auth(requester))
    p1 = client.get("/api/v1/tasks?lat=31.23&lng=121.47&limit=3&offset=0").json()
    p2 = client.get("/api/v1/tasks?lat=31.23&lng=121.47&limit=3&offset=3").json()
    assert len(p1) == 3 and len(p2) == 3
    assert not (set(t["id"] for t in p1) & set(t["id"] for t in p2))  # 页间不重
    # 第一页按距离升序（最近在前）
    dists = [t["distance_m"] for t in p1]
    assert dists == sorted(dists)
