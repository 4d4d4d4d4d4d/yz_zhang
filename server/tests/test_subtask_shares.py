"""AI-DEC-024 跨子任务产出共享（321 号 spec，V348）：前一步的交付人授权后，后一步的执行者才看得到。

一个项目拆成几步，后一步常常要前一步的成果，以前只能私下传。可前一个人的交付物给不给后一个人看是他的权利：
默认谁也看不到；交付人交了之后才能开、只能开给依赖这一步的那几步、随时收回；开放的是交付说明与预览图，原图不在里面。
"""
from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from tests.conftest import auth, topup
from tests.test_certification import make_verified
from tests.test_cockpit import _confirmed
from tests.test_contract_deliverables import _upload
from tests.test_task_flow import match_and_fund

API = "/api/v1"


def _chain(client, requester, worker):
    """拆好的项目里取一对相邻的两步（后一步依赖前一步）；前一步由 worker 接了并托管。后一步要等前一步完成才开招。"""
    topup(client, requester, 2_000_000)
    t = _confirmed(client, requester)
    cp = client.get(f"{API}/tasks/{t['id']}/cockpit", headers=auth(requester)).json()
    first_id, second_id = cp["critical_path"][0], cp["critical_path"][1]
    others = [n["id"] for n in cp["nodes"] if n["id"] not in (first_id, second_id) and first_id not in n["depends_on"]]
    first = client.get(f"{API}/tasks/{first_id}", headers=auth(requester)).json()
    second = client.get(f"{API}/tasks/{second_id}", headers=auth(requester)).json()
    cid = match_and_fund(client, requester, worker, first)
    return first, second, others, cid


def _finish_first_and_staff_second(client, requester, first, second):
    assert client.post(f"{API}/tasks/{first['id']}/accept-delivery", headers=auth(requester)).status_code == 200
    second = client.get(f"{API}/tasks/{second['id']}", headers=auth(requester)).json()
    assert second["status"] == "published", second["status"]
    nxt = make_verified(client, "13600003481", nick="后一步的人")
    match_and_fund(client, requester, nxt, second)
    return nxt


def _told(user_id: int, part: str) -> int:
    with SessionLocal() as db:
        return db.query(Notification).filter(Notification.user_id == user_id, Notification.title.like(f"%{part}%")).count()


def test_the_deliverer_opens_delivery_notes_and_previews_to_the_next_step_and_can_take_them_back(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_shape

    first, second, _, cid = _chain(client, requester, worker)
    S = f"{API}/tasks/{first['id']}/shares"
    view = client.get(S, headers=auth(worker)).json()
    _assert_shape(view, "SubtaskShareView")
    assert view["delivered"] is False
    row = next(r for r in view["next_steps"] if r["task_id"] == second["id"])
    _assert_shape(row, "SubtaskNextStep")
    assert row["shared"] is False and "share_id" not in row and row["executor_nickname"] is None, "后一步还没人接"
    r = client.post(S, json={"to_task_id": second["id"]}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_delivered", "还没交付，没有东西可开"
    pre, orig = _upload(client, worker, b"\x31"), _upload(client, worker, b"\x32")
    D = f"{API}/contracts/{cid}/deliverables"
    assert client.post(D, json={"ref": pre, "kind": "preview"}, headers=auth(worker)).status_code == 201
    assert client.post(D, json={"ref": orig, "kind": "original"}, headers=auth(worker)).status_code == 201
    client.post(f"{API}/tasks/{first['id']}/progress", json={"content": "和发单人私下说的话"}, headers=auth(worker))
    assert client.post(f"{API}/tasks/{first['id']}/deliver", json={"note": "需求文档在预览图里，接口约定见第 3 页"},
                       headers=auth(worker)).status_code == 200
    nxt = _finish_first_and_staff_second(client, requester, first, second)
    assert client.get(f"{API}/tasks/{second['id']}/inputs", headers=auth(nxt)).json() == [], "默认谁也看不到"
    r = client.post(S, json={"to_task_id": second["id"]}, headers=auth(worker))
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["next_steps"] if x["task_id"] == second["id"])
    assert r.json()["delivered"] is True and row["shared"] is True and row["share_id"]
    assert row["executor_nickname"] == "后一步的人", "交付人看得见现在是谁在做后一步"
    again = client.post(S, json={"to_task_id": second["id"]}, headers=auth(worker)).json()
    assert next(x for x in again["next_steps"] if x["task_id"] == second["id"])["share_id"] == row["share_id"], "再点一次不重复开"
    assert _told(nxt["id"], f"前一步「{first['title']}」的成果开放给你了") == 1
    got = client.get(f"{API}/tasks/{second['id']}/inputs", headers=auth(nxt)).json()
    assert len(got) == 1
    _assert_shape(got[0], "SubtaskInput")
    assert got[0]["from_task_id"] == first["id"]
    assert [d["content"] for d in got[0]["deliveries"]] == ["需求文档在预览图里，接口约定见第 3 页"], "只给交付说明，进度备注不在里面"
    assert [p["url"] for p in got[0]["previews"]] == [f"/api/v1/files/{pre}"], "只给预览图，原图不在里面"
    assert client.get(f"{API}/tasks/{second['id']}/inputs", headers=auth(requester)).status_code == 200, "发单人也看得到"
    r = client.delete(f"{S}/{row['share_id']}", headers=auth(worker))
    assert r.status_code == 200 and next(x for x in r.json()["next_steps"] if x["task_id"] == second["id"])["shared"] is False
    assert client.get(f"{API}/tasks/{second['id']}/inputs", headers=auth(nxt)).json() == [], "收回后立刻看不到"
    assert _told(nxt["id"], "的成果已收回") == 1
    assert client.delete(f"{S}/{row['share_id']}", headers=auth(worker)).status_code == 404, "收回过的不能再收"


def test_only_the_deliverer_opens_only_to_steps_that_depend_on_it(client, requester, worker):
    first, second, others, _ = _chain(client, requester, worker)
    S = f"{API}/tasks/{first['id']}/shares"
    client.post(f"{API}/tasks/{first['id']}/deliver", json={"note": "交了"}, headers=auth(worker))
    nxt = _finish_first_and_staff_second(client, requester, first, second)
    for who in (requester, nxt):
        r = client.post(S, json={"to_task_id": second["id"]}, headers=auth(who))
        assert r.status_code == 403, "发单人、后一步的人都不能替交付人开"
    assert client.get(S, headers=auth(nxt)).status_code == 403, "后一步的人看不到前一步的开放列表"
    assert client.get(S, headers=auth(requester)).status_code == 200, "发单人看得到谁开给了谁"
    stranger = make_verified(client, "13600003482", nick="路人")
    assert client.get(f"{API}/tasks/{second['id']}/inputs", headers=auth(stranger)).status_code == 403
    for bad in [*others[:1], first["id"]]:
        r = client.post(S, json={"to_task_id": bad}, headers=auth(worker))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "share_not_next_step", "只能开给依赖这一步的"
    share_id = next(x for x in client.post(S, json={"to_task_id": second["id"]}, headers=auth(worker)).json()["next_steps"]
                    if x["task_id"] == second["id"])["share_id"]
    S2 = f"{API}/tasks/{second['id']}/shares/{share_id}"
    assert client.delete(S2, headers=auth(nxt)).status_code in (403, 404), "别的任务名下收不回"
    assert client.delete(f"{S}/{share_id}", headers=auth(nxt)).status_code == 403, "只有交付人能收回"
    assert client.delete(f"{S}/{share_id}", headers=auth(requester)).status_code == 403, "发单人也不能替交付人收回"
