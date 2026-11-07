"""AGT-093 从编排复盘一步蒸馏成「我的方法」（154 号 spec）。

此前要先存笔记、再到知识库里选笔记蒸馏，而编排步骤本来就是结构化的——不必从文字里再猜一遍。
"""
from tests.conftest import auth, make_admin, topup
from tests.test_orchestrator import _finish_task, _mission

API = "/api/v1/missions"


def test_distill_takes_only_the_steps_that_got_done_in_order(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_shape

    topup(client, requester, 300000)
    m = _mission(client, requester, cap=200000, goal="装修验收统筹")
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    steps = client.get(f"{API}/{m['id']}", headers=auth(requester)).json()["steps"]
    first, rest = steps[0], steps[1:]
    client.post(f"/api/v1/tasks/{first['task_id']}/cancel", headers=auth(requester))   # 这一步失败，之后整改
    for s in rest:
        _finish_task(client, requester, worker, s["task_id"])
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    after = client.get(f"{API}/{m['id']}", headers=auth(requester)).json()["steps"]
    remedy = [s for s in after if s["is_remedy"]][0]
    _finish_task(client, requester, worker, remedy["task_id"])
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    d = client.post(f"{API}/{m['id']}/summary/distill", headers=auth(requester)).json()
    _assert_shape(d, "MissionMethodDraft")
    assert d["name"] == "装修验收统筹的做法" and d["found"] == "mission_steps"
    final = client.get(f"{API}/{m['id']}", headers=auth(requester)).json()["steps"]
    done = [s for s in final if s["status"] == "done"]
    assert [x["title"] for x in d["steps"]] == [s["title"] for s in done], "只收做成了的步骤，按顺序"
    with_acc = [s for s in done if s.get("acceptance")]
    if with_acc:
        assert next(x for x in d["steps"] if x["title"] == with_acc[0]["title"])["note"].startswith(with_acc[0]["acceptance"][0])
    # 出处是存进知识库的那条复盘笔记；再蒸馏一次不会多出一条
    assert d["source_note_ids"] == [d["note_id"]] and d["note_title"].startswith("编排复盘：")
    again = client.post(f"{API}/{m['id']}/summary/distill", headers=auth(requester)).json()
    assert again["note_id"] == d["note_id"]
    # 只是草稿：确认后走「保存为我的方法」
    assert client.get("/api/v1/notebook/methods", headers=auth(requester)).json() == []
    saved = client.post("/api/v1/notebook/methods", json={"name": d["name"], "steps": d["steps"],
                                                         "source_note_ids": d["source_note_ids"]}, headers=auth(requester))
    assert saved.status_code == 201 and len(saved.json()["steps"]) == len(d["steps"])


def test_nothing_done_yet_says_so(client, requester):
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="还没开始的事")
    d = client.post(f"{API}/{m['id']}/summary/distill", headers=auth(requester)).json()
    assert d["steps"] == [] and d["found"] == "none" and d["skipped_steps"] == 0


def test_only_the_owner_can_distill(client, requester, worker):
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="别人的编排")
    assert client.post(f"{API}/{m['id']}/summary/distill", headers=auth(worker)).status_code == 403
    admin = make_admin(client, "13800290001", "运营")
    assert client.post(f"{API}/{m['id']}/summary/distill", headers=auth(admin)).status_code == 403


def test_steps_still_in_progress_are_left_out_and_counted(client, requester, worker):
    topup(client, requester, 300000)
    m = _mission(client, requester, cap=200000, goal="活动执行统筹")
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    steps = client.get(f"{API}/{m['id']}", headers=auth(requester)).json()["steps"]
    assert len(steps) >= 2
    _finish_task(client, requester, worker, steps[1]["task_id"])
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    now = {s["id"]: s for s in client.get(f"{API}/{m['id']}", headers=auth(requester)).json()["steps"]}
    assert now[steps[0]["id"]]["status"] != "done" and now[steps[1]["id"]]["status"] == "done"
    d = client.post(f"{API}/{m['id']}/summary/distill", headers=auth(requester)).json()
    titles = [x["title"] for x in d["steps"]]
    assert steps[1]["title"] in titles and steps[0]["title"] not in titles
    assert d["skipped_steps"] >= 1
