"""API-058 新的提额申请提醒运营，久未处理再提醒（247 号 spec，V274）。

241 号的提额申请要运营打开后台才看得到：接入方配额用完就 429，申请躺着没人看等于业务停着。
现在提交时就通知运营；待批超过 48 小时还没处理，每天催一次（一笔一天最多一次），处理了就不再催。
"""
from datetime import timedelta

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.openapi.models import ApiQuotaRequest
from tests.conftest import JOB_HEADERS, auth
from tests.test_api_quota_requests import ADM, DEV
from tests.test_open_api_webhooks import make_key
from tests.test_ticket_assign_reply import _admin, _titles

JOB = "/api/v1/openapi/jobs/remind-quota-requests"


def _age(request_id: int, hours: int, reminded_hours_ago: int | None = None):
    with SessionLocal() as db:
        r = db.get(ApiQuotaRequest, request_id)
        r.created_at = utcnow() - timedelta(hours=hours)
        r.reminded_at = None if reminded_hours_ago is None else utcnow() - timedelta(hours=reminded_hours_ago)
        db.commit()


def test_ops_are_told_on_submit_and_reminded_after_48h_once_a_day(client, requester, worker, monkeypatch):
    monkeypatch.setattr(settings, "API_ACCOUNT_DAILY_QUOTA", 1)
    ops1 = _admin(client, "13800347001", ["ops"])
    ops2 = _admin(client, "13800347002", ["ops"])
    fin = _admin(client, "13800347003", ["finance"])
    make_key(client, requester)
    make_key(client, worker)
    a = client.post(DEV, json={"daily_quota": 50, "purpose": "接入店铺 ERP 同步订单"}, headers=auth(requester)).json()
    for o in (ops1, ops2):
        assert _titles(client, o).count("新的开放 API 提额申请") == 1
    assert "新的开放 API 提额申请" not in _titles(client, fin), "只叫运营"
    b = client.post(DEV, json={"daily_quota": 80, "purpose": "批量导入历史任务数据"}, headers=auth(worker)).json()
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "刚提交的不催"
    _age(a["id"], 49)
    _age(b["id"], 30)
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 1}, "只催等了 48 小时以上的"
    rows = client.get("/api/v1/notifications?limit=100", headers=auth(ops1)).json()
    rows = rows["items"] if isinstance(rows, dict) else rows
    body = [n for n in rows if n["title"] == "开放 API 提额申请等待处理"][0]["body"]
    assert f"#{a['id']}" in body and f"#{b['id']}" not in body and "最久 49 小时" in body
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "一天最多催一次"
    _age(a["id"], 75, reminded_hours_ago=25)
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 1}, "过了一天再催"
    client.post(f"{ADM}/{a['id']}/reject", json={"note": "用途写得不清楚"}, headers=auth(ops1))
    _age(a["id"], 100, reminded_hours_ago=30)
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "处理了就不再催"
    assert client.post(JOB).status_code in (401, 403)
