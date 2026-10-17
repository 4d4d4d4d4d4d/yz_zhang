"""CONC-066 列表接口的 N+1：每一个列表接口，数据多了查询次数不许跟着涨（115 号 spec）。

V118 修过一个（每开一次私聊扫全表），V128 修过一个（内容流每条两次）。两次都是撞上的，不是查出来的。
这里把它查出来：同一个视角（一个有发布、有报名、关注了人、有私聊、有通知、有收藏、有流水的普通用户），
造 k=2 与 k=6 两份「世界」，对每一个不带路径参数的列表接口各请求一次、数 SQL 条数。
**条数随 k 增长就是 N+1。** 有意随数据量增长的写进 `GROWS_ON_PURPOSE` 并写明为什么。
"""
import pytest
import sqlalchemy as sa

from app.core.db import SessionLocal, engine
from tests.conftest import auth, bind_payout, money

K_SMALL, K_LARGE = 2, 6
SKIP = {
    # 不是列表：单个对象 / 配置 / 计数
    "/auth/captcha-config", "/auth/oauth/providers", "/developer/scopes", "/legal/agreements",
    "/users/me", "/wallet", "/wallet/payout-account", "/spaces/me", "/me/newcomer",
    "/conversations/unread-count", "/notifications/unread-count", "/notifications/prefs",
    "/ventures/risk-disclosure", "/finance/my-tax", "/market/supply-hint", "/knowledge/price-reference",
    "/anchors/verify", "/anchors/blockchain", "/anchors/coverage",
    # 需要必填查询参数的（由各自的测试覆盖）
    "/search", "/search/suggest", "/knowledge/search",
    # 机器接口（API Key 鉴权，另有闸门）
    "/open/v1/tasks", "/open/v1/wallet",
    # 运维接口
    "/events/dead-letters", "/events/health",
}
# 不带参数请求不到列表的，补上参数
PARAMS = {"/contents/mine": "?status=published", "/knowledge/templates": "?category=保洁",
          "/task-templates": "?category=保洁"}
# 有意随数据量增长的：每一条都要写为什么不是 N+1
GROWS_ON_PURPOSE: dict[str, str] = {
    "/users/me/export": "PIPL 数据导出：本来就要把本人的每一类数据逐类读出来；一次请求、量级受个人数据量约束，不在热路径上",
}


class _Counter:
    def __init__(self):
        self.n = 0

    def __call__(self, conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        self.n += 1


def _person(i: int, tag: str):
    from app.core.security import create_token
    from app.modules.account.models import User
    from app.modules.legal import consent

    with SessionLocal() as db:
        u = User(phone=f"139{tag}{i:05d}", nickname=f"{tag}{i}", password_hash="x", is_verified=True,
                 is_adult=True, real_name="张三", id_digest=f"d{tag}{i}", id_masked="1101**", credit_score=100)
        db.add(u)
        db.flush()
        consent.grant_registration_consents(db, u.id)
        db.commit()
        return {"id": u.id, "token": create_token(u.id)}


def _world(client, k: int, tag: str) -> dict:
    """一个普通用户 me 的世界，每一类东西 k 份。"""
    from tests.test_task_flow import CLEAN_TASK

    me = _person(0, tag)
    others = [_person(i + 1, tag) for i in range(k)]
    h = auth(me)
    assert client.post("/api/v1/wallet/topup", json={"amount_cents": 500000}, headers=money(h)).status_code == 200
    bind_payout(client, me)
    for o in others:
        oh = auth(o)
        # 别人发的任务 → 广场；me 报名 → 我的报名；me 收藏
        t = client.post("/api/v1/tasks", json={**CLEAN_TASK, "title": f"{tag}别人的任务{o['id']}"}, headers=oh)
        assert t.status_code == 201, t.text
        tid = t.json()["id"]
        client.post(f"/api/v1/tasks/{tid}/applications", json={"message": "我来"}, headers=h)
        client.post(f"/api/v1/tasks/{tid}/bookmark", headers=h)
        # me 发的任务，别人报名 → 我的任务、通知
        mt = client.post("/api/v1/tasks", json={**CLEAN_TASK, "title": f"{tag}我的任务{o['id']}"}, headers=h).json()
        client.post(f"/api/v1/tasks/{mt['id']}/applications", json={"message": "选我"}, headers=oh)
        # 关注 → 内容流；别人发作品
        client.put(f"/api/v1/users/{o['id']}/follow", headers=h)
        client.post("/api/v1/contents", json={"body": f"{tag}作品{o['id']}"}, headers=oh)
        client.post("/api/v1/contents", json={"body": f"{tag}我的作品{o['id']}"}, headers=h)
        # 私聊
        conv = client.post("/api/v1/conversations/direct", json={"user_id": o["id"]}, headers=h).json()
        client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "你好"}, headers=oh)
        # 好友、圈层、空间、工单
        client.post("/api/v1/friends/requests", json={"user_id": me["id"]}, headers=oh)
        client.post("/api/v1/circles", json={"name": f"{tag}圈{o['id']}", "kind": "interest"}, headers=oh)
        client.put("/api/v1/spaces/me", json={"revision": 0, "published": True, "headline": f"{tag}的空间{o['id']}",
                                              "introduction": "", "items": []}, headers=oh)
        client.post("/api/v1/support/tickets", json={"category": "other", "subject": f"{tag}工单{o['id']}",
                                                      "content": "有个问题想问一下"}, headers=h)
        # 流水
        client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000}, headers=money(h))
    return me


def _list_endpoints() -> list[str]:
    from app.main import app

    out = []
    for path, ops in sorted(app.openapi()["paths"].items()):
        if ("get" in ops and path.startswith("/api/v1") and "{" not in path
                and "/admin/" not in path and "/jobs/" not in path):
            p = path[len("/api/v1"):]
            if p not in SKIP:
                out.append(p)
    return out


def _counts(client, me) -> dict[str, tuple[int, int]]:
    counter = _Counter()
    sa.event.listen(engine, "before_cursor_execute", counter)
    try:
        out = {}
        for p in _list_endpoints():
            counter.n = 0
            r = client.get(f"/api/v1{p}{PARAMS.get(p, '')}", headers=auth(me))
            out[p] = (counter.n, r.status_code)
        return out
    finally:
        sa.event.remove(engine, "before_cursor_execute", counter)


@pytest.fixture()
def both_worlds(client):
    small = _counts(client, _world(client, K_SMALL, "1"))
    large = _counts(client, _world(client, K_LARGE, "2"))
    return small, large


def test_the_scanner_finds_the_list_endpoints():
    eps = _list_endpoints()
    assert len(eps) >= 30 and "/tasks" in eps and "/feed" in eps


def test_no_list_endpoint_does_more_queries_when_there_is_more_data(both_worlds):
    small, large = both_worlds
    grows = {p: (small[p][0], large[p][0]) for p in small
             if large[p][0] > small[p][0] + 1 and p not in GROWS_ON_PURPOSE}
    assert not grows, ("这些列表接口的 SQL 条数随数据量增长（k=2 → k=6），是 N+1：\n  "
                       + "\n  ".join(f"{p}: {a} → {b}" for p, a, b in
                                     sorted((p, a, b) for p, (a, b) in grows.items())))


def test_the_world_really_has_data_in_it(both_worlds):
    """自检：世界造空了，所有接口条数都不涨——那是最糟的一种绿。"""
    small, large = both_worlds
    assert all(small[p][1] < 500 for p in small), {p: v for p, v in small.items() if v[1] >= 500}
    assert large["/feed"][0] >= 1 and large["/tasks"][0] >= 1
