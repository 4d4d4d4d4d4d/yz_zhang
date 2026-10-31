"""SCN-139 已签的名额改时段时一键发合约变更单（207 号 spec，V235）。

V234 让发单人按天改时段：还在招的名额直接改；已经有人接的不动，只写明「要走合约变更单」——发单人得自己去合约页一张张发。
现在可以勾「顺带给对方发变更单」：替他发一张写明「哪天的时段由几点改为几点」的变更单，**对方同意后**名额的时段与标题才跟着改；
对方拒绝就不改。没签好合约、已有待处理变更单的，写明原因、不发。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.task.models import Task
from tests.conftest import auth, topup
from tests.test_multiday_slots import _post, _today
from tests.test_task_flow import match_and_fund

API = "/api/v1/tasks"


def _setup(client, requester, worker):
    topup(client, requester, 100000)
    start = _today() + timedelta(days=2)
    t = _post(client, requester, people_needed=1, days=2, start_date=start.isoformat(), shift_start="09:00", shift_end="18:00").json()
    slot = t["slots"][1]
    contract_id = match_and_fund(client, requester, worker, slot)
    return t, start + timedelta(days=1), slot["id"], contract_id


def test_taken_slot_gets_a_change_order_and_changes_only_after_the_other_side_agrees(client, requester, worker):
    t, d2, slot_id, cid = _setup(client, requester, worker)
    url = f"{API}/{t['id']}/days/{d2.isoformat()}/shift"
    r = client.patch(url, json={"shift_start": "10:00", "shift_end": "16:00", "propose_change": True}, headers=auth(requester))
    assert r.status_code == 200, r.text
    kept = r.json()["kept"][0]
    assert kept["task_id"] == slot_id and kept["change_order_id"] and "对方同意后生效" in kept["reason"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(kept, "DayShiftKept")
    with SessionLocal() as db:
        assert db.get(Task, slot_id).shift_start == "09:00", "对方没同意前不改"
    orders = client.get(f"/api/v1/contracts/{cid}/change-orders", headers=auth(worker)).json()
    mine = next(o for o in orders if o["id"] == kept["change_order_id"])
    assert f"{d2.isoformat()} 的时段由 09:00–18:00 改为 10:00–16:00" in mine["scope_change"]
    assert client.post(f"/api/v1/contracts/{cid}/change-orders/{mine['id']}/accept", headers=auth(worker)).status_code == 200
    md = f"{d2.month:02d}-{d2.day:02d}"
    with SessionLocal() as db:
        s = db.get(Task, slot_id)
        assert (s.shift_start, s.shift_end) == ("10:00", "16:00") and f"（{md} 10:00–16:00）" in s.title


def test_rejected_change_order_leaves_the_slot_alone_and_pending_one_blocks_another(client, requester, worker):
    t, d2, slot_id, cid = _setup(client, requester, worker)
    url = f"{API}/{t['id']}/days/{d2.isoformat()}/shift"
    first = client.patch(url, json={"shift_start": "10:00", "shift_end": "16:00", "propose_change": True}, headers=auth(requester)).json()
    again = client.patch(url, json={"shift_start": "11:00", "shift_end": "15:00", "propose_change": True}, headers=auth(requester)).json()
    assert again["kept"][0]["change_order_id"] is None and "待对方处理的变更单" in again["kept"][0]["reason"]
    oid = first["kept"][0]["change_order_id"]
    assert client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/reject", headers=auth(worker)).status_code == 200
    with SessionLocal() as db:
        assert db.get(Task, slot_id).shift_start == "09:00"
    plain = client.patch(url, json={"shift_start": "10:00", "shift_end": "16:00"}, headers=auth(requester)).json()
    assert plain["kept"][0]["change_order_id"] is None and "走合约变更单" in plain["kept"][0]["reason"], "不勾就不发"


def test_taken_but_not_signed_says_so(client, requester, worker):
    topup(client, requester, 100000)
    start = _today() + timedelta(days=2)
    t = _post(client, requester, people_needed=1, days=2, start_date=start.isoformat(), shift_start="09:00", shift_end="18:00").json()
    slot = t["slots"][1]
    app_id = client.post(f"{API}/{slot['id']}/applications", json={}, headers=auth(worker)).json()["id"]
    client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester))
    r = client.patch(f"{API}/{t['id']}/days/{(start + timedelta(days=1)).isoformat()}/shift",
                     json={"shift_start": "10:00", "shift_end": "16:00", "propose_change": True}, headers=auth(requester)).json()
    assert r["kept"][0]["change_order_id"] is None and "还没签好合约" in r["kept"][0]["reason"]
