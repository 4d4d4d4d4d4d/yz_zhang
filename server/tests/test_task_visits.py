"""SCN-120 一单多次上门的逐次回报（176 号 spec，V203）。

喂猫 7 天、每天两次：以前每次做了什么只能靠留言。现在发单时写「上门几次、每次要做的事」，
接单人每次交一条回报（勾清单、备注、照片），发单人收到通知、看得到计划几次、回报了几次、哪次漏了什么。
"""
from tests.conftest import auth, topup
from tests.test_task_flow import CLEAN_TASK, match_and_fund

API = "/api/v1/tasks"
CHECK = ["喂食", "换水", "铲屎"]


def _visit_task(client, requester, worker, **kw):
    topup(client, requester, 40000)
    r = client.post(API, json={**CLEAN_TASK, "category": "跑腿", "visits_planned": 14,
                               "visit_checklist": [" 喂食", "换水", "铲屎", "换水", ""], **kw}, headers=auth(requester))
    assert r.status_code == 201, r.text
    t = r.json()
    match_and_fund(client, requester, worker, t)
    return t


def test_checklist_is_cleaned_and_public(client, requester, worker):
    t = _visit_task(client, requester, worker)
    assert t["visits_planned"] == 14 and t["visit_checklist"] == CHECK, "去空白、去空项、去重"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(t, "Task")
    r = client.post(API, json={**CLEAN_TASK, "visit_checklist": ["把猫砂盆里的结块全部铲干净并且换上新的猫砂"]},
                    headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "visit_item_too_long"


def test_each_visit_report_tells_the_poster_what_was_done_and_missed(client, requester, worker):
    t = _visit_task(client, requester, worker)
    r = client.post(f"{API}/{t['id']}/visits", json={"done": ["铲屎", "喂食"], "note": "猫很精神"}, headers=auth(worker))
    assert r.status_code == 201, r.text
    assert r.json() == {"n": 1, "id": r.json()["id"], "done": ["喂食", "铲屎"], "missed": ["换水"]}, "按清单顺序"
    client.post(f"{API}/{t['id']}/visits", json={"done": CHECK}, headers=auth(worker))
    notes = client.get("/api/v1/notifications", headers=auth(requester)).json()
    first = next(n for n in notes if n["title"] == "第 1/14 次上门回报")
    assert "已做：喂食、铲屎；没做：换水" in first["body"] and "猫很精神" in first["body"]
    assert any(n["title"] == "第 2/14 次上门回报" for n in notes)
    v = client.get(f"{API}/{t['id']}/visits", headers=auth(requester)).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(v, "TaskVisits")
    _assert_shape(v["visits"][0], "TaskVisit")
    assert v["planned"] == 14 and v["reported"] == 2 and v["missed_total"] == 1
    assert [x["missed"] for x in v["visits"]] == [["换水"], []]
    # 进展记录里也有这两条（证据包、纠纷照常能看到）
    kinds = [x["kind"] for x in client.get(f"{API}/{t['id']}/progress", headers=auth(requester)).json()]
    assert kinds.count("visit") == 2


def test_only_the_executor_reports_only_while_working_and_only_listed_items(client, requester, worker):
    t = _visit_task(client, requester, worker)
    assert client.post(f"{API}/{t['id']}/visits", json={"done": ["喂食"]}, headers=auth(requester)).status_code == 403
    r = client.post(f"{API}/{t['id']}/visits", json={"done": ["遛狗"]}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "visit_item_unknown"
    r = client.post(f"{API}/{t['id']}/visits", json={}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "visit_empty"
    r = client.post(f"{API}/{t['id']}/visits", json={"done": ["喂食"], "images": ["https://evil/x.png"]}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_image_url"
    client.post(f"{API}/{t['id']}/deliver", headers=auth(worker))
    r = client.post(f"{API}/{t['id']}/visits", json={"done": ["喂食"]}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_in_progress"


def test_visits_are_only_visible_to_the_two_parties(client, requester, worker):
    from tests.conftest import register

    t = _visit_task(client, requester, worker)
    outsider = register(client, "13800000399", "路人")
    assert client.get(f"{API}/{t['id']}/visits", headers=auth(outsider)).status_code == 403
    assert client.get(f"{API}/{t['id']}/visits", headers=auth(worker)).status_code == 200


def test_a_task_without_a_checklist_still_takes_a_note_or_photo(client, requester, worker):
    t = _visit_task(client, requester, worker, visits_planned=0, visit_checklist=[])
    r = client.post(f"{API}/{t['id']}/visits", json={"note": "到了，一切正常"}, headers=auth(worker))
    assert r.status_code == 201 and r.json()["missed"] == []
    notes = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any(n["title"] == "第 1 次上门回报" for n in notes), "没写计划次数时不写「/0」"


def test_slots_carry_the_checklist(client, requester):
    r = client.post(API, json={**CLEAN_TASK, "category": "跑腿", "people_needed": 2, "visits_planned": 3,
                               "visit_checklist": CHECK}, headers=auth(requester))
    assert r.status_code == 201, r.text
    assert all(s["visits_planned"] == 3 and s["visit_checklist"] == CHECK for s in r.json()["slots"])
