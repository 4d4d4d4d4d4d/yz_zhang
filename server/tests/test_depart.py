"""SCN-122c 接单人「出发了」（364 号 spec，V392）。

替爸妈发单的人最常被问「人到哪了」。接单人点「出发了」并报预计几分钟到：发单人收到通知，
服务对象的进度链接页显示「已出发，预计几点到」，到达后这一行就不再显示。十分钟内再点只改时间、不再发通知。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.task import router as task_router
from app.modules.task.models import ProgressLog
from tests.conftest import auth, topup
from tests.test_on_behalf import ON_BEHALF, _post
from tests.test_task_flow import CLEAN_TASK, match_and_fund

API = "/api/v1"


def _matched(client, requester, worker, **kw):
    topup(client, requester, 40000)
    t = _post(client, requester, **kw).json()
    match_and_fund(client, requester, worker, t)
    return t


def test_departing_notifies_the_poster_and_shows_on_the_progress_link(client, requester, worker):
    t = _matched(client, requester, worker, **ON_BEHALF)
    token = client.post(f"{API}/tasks/{t['id']}/recipient-link", json={}, headers=auth(requester)).json()["token"]
    before = client.get(f"{API}/recipient-progress/{token}").json()
    assert before["departed_at"] is None and before["eta_at"] is None
    r = client.post(f"{API}/tasks/{t['id']}/depart", json={"eta_minutes": 30}, headers=auth(worker))
    assert r.status_code == 201, r.text
    d = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(d, "DepartResult")
    assert d["updated"] is False and d["eta_at"] > d["departed_at"]
    notes = client.get(f"{API}/notifications", headers=auth(requester)).json()
    assert any(n["title"] == "接单人已出发" and "预计" in n["body"] and "北京时间" in n["body"] for n in notes)
    v = client.get(f"{API}/recipient-progress/{token}").json()
    _assert_shape(v, "RecipientProgress")
    assert v["departed_at"] == d["departed_at"] and v["eta_at"] == d["eta_at"]
    # 到达之后不再显示「已出发」
    client.post(f"{API}/tasks/{t['id']}/visits", json={"note": "到了"}, headers=auth(worker))
    after = client.get(f"{API}/recipient-progress/{token}").json()
    assert after["departed_at"] is None and after["last_arrival_at"]


def test_departing_again_within_ten_minutes_only_moves_the_eta(client, requester, worker):
    t = _matched(client, requester, worker)
    first = client.post(f"{API}/tasks/{t['id']}/depart", json={"eta_minutes": 30}, headers=auth(worker)).json()
    again = client.post(f"{API}/tasks/{t['id']}/depart", json={"eta_minutes": 60}, headers=auth(worker)).json()
    assert again["updated"] is True and again["id"] == first["id"] and again["eta_at"] > first["eta_at"]
    notes = [n for n in client.get(f"{API}/notifications", headers=auth(requester)).json() if n["title"] == "接单人已出发"]
    assert len(notes) == 1, "十分钟内再点不再发第二条通知"
    with SessionLocal() as db:
        log = db.get(ProgressLog, first["id"])
        log.created_at = utcnow() - timedelta(minutes=task_router.DEPART_MERGE_MINUTES + 1)
        db.commit()
    third = client.post(f"{API}/tasks/{t['id']}/depart", json={"eta_minutes": 20}, headers=auth(worker)).json()
    assert third["updated"] is False and third["id"] != first["id"]


def test_only_the_executor_of_an_active_offline_task_can_depart(client, requester, worker):
    t = _matched(client, requester, worker)
    r = client.post(f"{API}/tasks/{t['id']}/depart", json={"eta_minutes": 30}, headers=auth(requester))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "depart_not_executor"
    for bad in (4, 241):
        assert client.post(f"{API}/tasks/{t['id']}/depart", json={"eta_minutes": bad}, headers=auth(worker)).status_code == 422
    client.post(f"{API}/tasks/{t['id']}/deliver", headers=auth(worker))
    client.post(f"{API}/tasks/{t['id']}/accept-delivery", headers=auth(requester))
    r = client.post(f"{API}/tasks/{t['id']}/depart", json={"eta_minutes": 30}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "depart_not_active"
    remote = client.post(f"{API}/tasks", json={**CLEAN_TASK, "is_remote": True, "category": "设计"}, headers=auth(requester)).json()
    match_and_fund(client, requester, worker, remote)
    r = client.post(f"{API}/tasks/{remote['id']}/depart", json={"eta_minutes": 30}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "depart_remote_task"
