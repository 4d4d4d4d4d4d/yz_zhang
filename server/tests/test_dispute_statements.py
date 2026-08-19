"""DSP-005 答辩举证与两造兼听：被诉方必须有陈述机会，仲裁员不得只听一面之词。

此前纠纷只有发起方的 reason + 系统自动快照，被诉方全程无渠道发声，
仲裁员据此就裁决分钱——程序正义硬伤。
"""
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import engine
from app.modules.account.models import utcnow

from .conftest import auth, register, respond_dispute, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _make_admin(client, phone):
    admin = register(client, phone, "仲裁员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def _open(client, requester, worker, title="答辩单"):
    topup(client, requester, 30000)
    task = publish_task(client, requester, title=title, budget_cents=20000)
    match_and_fund(client, requester, worker, task)
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付未达约定标准，申请平台介入"},
                    headers=auth(requester)).json()
    return task, d


def test_verdict_blocked_until_respondent_speaks(client, requester, worker):
    admin = _make_admin(client, "37000000000")
    _, d = _open(client, requester, worker)

    # 被诉方未答辩、答辩期未过 → 不得裁决
    r = client.post(f"/api/v1/disputes/{d['id']}/verdict",
                    json={"executor_share_bps": 0, "reason": "一面之词"},
                    headers=auth(admin))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "response_window_open"

    # 被诉方答辩后 → 可裁决
    respond_dispute(client, d["id"], worker, "我方已按约定完成，附交付截图。")
    r = client.post(f"/api/v1/disputes/{d['id']}/verdict",
                    json={"executor_share_bps": 5000, "reason": "两造陈述后各担一半"},
                    headers=auth(admin))
    assert r.status_code == 200 and r.json()["status"] == "resolved"


def test_default_judgment_after_response_window(client, requester, worker):
    """被诉方逾期不答辩 → 可缺席裁决，避免一方不出面就拖死流程。"""
    admin = _make_admin(client, "37000000010")
    _, d = _open(client, requester, worker, title="缺席裁决单")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE disputes SET created_at = :c WHERE id = :i"),
                     {"c": utcnow() - timedelta(hours=settings.DISPUTE_RESPONSE_HOURS + 1),
                      "i": d["id"]})
    r = client.post(f"/api/v1/disputes/{d['id']}/verdict",
                    json={"executor_share_bps": 2000, "reason": "被诉方逾期未答辩，缺席裁决"},
                    headers=auth(admin))
    assert r.status_code == 200


def test_statements_visible_to_parties_and_admin_only(client, requester, worker):
    admin = _make_admin(client, "37000000020")
    task, d = _open(client, requester, worker, title="陈述可见性单")
    respond_dispute(client, d["id"], worker, "我方说明如下：现场照片见附件。")
    client.post(f"/api/v1/disputes/{d['id']}/statements",
                json={"content": "发起方补充举证：验收标准见聊天记录。",
                      "attachments": ["https://example.com/a.jpg"]},
                headers=auth(requester))

    rows = client.get(f"/api/v1/disputes/{d['id']}/statements", headers=auth(worker)).json()
    assert [r["role"] for r in rows] == ["respondent", "opener"]
    assert rows[1]["attachments"] == ["https://example.com/a.jpg"]
    # 管理员可查
    assert len(client.get(f"/api/v1/disputes/{d['id']}/statements",
                          headers=auth(admin)).json()) == 2
    # 路人不可查
    stranger = register(client, "37000000021", "路人")
    verify_user(client, stranger, "路人甲")
    assert client.get(f"/api/v1/disputes/{d['id']}/statements",
                      headers=auth(stranger)).status_code == 403

    # 对方收到新陈述通知
    notices = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any("新陈述" in n["title"] for n in notices)


def test_no_statements_after_close(client, requester, worker):
    admin = _make_admin(client, "37000000030")
    _, d = _open(client, requester, worker, title="结案后禁言单")
    respond_dispute(client, d["id"], worker)
    client.post(f"/api/v1/disputes/{d['id']}/verdict",
                json={"executor_share_bps": 5000, "reason": "各担一半"}, headers=auth(admin))
    r = client.post(f"/api/v1/disputes/{d['id']}/statements",
                    json={"content": "结案后还想补充说明"}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "dispute_closed"
