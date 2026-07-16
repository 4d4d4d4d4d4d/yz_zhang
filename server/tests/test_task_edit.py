"""TASK-014 任务编辑 + 防调包（bait-and-switch）保护 + 截止时间校验。

真实业务缺口：原本任务发布后完全不可编辑（连改错别字都不行），
但直接放开编辑又会引入「高价招人、有人报名后偷偷改低价/改要求」的调包欺诈。
业界做法：draft 自由改；已发布且有人报名后实质条款受保护（预算只上不下、
技能锁定），非实质字段（标题/描述/地址提示）始终可改，实质变更通知报名者。
"""
from datetime import timedelta

from app.modules.account.models import utcnow

from .conftest import auth, register, verify_user
from .test_task_flow import publish_task


def test_draft_free_edit(client, requester):
    # 未发布任务可自由改所有字段
    t = client.post("/api/v1/tasks", json={
        "title": "草稿任务", "category": "跑腿", "budget_cents": 10000,
        "is_remote": True, "publish_now": False,
    }, headers=auth(requester)).json()
    r = client.patch(f"/api/v1/tasks/{t['id']}",
                     json={"title": "改后标题", "budget_cents": 5000,
                           "required_skills": ["搬运"]}, headers=auth(requester))
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "改后标题" and body["budget_cents"] == 5000
    assert body["required_skills"] == ["搬运"]


def test_published_no_applicants_free_edit(client, requester):
    t = publish_task(client, requester, budget_cents=10000)
    # 无人报名：仍可自由改，包括下调预算
    r = client.patch(f"/api/v1/tasks/{t['id']}",
                     json={"budget_cents": 8000, "required_skills": ["保洁"]},
                     headers=auth(requester))
    assert r.status_code == 200 and r.json()["budget_cents"] == 8000


def test_baitswitch_protection_after_applicants(client, requester, worker):
    t = publish_task(client, requester, budget_cents=20000)
    client.post(f"/api/v1/tasks/{t['id']}/applications", json={}, headers=auth(worker))

    # 有人报名后：预算不可下调
    r = client.patch(f"/api/v1/tasks/{t['id']}",
                     json={"budget_cents": 10000}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "budget_locked"
    # 技能要求锁定
    r = client.patch(f"/api/v1/tasks/{t['id']}",
                     json={"required_skills": ["高空作业"]}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "skills_locked"
    # 非实质字段仍可改
    r = client.patch(f"/api/v1/tasks/{t['id']}",
                     json={"title": "补充说明版", "description": "细节更清楚了"},
                     headers=auth(requester))
    assert r.status_code == 200 and r.json()["title"] == "补充说明版"

    # 上调预算允许，且通知报名者
    r = client.patch(f"/api/v1/tasks/{t['id']}",
                     json={"budget_cents": 30000}, headers=auth(requester))
    assert r.status_code == 200 and r.json()["budget_cents"] == 30000
    notices = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any("有更新" in n["title"] for n in notices)


def test_edit_forbidden_after_execution_and_for_non_owner(client, requester, worker):
    from .conftest import topup
    from .test_task_flow import match_and_fund

    topup(client, requester, 40000)
    t = publish_task(client, requester, budget_cents=20000)
    # 非本人不可编辑
    stranger = register(client, "26000000001", "路人")
    r = client.patch(f"/api/v1/tasks/{t['id']}", json={"title": "篡改"}, headers=auth(stranger))
    assert r.status_code == 403

    match_and_fund(client, requester, worker, t)  # 进入 matched
    r = client.patch(f"/api/v1/tasks/{t['id']}", json={"title": "执行中改标题"},
                     headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_editable"


def test_deadline_in_past_rejected(client, requester):
    past = (utcnow() - timedelta(days=1)).isoformat()
    r = client.post("/api/v1/tasks", json={
        "title": "过期截止任务", "category": "跑腿", "budget_cents": 10000,
        "is_remote": True, "deadline": past, "publish_now": True,
    }, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "deadline_in_past"

    # 未来截止正常
    future = (utcnow() + timedelta(days=3)).isoformat()
    r = client.post("/api/v1/tasks", json={
        "title": "正常截止任务", "category": "跑腿", "budget_cents": 10000,
        "is_remote": True, "deadline": future, "publish_now": True,
    }, headers=auth(requester))
    assert r.status_code in (200, 201)
