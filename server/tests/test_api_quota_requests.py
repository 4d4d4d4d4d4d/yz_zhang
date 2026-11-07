"""API-057 接入方自己申请提额，运营在后台批（241 号 spec，V268）。

235 号让运营能给单个接入方调高账号配额，但接入方没有入口：只能找客服、发邮件，运营再手工去调。
现在接入方在开发者页写想要多少、多少天、干什么用；运营在后台看到申请（附现在的配额与最近 7 天用量最多的一天），
批准（可以改量与天数）或驳回（写理由）。批准的结果写进同一处账号配额，鉴权立刻按新配额算。
"""
from app.core import ratelimit
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from app.modules.openapi.models import ApiAccountQuota
from tests.conftest import auth
from tests.test_api_account_quota_override import API, OPEN
from tests.test_open_api_webhooks import api, make_key
from tests.test_ticket_assign_reply import _admin, _titles

DEV = f"{API}/developer/quota-requests"
ADM = f"{API}/admin/api-quota-requests"


def test_developer_applies_ops_approves_and_quota_takes_effect(client, requester, monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(settings, "API_KEY_DAILY_QUOTA", 100)
    monkeypatch.setattr(settings, "API_ACCOUNT_DAILY_QUOTA", 1)
    ops = _admin(client, "13800341001", ["ops"])
    assert client.post(DEV, json={"daily_quota": 5, "purpose": "接入店铺 ERP 同步订单"}, headers=auth(requester)).json()["detail"]["code"] \
        == "api_quota_request_no_key"
    k = make_key(client, requester)
    assert client.get(OPEN, headers=api(k["key"])).status_code == 200
    assert client.post(DEV, json={"daily_quota": 1, "purpose": "接入店铺 ERP 同步订单"}, headers=auth(requester)).json()["detail"]["code"] \
        == "api_quota_request_not_higher"
    r = client.post(DEV, json={"daily_quota": 5, "days": 30, "purpose": "接入店铺 ERP 同步订单"}, headers=auth(requester))
    assert r.status_code == 201 and r.json()["status"] == "pending"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "ApiQuotaRequest")
    again = client.post(DEV, json={"daily_quota": 9, "purpose": "接入店铺 ERP 同步订单"}, headers=auth(requester))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "api_quota_request_pending"
    rows = client.get(ADM, headers=auth(ops)).json()
    assert [(x["user_id"], x["daily_quota"], x["days"], x["current_quota"], x["peak_7d"]) for x in rows] == [(requester["id"], 5, 30, 1, 1)]
    _assert_shape(rows[0], "AdminApiQuotaRequest")
    ok = client.post(f"{ADM}/{r.json()['id']}/approve", json={"note": "先给 3 个月的量", "daily_quota": 3}, headers=auth(ops))
    assert ok.status_code == 200 and (ok.json()["status"], ok.json()["granted_quota"], ok.json()["granted_days"]) == ("approved", 3, 30)
    assert [client.get(OPEN, headers=api(k["key"])).status_code for _ in range(3)] == [200, 200, 429], "批准后立刻按 3 次算（今天已用 1）"
    with SessionLocal() as db:
        q = db.query(ApiAccountQuota).filter(ApiAccountQuota.user_id == requester["id"]).one()
        assert q.daily_quota == 3 and q.expires_at is not None and q.reason == f"按申请 #{r.json()['id']}：先给 3 个月的量"
        assert db.query(AdminAudit).filter(AdminAudit.action == "api_account_quota").count() == 1
    assert any("账号每日配额已调整" in t for t in _titles(client, requester))
    mine = client.get(DEV, headers=auth(requester)).json()
    assert mine[0]["status"] == "approved" and mine[0]["decision_note"] == "先给 3 个月的量"
    assert client.post(f"{ADM}/{r.json()['id']}/approve", json={}, headers=auth(ops)).json()["detail"]["code"] == "api_quota_request_decided"
    assert client.get(ADM, headers=auth(ops)).json() == [], "批过的不在待批里"
    assert len(client.get(f"{ADM}?status=all", headers=auth(ops)).json()) == 1
    export = client.get(f"{API}/users/me/export", headers=auth(requester)).json()
    assert export["api_quota_requests"][0]["granted_quota"] == 3


def test_reject_needs_reason_withdraw_and_permissions(client, requester, worker, monkeypatch):
    monkeypatch.setattr(settings, "API_ACCOUNT_DAILY_QUOTA", 1)
    ops = _admin(client, "13800341011", ["ops"])
    fin = _admin(client, "13800341012", ["finance"])
    make_key(client, requester)
    make_key(client, worker)
    a = client.post(DEV, json={"daily_quota": 50, "purpose": "批量导入历史任务数据"}, headers=auth(requester)).json()
    assert client.post(f"{ADM}/{a['id']}/reject", json={"note": "不"}, headers=auth(ops)).json()["detail"]["code"] \
        == "api_quota_reject_reason_required"
    no = client.post(f"{ADM}/{a['id']}/reject", json={"note": "用途写得不清楚，请补充每天大概调用哪些接口"}, headers=auth(ops))
    assert no.status_code == 200 and no.json()["status"] == "rejected"
    assert any("提额申请没有通过" in t for t in _titles(client, requester))
    with SessionLocal() as db:
        assert db.query(ApiAccountQuota).count() == 0, "驳回不动配额"
        assert db.query(AdminAudit).filter(AdminAudit.action == "api_quota_request_reject").count() == 1
    b = client.post(DEV, json={"daily_quota": 50, "purpose": "批量导入历史任务数据，每天约 40 次"}, headers=auth(requester)).json()
    assert client.delete(f"{DEV}/{b['id']}", headers=auth(worker)).status_code == 404, "别人的申请撤不了"
    assert client.delete(f"{DEV}/{b['id']}", headers=auth(requester)).json()["status"] == "withdrawn"
    assert client.delete(f"{DEV}/{b['id']}", headers=auth(requester)).json()["detail"]["code"] == "api_quota_request_decided"
    assert client.post(f"{ADM}/{b['id']}/approve", json={}, headers=auth(ops)).status_code == 409, "撤回的不能批"
    assert client.get(ADM, headers=auth(fin)).status_code == 403
    assert client.post(f"{ADM}/{b['id']}/reject", json={"note": "没权限的人"}, headers=auth(fin)).status_code == 403
    assert client.post(DEV, json={"daily_quota": 50, "purpose": "太短"}, headers=auth(requester)).status_code == 422
    assert client.get(DEV, headers=auth(worker)).json() == []
