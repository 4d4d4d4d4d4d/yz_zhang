"""V21 批判性扫描：真双盲评分（旁道泄露修复）+ 变更单条款附录 + 换绑手机 + 平台公告。

重点是第一项——上轮双盲只盲了"内容可见性"，但 record_review 在提交即更新对方
rating_avg/信用分，对方看自己主页分数变化就能反推星级，然后窗口内报复。
真双盲要求评分聚合同样延迟到公开时点。
"""
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import engine
from app.modules.account.models import utcnow

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _make_admin(client, phone):
    admin = register(client, phone, "管理员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def _complete(client, requester, worker, title="评分单"):
    topup(client, requester, 20000)
    task = publish_task(client, requester, title=title)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    return task


def _rating(client, u):
    return client.get("/api/v1/users/me", headers=auth(u)).json()["rating_avg"]


# ---------- CRED-002 真双盲：评分延迟到公开时点 ----------
def test_rating_not_leaked_before_reveal(client, requester, worker):
    task = _complete(client, requester, worker)
    before = _rating(client, worker)

    # 发布者先评执行者 1 星：若立即入账，执行者查主页 rating_avg 会掉 → 反推被差评
    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 1, "comment": "较差"}, headers=auth(requester))
    assert _rating(client, worker) == before  # 未泄露：评分尚未入账

    # 执行者回评后双方公开 → 评分同时结算
    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 5, "comment": "还行"}, headers=auth(worker))
    assert _rating(client, worker) == 1.0  # 现在才入账


def test_rating_settles_on_window_expiry_single_review(client, requester, worker):
    task = _complete(client, requester, worker, title="窗口结算单")
    before = _rating(client, worker)
    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 2}, headers=auth(requester))
    assert _rating(client, worker) == before  # 窗口内不入账

    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE tasks SET completed_at = :d WHERE id = :t"),
                     {"d": utcnow() - timedelta(days=settings.REVIEW_WINDOW_DAYS + 1),
                      "t": task["id"]})
    # 兜底 job 结算（无人读取也按时入账）
    r = client.post("/api/v1/tasks/jobs/settle-reviews")
    assert r.json()["settled"] == 1
    assert _rating(client, worker) == 2.0
    # 幂等：重跑不重复入账
    assert client.post("/api/v1/tasks/jobs/settle-reviews").json()["settled"] == 0
    assert _rating(client, worker) == 2.0


# ---------- SC-007 变更单条款附录 ----------
def test_change_order_appends_terms_addendum(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=20000, title="改价文书单")
    cid = match_and_fund(client, requester, worker, task)
    oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                      json={"new_amount_cents": 30000, "reason": "增加清洁范围"},
                      headers=auth(requester)).json()["id"]
    client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))

    export = client.get(f"/api/v1/contracts/{cid}/export", headers=auth(requester)).json()
    text = export["text"]
    # 导出文书须体现新金额与变更附录，而非停留在原始 200 元
    assert "变更附录 v2" in text and "300.00 元" in text and "增加清洁范围" in text


# ---------- ACC-008 换绑手机 ----------
def test_change_phone_requires_code_and_password(client):
    u = register(client, "25000000001", "换绑者")

    # 错误密码
    r = client.post("/api/v1/auth/change-phone",
                    json={"new_phone": "25000009999", "sms_code": "123456", "password": "wrong"},
                    headers=auth(u))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_password"

    # 目标号已被占用
    register(client, "25000000002", "占位者")
    r = client.post("/api/v1/auth/change-phone",
                    json={"new_phone": "25000000002", "sms_code": "123456", "password": "pass123456"},
                    headers=auth(u))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "phone_taken"

    # 成功换绑 → 新号可登录，旧号不可
    r = client.post("/api/v1/auth/change-phone",
                    json={"new_phone": "25000009999", "sms_code": "123456", "password": "pass123456"},
                    headers=auth(u))
    assert r.status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"phone": "25000009999", "password": "pass123456"}).status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"phone": "25000000001", "password": "pass123456"}).status_code == 400


# ---------- OPS-009 平台公告 ----------
def test_platform_announcement_broadcast(client, requester):
    admin = _make_admin(client, "25000000010")
    unverified = register(client, "25000000011", "未实名者")  # 不做实名

    r = client.post("/api/v1/admin/announcements",
                    json={"title": "平台维护通知", "body": "今晚 02:00 例行维护"},
                    headers=auth(admin))
    assert r.json()["delivered"] >= 2
    for u in (requester, unverified):
        notices = client.get("/api/v1/notifications", headers=auth(u)).json()
        assert any(n["title"] == "平台维护通知" for n in notices)

    # 仅实名：未实名者收不到
    client.post("/api/v1/admin/announcements",
                json={"title": "资金合规公告", "verified_only": True}, headers=auth(admin))
    assert any(n["title"] == "资金合规公告"
               for n in client.get("/api/v1/notifications", headers=auth(requester)).json())
    assert not any(n["title"] == "资金合规公告"
                   for n in client.get("/api/v1/notifications", headers=auth(unverified)).json())

    # 普通用户不能发公告
    assert client.post("/api/v1/admin/announcements",
                       json={"title": "冒充"}, headers=auth(unverified)).status_code == 403
