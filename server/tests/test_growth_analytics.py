"""增长与分析：13.C 埋点漏斗 / CNT-022 邀请裂变 / SRCH-003 搜索热词"""
import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, promote_admin, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def make_admin(client, phone="12900000000"):
    admin = register(client, phone, "运营")
    promote_admin(admin["id"])
    return admin


# ---------- 埋点漏斗（13.C） ----------
def test_analytics_funnels(client, requester, worker):
    admin = make_admin(client)
    topup(client, requester, 40000)
    # 一条走完的任务 + 一条只发布的任务
    done = publish_task(client, requester, title="已完成单")
    match_and_fund(client, requester, worker, done)
    client.post(f"/api/v1/tasks/{done['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{done['id']}/accept-delivery", headers=auth(requester))
    publish_task(client, requester, title="仅发布单")
    # 客户端埋点上报
    r = client.post("/api/v1/events", json={"name": "task_publish_click"}, headers=auth(requester))
    assert r.status_code == 201

    f = client.get("/api/v1/admin/funnels", headers=auth(admin)).json()
    pub = f["publish_funnel"]
    assert pub["created"] == 2 and pub["published"] == 2
    assert pub["matched"] == 1 and pub["completed"] == 1
    assert pub["complete_rate"] == 1.0  # 1/1 matched→completed
    assert f["worker_funnel"]["accepted"] == 1 and f["worker_funnel"]["settled"] == 1
    assert f["custom_events"]["task_publish_click"] == 1
    # 非管理员看不到
    assert client.get("/api/v1/admin/funnels", headers=auth(requester)).status_code == 403


# ---------- 邀请裂变（CNT-022） ----------
def test_cnt022_referral_attribution_and_reward(client):
    # 邀请人注册拿到邀请码
    inviter = register(client, "12900000001", "邀请人")
    me = client.get("/api/v1/users/me", headers=auth(inviter)).json()
    code = me["referral_code"]
    assert code.startswith("R")

    # 被邀请人带邀请码注册
    r = client.post("/api/v1/auth/register", json={
        "phone": "12900000002", "password": "pass123456", "nickname": "新人",
        "sms_code": "123456", "referral_code": code,
    })
    invitee = {"token": r.json()["token"], "id": r.json()["user"]["id"]}
    verify_user(client, invitee, "新人实名")

    inviter_before = client.get(f"/api/v1/users/{inviter['id']}").json()["credit_score"]

    # 被邀请人作为执行者完成首单 → 邀请人得奖励
    boss = register(client, "12900000003", "发布者")
    verify_user(client, boss)
    topup(client, boss, 40000)
    task = publish_task(client, boss)
    match_and_fund(client, boss, invitee, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(invitee))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(boss))

    inviter_after = client.get(f"/api/v1/users/{inviter['id']}").json()["credit_score"]
    assert inviter_after == inviter_before + 5  # REFERRAL_BONUS
    notes = client.get("/api/v1/notifications", headers=auth(inviter)).json()
    assert any("邀请奖励到账" == n["title"] for n in notes)

    # 第二单不再重复奖励
    task2 = publish_task(client, boss, title="第二单")
    topup(client, boss, 40000)
    match_and_fund(client, boss, invitee, task2)
    client.post(f"/api/v1/tasks/{task2['id']}/deliver", headers=auth(invitee))
    client.post(f"/api/v1/tasks/{task2['id']}/accept-delivery", headers=auth(boss))
    assert client.get(f"/api/v1/users/{inviter['id']}").json()["credit_score"] == inviter_after


def test_cnt022_invalid_referral_code_ignored(client):
    r = client.post("/api/v1/auth/register", json={
        "phone": "12900000009", "password": "pass123456", "nickname": "无效码",
        "sms_code": "123456", "referral_code": "R999999",
    })
    assert r.status_code == 201  # 无效邀请码不阻断注册


# ---------- 搜索热词（SRCH-003） ----------
def test_srch003_trending_and_suggest(client, requester):
    """热词按**人数**排序、联想按前缀、空前缀回热词。

    V127 改写了这条的造数方式。原来是**同一个人**搜「保洁」三次，断言它以
    count=3 登上热词榜——那正是 PRIV-060 关掉的行为：一个人的搜索被公开，
    而且次数可以被一个人刷出来。这条测试的**意图**（排序、前缀、空前缀）
    仍然成立，所以留着它，只把造数换成不同的人：保洁 4 人、保姆 3 人、
    跑腿 1 人（达不到门槛，不该出现）。
    """
    from tests.conftest import register

    people = [requester] + [register(client, f"138000989{i:02d}", f"搜索者{i}") for i in range(3)]

    def s(user, q):
        client.get("/api/v1/search", params={"q": q}, headers=auth(user))

    for u in people:                 # 4 个人搜保洁
        s(u, "保洁")
    for u in people[:3]:             # 3 个人搜保姆
        s(u, "保姆")
    s(people[0], "跑腿")             # 1 个人搜跑腿：不公开

    trending = client.get("/api/v1/search/trending").json()
    assert trending[0]["term"] == "保洁" and trending[0]["count"] == 4
    assert all(t["term"] != "跑腿" for t in trending), "一个人的搜索上了热词榜"
    # 联想：前缀「保」→ 命中保洁与保姆，按人数排序
    sug = client.get("/api/v1/search/suggest", params={"q": "保"}).json()
    assert sug[0] == "保洁" and "保姆" in sug
    # 空前缀 → 返回热词
    assert client.get("/api/v1/search/suggest").json()[0] == "保洁"
