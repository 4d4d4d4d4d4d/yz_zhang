"""SCN-124 上门回报时带上到场打卡（195 号 spec，V222）。

以前回报与打卡是两件事：发单人看回报里「喂了、换了水」，到场没有要另去翻打卡记录，而网页上看不到打卡。
现在回报可以顺带交当前位置：与到场打卡同一套规则（打卡即位置同意、超出打卡半径就拒绝并写明差多远），
回报记成「到场（距 N 米）」；坐标按 GEO 规则在任务结束后清掉，距离留着当履约证据。
"""
from app.core.db import SessionLocal
from app.modules.task.models import ProgressLog
from tests.conftest import auth
from tests.test_task_visits import CHECK, _visit_task

API = "/api/v1/tasks"


def test_a_visit_with_location_counts_as_being_there(client, requester, worker):
    t = _visit_task(client, requester, worker)
    r = client.post(f"{API}/{t['id']}/visits", json={"done": CHECK, "lat": t["lat"] + 0.0005, "lng": t["lng"]},
                    headers=auth(worker))
    assert r.status_code == 201, r.text
    assert 40 <= r.json()["at_site_m"] <= 70, "约 55 米"
    client.post(f"{API}/{t['id']}/visits", json={"done": ["喂食"]}, headers=auth(worker))
    v = client.get(f"{API}/{t['id']}/visits", headers=auth(requester)).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(v["visits"][0], "TaskVisit")
    assert [x["at_site_m"] for x in v["visits"]] == [r.json()["at_site_m"], None], "没带位置的那次不算到场"
    note = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any("到场打卡（距任务地点" in n["body"] for n in note), "发单人收到的通知里写明到场"


def test_too_far_is_refused_with_the_distance_and_nothing_is_recorded(client, requester, worker):
    t = _visit_task(client, requester, worker)
    r = client.post(f"{API}/{t['id']}/visits", json={"done": CHECK, "lat": t["lat"] + 0.05, "lng": t["lng"]},
                    headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "too_far"
    assert "米" in r.json()["detail"]["message"] and "先不带位置交回报" in r.json()["detail"]["message"]
    assert client.get(f"{API}/{t['id']}/visits", headers=auth(requester)).json()["reported"] == 0


def test_location_must_come_as_a_pair_and_only_for_onsite_tasks(client, requester, worker):
    t = _visit_task(client, requester, worker)
    r = client.post(f"{API}/{t['id']}/visits", json={"done": CHECK, "lat": t["lat"]}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "visit_location_incomplete"
    remote = _visit_task(client, requester, worker, is_remote=True, lat=None, lng=None)
    r = client.post(f"{API}/{remote['id']}/visits", json={"done": CHECK, "lat": 31.2, "lng": 121.4}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_checkin_needed"


def test_coordinates_are_purged_after_the_task_ends_but_the_distance_stays(client, requester, worker):
    t = _visit_task(client, requester, worker)
    client.post(f"{API}/{t['id']}/visits", json={"done": CHECK, "lat": t["lat"], "lng": t["lng"]}, headers=auth(worker))
    with SessionLocal() as db:
        row = db.query(ProgressLog).filter(ProgressLog.task_id == t["id"], ProgressLog.kind == "visit").one()
        assert (row.lat, row.distance_m) == (t["lat"], 0)
    from datetime import timedelta

    from app.modules.account.models import utcnow
    from app.modules.task.models import Task
    from tests.conftest import JOB_HEADERS

    with SessionLocal() as db:   # 任务早已结束（只改状态，不走放款流程——这里只看坐标清理）
        task = db.get(Task, t["id"])
        task.status, task.completed_at = "completed", utcnow() - timedelta(days=60)
        db.commit()
    assert client.post(f"{API}/jobs/purge-locations", headers=JOB_HEADERS).status_code == 200
    with SessionLocal() as db:
        row = db.query(ProgressLog).filter(ProgressLog.task_id == t["id"], ProgressLog.kind == "visit").one()
        assert row.lat is None and row.lng is None and row.distance_m == 0
    assert client.get(f"{API}/{t['id']}/visits", headers=auth(requester)).json()["visits"][0]["at_site_m"] == 0


def test_plain_checkin_records_the_distance_too(client, requester, worker):
    t = _visit_task(client, requester, worker)
    assert client.post(f"{API}/{t['id']}/checkin", json={"lat": t["lat"], "lng": t["lng"]}, headers=auth(worker)).status_code == 201
    with SessionLocal() as db:
        assert db.query(ProgressLog).filter(ProgressLog.task_id == t["id"], ProgressLog.kind == "checkin").one().distance_m == 0


def test_an_onsite_task_without_coordinates_cannot_be_checked_in_against(client, requester, worker):
    """线下单却没有坐标（发布时必须给位置，只有早期数据会这样）：没有「任务地点」可比，不能算到场（与到场打卡一致）。"""
    from app.modules.task.models import Task

    t = _visit_task(client, requester, worker)
    with SessionLocal() as db:
        task = db.get(Task, t["id"])
        task.lat = task.lng = None
        db.commit()
    r = client.post(f"{API}/{t['id']}/visits", json={"done": CHECK, "lat": 31.2, "lng": 121.4}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_checkin_needed"
