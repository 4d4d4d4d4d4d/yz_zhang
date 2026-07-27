"""DSP-009/010 纠纷 SLA 与申诉窗口（业界惯例：处理时限硬约束 + 裁决终局性）。

纠纷冻结着托管资金：
- SLA：开立超 N 天未结案 → 自动升级（标记 + 管理员通知 + 人审工单），幂等，
  不自动裁决（资金裁决必须有人类经手）；
- 申诉窗口：仲裁结案后 N 天内可申诉，逾期裁决终局。
"""
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import engine
from app.modules.account.models import utcnow

from .conftest import JOB_HEADERS, auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _make_admin(client, phone):
    admin = register(client, phone, "仲裁员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def _open_dispute(client, requester, worker, title="纠纷单"):
    topup(client, requester, 20000)
    task = publish_task(client, requester, title=title)
    match_and_fund(client, requester, worker, task)
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付质量存在争议，申请平台介入"},
                    headers=auth(requester)).json()
    return task, d


def _backdate_dispute(did: int, days: float) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE disputes SET created_at = :d WHERE id = :i"),
                     {"d": utcnow() - timedelta(days=days), "i": did})


def test_overdue_dispute_escalates_once_fresh_untouched(client, requester, worker):
    admin = _make_admin(client, "21000000000")
    _, d_old = _open_dispute(client, requester, worker, title="超期纠纷")
    _backdate_dispute(d_old["id"], settings.DISPUTE_SLA_DAYS + 1)

    w2 = register(client, "21000000002", "执行者乙")
    verify_user(client, w2, "执行者乙")
    _, d_new = _open_dispute(client, requester, w2, title="新鲜纠纷")

    r = client.post("/api/v1/disputes/jobs/escalate-overdue", headers=JOB_HEADERS)
    assert r.json()["escalated"] == 1  # 只升级超期的

    got = client.get(f"/api/v1/disputes/{d_old['id']}", headers=auth(requester)).json()
    assert got["escalated"] is True and got["status"] == "open"  # 升级但不自动裁决
    assert client.get(f"/api/v1/disputes/{d_new['id']}",
                      headers=auth(requester)).json()["escalated"] is False
    # 管理员收到升级通知 + 生成人审工单
    notices = client.get("/api/v1/notifications", headers=auth(admin)).json()
    assert any("超期升级" in n["title"] for n in notices)
    tickets = client.get("/api/v1/admin/tickets", headers=auth(admin)).json()
    assert any("SLA超期" in t["subject"] for t in tickets)

    # 幂等：重跑不重复升级
    assert client.post("/api/v1/disputes/jobs/escalate-overdue", headers=JOB_HEADERS).json()["escalated"] == 0


def test_appeal_window_closes_verdict_becomes_final(client, requester, worker):
    admin = _make_admin(client, "21000000010")
    _, d = _open_dispute(client, requester, worker, title="申诉窗口单")
    client.post(f"/api/v1/disputes/{d['id']}/verdict",
                json={"executor_share_bps": 5000, "reason": "各担一半"},
                headers=auth(admin))

    # 把结案时间推到窗口外
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE disputes SET resolved_at = :d WHERE id = :i"),
                     {"d": utcnow() - timedelta(days=settings.APPEAL_WINDOW_DAYS + 1),
                      "i": d["id"]})

    r = client.post(f"/api/v1/disputes/{d['id']}/appeal", headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "appeal_window_closed"


def test_appeal_within_window_still_works(client, requester, worker):
    admin = _make_admin(client, "21000000020")
    _, d = _open_dispute(client, requester, worker, title="窗口内申诉单")
    client.post(f"/api/v1/disputes/{d['id']}/verdict",
                json={"executor_share_bps": 3000, "reason": "规则裁决"},
                headers=auth(admin))
    r = client.post(f"/api/v1/disputes/{d['id']}/appeal", headers=auth(worker))
    assert r.status_code == 200 and r.json()["status"] == "appealed"
