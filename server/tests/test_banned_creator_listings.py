"""OPS-013 续：被封发布者的挂单必须下架，否则工人白报名空等。

V36 处理了在途合约；本批补未成交挂单——封禁后无人能选人，
留在广场是纯粹的用户时间浪费。
"""
import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, register, topup, verify_user
from .test_task_flow import publish_task


def _make_admin(client, phone):
    admin = register(client, phone, "管理员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def test_ban_closes_open_listings_and_rejects_applicants(client, requester, worker):
    admin = _make_admin(client, "35000000000")
    t1 = publish_task(client, requester, title="待下架挂单一")
    t2 = publish_task(client, requester, title="待下架挂单二")
    client.post(f"/api/v1/tasks/{t1['id']}/applications", json={}, headers=auth(worker))

    # 预览能看到挂单数
    pre = client.get(f"/api/v1/admin/users/{requester['id']}/ban-impact",
                     headers=auth(admin)).json()
    assert pre["open_task_count"] == 2

    r = client.post(f"/api/v1/admin/users/{requester['id']}/ban", headers=auth(admin))
    assert r.json()["impact"]["open_task_count"] == 2

    # 挂单被取消
    for t in (t1, t2):
        assert client.get(f"/api/v1/tasks/{t['id']}", headers=auth(worker)).json()["status"] == "cancelled"
    # 报名者被通知且报名关闭
    apps = client.get("/api/v1/users/me/applications", headers=auth(worker)).json()
    assert all(a["status"] == "rejected" for a in apps)
    notices = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any("已下架" in n["title"] for n in notices)
    # 审计记录下架数量
    log = client.get("/api/v1/admin/audit-log?action=ban_user", headers=auth(admin)).json()
    assert "下架挂单 2" in log[0]["detail"]


def test_square_excludes_banned_creator_tasks(client, requester, worker):
    admin = _make_admin(client, "35000000010")
    task = publish_task(client, requester, title="广场过滤单")
    ids = [t["id"] for t in client.get("/api/v1/tasks").json()]
    assert task["id"] in ids

    # 直接改库模拟历史遗留数据（绕过封禁流程的下架逻辑）
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_banned = 1 WHERE id = :i"),
                     {"i": requester["id"]})
    ids = [t["id"] for t in client.get("/api/v1/tasks").json()]
    assert task["id"] not in ids  # 广场防御性过滤


def test_cannot_apply_to_banned_creator_task(client, requester, worker):
    task = publish_task(client, requester, title="不可报名单")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_banned = 1 WHERE id = :i"),
                     {"i": requester["id"]})
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "creator_unavailable"
