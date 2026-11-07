"""SCN-136 验收确认里写明「N 次回报里有 M 次到场」（204 号 spec，V230）。

V222 让回报可以带上到场打卡，但发单人验收时只看到「计划几次、回报几次、漏了几项」，看不出几次是真到了场。
现在上门回报的汇总多一个 `at_site`：几次回报带了到场打卡；线上单或没有任务坐标时打不了卡，是 null（不是 0 次）。
"""
from app.core.db import SessionLocal
from app.modules.task.models import Task
from tests.conftest import auth
from tests.test_client_shape_alignment import _assert_shape
from tests.test_task_visits import CHECK, _visit_task

API = "/api/v1/tasks"


def test_summary_counts_visits_with_a_checkin(client, requester, worker):
    t = _visit_task(client, requester, worker)
    v = client.get(f"{API}/{t['id']}/visits", headers=auth(requester)).json()
    assert (v["reported"], v["at_site"]) == (0, 0), "能打卡的单还没回报：0 次，不是 null"
    client.post(f"{API}/{t['id']}/visits", json={"done": CHECK, "lat": t["lat"], "lng": t["lng"]}, headers=auth(worker))
    client.post(f"{API}/{t['id']}/visits", json={"done": CHECK}, headers=auth(worker))
    client.post(f"{API}/{t['id']}/visits", json={"done": CHECK, "lat": t["lat"], "lng": t["lng"] + 0.0003}, headers=auth(worker))
    v = client.get(f"{API}/{t['id']}/visits", headers=auth(requester)).json()
    assert (v["reported"], v["at_site"]) == (3, 2)
    _assert_shape(v, "TaskVisits")


def test_tasks_that_cannot_check_in_say_null_not_zero(client, requester, worker):
    remote = _visit_task(client, requester, worker, is_remote=True, lat=None, lng=None)
    client.post(f"{API}/{remote['id']}/visits", json={"done": CHECK}, headers=auth(worker))
    v = client.get(f"{API}/{remote['id']}/visits", headers=auth(requester)).json()
    assert (v["reported"], v["at_site"]) == (1, None)
    with SessionLocal() as db:      # 线上单就算留了坐标也打不了卡（打卡接口会拒）
        row = db.get(Task, remote["id"])
        row.lat, row.lng = 31.23, 121.47
        db.commit()
    assert client.get(f"{API}/{remote['id']}/visits", headers=auth(requester)).json()["at_site"] is None
    onsite_no_coords = _visit_task(client, requester, worker)
    with SessionLocal() as db:      # 早期数据：线下单没留坐标
        row = db.get(Task, onsite_no_coords["id"])
        row.lat = row.lng = None
        db.commit()
    v = client.get(f"{API}/{onsite_no_coords['id']}/visits", headers=auth(requester)).json()
    assert v["at_site"] is None, "线下单却没有任务坐标：也打不了卡"
