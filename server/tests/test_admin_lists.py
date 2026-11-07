"""ADMIN-061 审计日志与 PAY-043 提现复核台：筛选、总数、导出（143 号 spec）；TZ-068 导出时间写明时区。

两张都是合规与资金运营每天要开的页面。条目一多，「谁批了那笔三万块」「上个月哪些人改过角色」
就只剩翻页；监管调取要的是一份**带时区**的文件，而不是截图。
"""
from datetime import datetime, timedelta

from app.core.db import SessionLocal
from app.core.timefmt import EXPORT_TZ_LABEL, export_time
from app.modules.account.models import User
from app.modules.admin.models import AdminAudit
from tests.conftest import auth, make_admin, register

API = "/api/v1"


def _admin(client, phone, roles=None):
    a = make_admin(client, phone, f"管理员{phone[-2:]}")
    if roles is not None:
        with SessionLocal() as db:
            db.get(User, a["id"]).admin_roles = roles
            db.commit()
    return a


def _seed_audits(a1, a2):
    base = datetime(2026, 10, 1, 0, 0, 0)
    with SessionLocal() as db:
        db.add_all([
            AdminAudit(admin_id=a1, action="withdraw_approve", target_type="withdraw", target_id=7, detail="大额 3 万", created_at=base),
            AdminAudit(admin_id=a1, action="ban_user", target_type="user", target_id=9, detail="刷单", created_at=base + timedelta(days=2)),
            AdminAudit(admin_id=a2, action="withdraw_approve", target_type="withdraw", target_id=8, detail="小额", created_at=base + timedelta(days=5)),
        ])
        db.commit()


def test_export_time_is_beijing_time():
    assert export_time(datetime(2026, 10, 14, 0, 30)) == "2026-10-14 08:30:00"
    assert export_time(None) == "" and "UTC+8" in EXPORT_TZ_LABEL


def test_audit_log_filters_and_total(client):
    a1 = _admin(client, "13800230001", ["compliance"])
    a2 = _admin(client, "13800230002")
    _seed_audits(a1["id"], a2["id"])
    h = auth(a1)
    url = f"{API}/admin/audit-log"
    r = client.get(url, params={"admin_id": a1["id"]}, headers=h)
    assert r.headers["X-Total-Count"] == "2" and [x["action"] for x in r.json()] == ["ban_user", "withdraw_approve"]
    assert [x["target_id"] for x in client.get(url, params={"target_type": "withdraw", "target_id": 8}, headers=h).json()] == [8]
    assert [x["target_id"] for x in client.get(url, params={"since": "2026-10-02T00:00:00Z", "until": "2026-10-04T00:00:00Z"},
                                                headers=h).json()] == [9]
    # 带时区的入参按 UTC 换算：北京时间 10-06 00:00 = UTC 10-05 16:00
    assert [x["target_id"] for x in client.get(url, params={"since": "2026-10-06T00:00:00+08:00"}, headers=h).json()
            if x["target_type"] == "withdraw"] == [8]
    assert [x["target_id"] for x in client.get(url, params={"q": "3 万"}, headers=h).json()] == [7]
    page = client.get(url, params={"action": "withdraw_approve", "limit": 1, "offset": 1}, headers=h)
    assert page.headers["X-Total-Count"] == "2" and [x["target_id"] for x in page.json()] == [7]


def test_audit_export_labels_the_timezone_and_is_itself_audited(client, monkeypatch):
    a1 = _admin(client, "13800230003", ["compliance"])
    a2 = _admin(client, "13800230004")
    _seed_audits(a1["id"], a2["id"])
    r = client.get(f"{API}/admin/audit-log/export", params={"action": "withdraw_approve"}, headers=auth(a1)).json()
    lines = r["csv"].strip().splitlines()
    assert lines[0].startswith("时间（北京时间 UTC+8）,管理员编号,管理员昵称")
    assert lines[1].startswith("2026-10-06 08:00:00,") and lines[2].startswith("2026-10-01 08:00:00,")
    assert r["rows"] == 2 and r["total"] == 2 and r["truncated"] is False and r["timezone"] == EXPORT_TZ_LABEL
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r, "AuditLogExport")
    with SessionLocal() as db:
        ex = db.query(AdminAudit).filter(AdminAudit.action == "export_audit_log").one()
        assert ex.admin_id == a1["id"] and "2 行" in ex.detail and "withdraw_approve" in ex.detail
    from app.modules.admin import router as admin_router

    monkeypatch.setattr(admin_router, "AUDIT_EXPORT_MAX", 1)
    cut = client.get(f"{API}/admin/audit-log/export", headers=auth(a1)).json()
    assert cut["rows"] == 1 and cut["truncated"] is True and cut["total"] >= 3


def test_audit_log_is_compliance_only(client):
    sup = _admin(client, "13800230005", ["support"])
    for path in ("/admin/audit-log", "/admin/audit-log/export"):
        r = client.get(f"{API}{path}", headers=auth(sup))
        assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_role_required"


def _seed_withdraws(u1, u2):
    from app.modules.aml.models import SuspiciousActivity
    from app.modules.wallet.models import WithdrawRequest

    with SessionLocal() as db:
        rows = [WithdrawRequest(user_id=u1, amount_cents=500_00, status="pending"),
                WithdrawRequest(user_id=u2, amount_cents=30_000_00, status="pending"),
                WithdrawRequest(user_id=u1, amount_cents=8_000_00, status="pending"),
                WithdrawRequest(user_id=u2, amount_cents=9_000_00, status="rejected")]
        db.add_all(rows)
        db.flush()
        db.add(SuspiciousActivity(user_id=u1, pattern="structuring", detail="7 天内 3 笔", amount_cents=8_000_00,
                                  ref_type="withdraw_request", ref_id=rows[2].id))
        db.commit()
        return [r.id for r in rows]


def test_withdraw_queue_filters_sort_and_total(client):
    fin = _admin(client, "13800230006", ["finance"])
    u1, u2 = register(client, "13800230007", "甲"), register(client, "13800230008", "乙")
    ids = _seed_withdraws(u1["id"], u2["id"])
    url, h = f"{API}/wallet/withdraw-requests", auth(fin)
    r = client.get(url, headers=h)
    assert r.headers["X-Total-Count"] == "3" and [x["id"] for x in r.json()] == ids[:3], "默认：待处理的、先来先审"
    assert [x["id"] for x in client.get(url, params={"sort": "largest"}, headers=h).json()] == [ids[1], ids[2], ids[0]]
    assert [x["id"] for x in client.get(url, params={"user_id": u1["id"]}, headers=h).json()] == [ids[0], ids[2]]
    assert [x["id"] for x in client.get(url, params={"min_amount_cents": 800_000}, headers=h).json()] == [ids[1], ids[2]]
    flagged = client.get(url, params={"flagged_only": True}, headers=h)
    assert flagged.headers["X-Total-Count"] == "1" and [x["id"] for x in flagged.json()] == [ids[2]]
    assert flagged.json()[0]["flags"][0]["pattern"] == "structuring"
    assert client.get(url, params={"sort": "newest"}, headers=h).status_code == 422
