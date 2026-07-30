"""TASK-016 我的任务中心：posted / working / all + 状态筛选 + 分页。

广场只展示 published+public，此前用户无法列出自己的草稿/执行中/已完成任务，
也看不到自己正在执行的单。补个人任务中心后闭合这一能力缺口。
"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def test_posted_working_all_filters(client, requester, worker):
    topup(client, requester, 40000)
    # requester 发布 2 单，其中 1 单由 worker 执行
    t1 = publish_task(client, requester, title="我发的单一")
    t2 = publish_task(client, requester, title="我发的单二")
    match_and_fund(client, requester, worker, t2)  # worker 执行 t2

    posted = client.get("/api/v1/tasks/mine?role=posted", headers=auth(requester)).json()
    assert {t["id"] for t in posted} == {t1["id"], t2["id"]}

    # worker：作为执行者能看到 t2
    working = client.get("/api/v1/tasks/mine?role=working", headers=auth(worker)).json()
    assert [t["id"] for t in working] == [t2["id"]]
    # worker 没发过任务
    assert client.get("/api/v1/tasks/mine?role=posted", headers=auth(worker)).json() == []

    # all：worker 看到自己执行的；requester 看到自己发的
    assert {t["id"] for t in client.get("/api/v1/tasks/mine", headers=auth(worker)).json()} == {t2["id"]}


def test_status_filter_and_draft_visible(client, requester):
    # 草稿（不进广场）也能在「我的」看到
    draft = client.post("/api/v1/tasks", json={
        "title": "我的草稿", "category": "跑腿", "budget_cents": 10000,
        "is_remote": True, "publish_now": False,
    }, headers=auth(requester)).json()
    published = publish_task(client, requester, title="我的已发布")

    drafts = client.get("/api/v1/tasks/mine?status=draft", headers=auth(requester)).json()
    assert [t["id"] for t in drafts] == [draft["id"]]
    pubs = client.get("/api/v1/tasks/mine?status=published", headers=auth(requester)).json()
    assert published["id"] in [t["id"] for t in pubs] and draft["id"] not in [t["id"] for t in pubs]


def test_mine_requires_auth_and_paginates(client, requester):
    assert client.get("/api/v1/tasks/mine").status_code == 403  # 需登录
    for i in range(5):
        publish_task(client, requester, title=f"分页我的单{i}")
    p1 = client.get("/api/v1/tasks/mine?limit=2&offset=0", headers=auth(requester)).json()
    p2 = client.get("/api/v1/tasks/mine?limit=2&offset=2", headers=auth(requester)).json()
    assert len(p1) == 2 and len(p2) == 2
    assert not (set(t["id"] for t in p1) & set(t["id"] for t in p2))


def test_mine_isolated_between_users(client, requester, worker):
    publish_task(client, requester, title="别人的单")
    # worker 的「我的」里不含 requester 的任务
    assert client.get("/api/v1/tasks/mine", headers=auth(worker)).json() == []
