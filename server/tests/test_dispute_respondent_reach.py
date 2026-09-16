"""DSPR-010~031 被诉方真的收得到、也真的开得了口（38 号 spec）。

V61 修好了「被诉方在客户端上是哑的」——但只修了 Web。
线下服务的执行方主要在 App 上，于是修完之后的分布是：
**最可能坐在被告席上的那群人，恰恰是唯一仍然开不了口的那群人。**
这比原来「所有人都开不了口」更糟，因为它看起来已经修好了。

另一半是提醒：开得了口不等于知道要开口。此前只有开案时一条通知，
答辩期 48 小时静默过去就变成缺席裁决——**一个只在开始时响一次的闹钟，
和没有闹钟差别不大。**
"""
import os
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.modules.account.models import utcnow
from app.modules.dispute.models import Dispute

from .conftest import JOB_HEADERS, auth, register, topup
from .test_task_flow import match_and_fund, publish_task

APP_TSX = os.path.join(os.path.dirname(__file__), "..", "..", "app", "App.tsx")


def open_dispute(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付不符约定，要求重做或退款"}, headers=auth(requester))
    assert r.status_code == 201, r.text
    return task, r.json()


def run_reminder(client):
    r = client.post("/api/v1/disputes/jobs/remind-response", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def near_deadline(dispute_id, hours_before=1):
    """把开案时间往前推，使「距答辩截止还剩 hours_before 小时」。"""
    db = SessionLocal()
    d = db.get(Dispute, dispute_id)
    d.created_at = utcnow() - timedelta(hours=settings.DISPUTE_RESPONSE_HOURS - hours_before)
    db.add(d)
    db.commit()
    db.close()


def notices(client, user):
    return client.get("/api/v1/notifications", headers=auth(user)).json()


# ---------- DSPR-020~024 提醒 ----------
def test_dspr020_respondent_is_reminded_before_the_window_closes(client, requester, worker):
    """答辩期将届满而被诉方仍未陈述 → 必达提醒。"""
    task, dispute = open_dispute(client, requester, worker)
    assert run_reminder(client)["reminded"] == 0, "刚开案就催属于骚扰"

    near_deadline(dispute["id"])
    assert run_reminder(client)["reminded"] == 1

    body = next(n for n in notices(client, worker) if n["title"] == "答辩期即将届满")["body"]
    assert f"#{task['id']}" in body          # 是哪个任务
    assert "小时后截止" in body                # 还剩多久
    assert "仅凭对方的陈述" in body             # 不答辩的代价


def test_dspr030_running_the_job_twice_produces_one_reminder(client, requester, worker):
    """「距截止不足 N 小时」每次跑都成立——没有幂等标记就是每小时一条骚扰。"""
    _, dispute = open_dispute(client, requester, worker)
    near_deadline(dispute["id"])
    assert run_reminder(client)["reminded"] == 1
    assert run_reminder(client)["reminded"] == 0
    assert len([n for n in notices(client, worker) if n["title"] == "答辩期即将届满"]) == 1


def test_dspr024_respondent_who_already_spoke_is_not_nagged(client, requester, worker):
    _, dispute = open_dispute(client, requester, worker)
    client.post(f"/api/v1/disputes/{dispute['id']}/statements",
                json={"content": "已按约定完成，附现场照片。"}, headers=auth(worker))
    near_deadline(dispute["id"])
    assert run_reminder(client)["reminded"] == 0
    assert not [n for n in notices(client, worker) if n["title"] == "答辩期即将届满"]


def test_dspr024_closed_dispute_is_not_reminded(client, requester, worker):
    _, dispute = open_dispute(client, requester, worker)
    admin = register(client, "13955500099", "仲裁员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    near_deadline(dispute["id"], hours_before=-1)          # 答辩期已过，可缺席裁决
    client.post(f"/api/v1/disputes/{dispute['id']}/verdict",
                json={"executor_share_bps": 5000, "reason": "逾期未答辩，依现有证据处理"},
                headers=auth(admin))
    assert run_reminder(client)["reminded"] == 0


def test_dspr021_lead_time_follows_the_configured_window(client, requester, worker, monkeypatch):
    """提前量按答辩期的 1/4 算，不写死小时数。

    写死「截止前 12 小时」在把答辩期调成 6 小时的部署里永远不会触发——
    这是 DSPC-012 那个硬编码 48 的同类错误。
    """
    monkeypatch.setattr(settings, "DISPUTE_RESPONSE_HOURS", 8)   # → 提前量 2 小时
    _, dispute = open_dispute(client, requester, worker)
    near_deadline(dispute["id"], hours_before=3)                 # 还没进提醒窗
    assert run_reminder(client)["reminded"] == 0
    near_deadline(dispute["id"], hours_before=1)                 # 进了
    assert run_reminder(client)["reminded"] == 1


def test_dspr023_reminder_ignores_the_notification_switch(client, requester, worker):
    """允许用一个通知开关放弃自己的陈述权，是把公平交给默认设置。"""
    assert client.put("/api/v1/notifications/prefs?category=task&enabled=false",
                      headers=auth(worker)).status_code == 200
    _, dispute = open_dispute(client, requester, worker)
    near_deadline(dispute["id"])
    run_reminder(client)
    assert [n for n in notices(client, worker) if n["title"] == "答辩期即将届满"]


# ---------- DSPR-010~013 App 侧 ----------
def test_dspr010_app_can_reach_every_respondent_action():
    """App 必须接上和 Web 同一批当事人动作。

    `app/` 不在 npm workspaces 里、没有 tsconfig，**从来没有任何东西
    typecheck 过它**——这正是这个缺口能一直躺着的原因。
    这里做的是字面量检查（可靠、不需要装 expo/react-native），
    完整的类型检查记为缺口 DSPR-042。
    """
    src = open(APP_TSX).read()
    for method in ("disputeByTask", "disputeStatements",
                   "addDisputeStatement", "appealDispute"):
        assert f"client.{method}(" in src, (
            f"app/App.tsx 没有调用 {method}——"
            "被诉方在 App 上仍然开不了口，而线下执行方主要在 App 上"
        )


def test_dspr011_app_states_the_cost_of_staying_silent():
    """不是画个输入框就算给了机会：得让人知道不说话会发生什么。"""
    src = open(APP_TSX).read()
    assert "尚未答辩" in src
    assert "仅凭对方的陈述" in src


def test_dspr013_app_hides_the_form_once_the_dispute_is_closed():
    src = open(APP_TSX).read()
    assert "'resolved'" in src and "'settled'" in src


def test_dspr010_app_does_not_recompute_server_side_rules():
    """截止时间与可否申诉都用服务端给的字段，不在 App 里再算一遍。"""
    src = open(APP_TSX).read()
    assert "dispute.response_deadline" in src
    assert "dispute.appealable" in src
    assert "48" not in src.split("DisputeBlock")[1], "App 里出现了硬编码的 48 小时"
