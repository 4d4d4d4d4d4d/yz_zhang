"""PWB 个人工作台（116 号 spec）：我的任务、进度、进展记录、助手记忆与例行任务。

用户的要求：个人门户「至少能完成个人的任务和进度的维护」，助手参照 WorkBuddy（拆清单、记忆、定时任务）。
"""
from datetime import datetime, timedelta

import pytest

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.workbench import service as svc
from app.modules.workbench.models import WbItem, WbRoutine, WbRoutineRun
from tests.conftest import JOB_HEADERS, auth, register

API = "/api/v1/workbench"


def _item(client, user, **kw):
    r = client.post(f"{API}/items", json={"title": "整理报税材料", **kw}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ 任务与进度
def test_create_list_update_and_progress_log(client, requester):
    h = auth(requester)
    p = client.post(f"{API}/projects", json={"name": "家里的事"}, headers=h).json()
    it = _item(client, requester, project_id=p["id"], priority=2)
    assert it["status"] == "todo" and it["progress"] == 0 and it["progress_source"] == "manual"
    r = client.patch(f"{API}/items/{it['id']}", json={"status": "doing", "progress": 40,
                                                       "revision": it["revision"]}, headers=h)
    assert r.status_code == 200 and r.json()["progress"] == 40 and r.json()["status_name"] == "进行中"
    logs = client.get(f"{API}/items/{it['id']}/logs", headers=h).json()
    assert any("待办 → 进行中" in x["body"] for x in logs) and any("40%" in x["body"] for x in logs)
    client.post(f"{API}/items/{it['id']}/logs", json={"body": "银行流水已打印"}, headers=h)
    assert client.get(f"{API}/items/{it['id']}/logs", headers=h).json()[0]["body"] == "银行流水已打印"
    listed = client.get(f"{API}/items?project_id={p['id']}", headers=h).json()
    assert [x["id"] for x in listed] == [it["id"]]
    done = client.patch(f"{API}/items/{it['id']}", json={"status": "done"}, headers=h).json()
    assert done["progress"] == 100 and done["completed_at"]


def test_stale_revision_is_refused(client, requester):
    it = _item(client, requester)
    h = auth(requester)
    assert client.patch(f"{API}/items/{it['id']}", json={"title": "A", "revision": 0}, headers=h).status_code == 200
    r = client.patch(f"{API}/items/{it['id']}", json={"title": "B", "revision": 0}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "wb_revision_conflict"


def test_checklist_drives_progress_and_cannot_be_overridden(client, requester):
    h = auth(requester)
    it = _item(client, requester)
    r = client.post(f"{API}/items/{it['id']}/children", json={"steps": [{"title": "a"}, {"title": "b"}]}, headers=h)
    assert r.status_code == 201 and len(r.json()["children"]) == 2
    a = r.json()["children"][0]
    client.patch(f"{API}/items/{a['id']}", json={"status": "done"}, headers=h)
    got = client.get(f"{API}/items/{it['id']}", headers=h).json()
    assert got["progress"] == 50 and got["progress_source"] == "children" and got["children_done"] == 1
    r = client.patch(f"{API}/items/{it['id']}", json={"progress": 90}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "progress_from_children"
    # 清单只有一层
    r = client.post(f"{API}/items", json={"title": "孙子", "parent_id": a["id"]}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "only_one_level"


def test_views_today_and_overdue(client, requester):
    now = utcnow()
    _item(client, requester, title="昨天就该交", due_at=(now - timedelta(hours=30)).isoformat() + "Z")
    _item(client, requester, title="没有期限")
    h = auth(requester)
    overdue = client.get(f"{API}/items?view=overdue", headers=h).json()
    assert [x["title"] for x in overdue] == ["昨天就该交"]
    assert len(client.get(f"{API}/items?view=all", headers=h).json()) == 2
    assert [x["title"] for x in client.get(f"{API}/items?q=期限", headers=h).json()] == ["没有期限"]


# ------------------------------------------------------------------ 只对本人可见
def test_other_peoples_things_are_404(client, requester, worker):
    h, other = auth(requester), auth(worker)
    p = client.post(f"{API}/projects", json={"name": "私事"}, headers=h).json()
    it = _item(client, requester)
    m = client.post(f"{API}/memories", json={"content": "我习惯早上处理文书"}, headers=h).json()
    ro = client.post(f"{API}/routines", json={"name": "早报", "kind": "digest", "freq": "daily"}, headers=h).json()
    for method, path in (("get", f"/items/{it['id']}"), ("patch", f"/items/{it['id']}"),
                         ("delete", f"/items/{it['id']}"), ("get", f"/items/{it['id']}/logs"),
                         ("post", f"/items/{it['id']}/breakdown"), ("patch", f"/projects/{p['id']}"),
                         ("delete", f"/projects/{p['id']}"), ("delete", f"/memories/{m['id']}"),
                         ("patch", f"/routines/{ro['id']}"), ("post", f"/routines/{ro['id']}/run"),
                         ("get", f"/routines/{ro['id']}/runs")):
        kw = {"json": {}} if method in ("patch",) else {}
        r = getattr(client, method)(f"{API}{path}", headers=other, **kw)
        assert r.status_code == 404, (method, path, r.status_code)
    # 不能把任务挂到别人的项目下
    r = client.post(f"{API}/items", json={"title": "x", "project_id": p["id"]}, headers=other)
    assert r.status_code == 404
    assert client.get(f"{API}/items", headers=other).json() == []
    assert client.get(f"{API}/memories", headers=other).json()["items"] == []


def test_owner_cannot_be_set_by_the_client(client, requester, worker):
    r = client.post(f"{API}/items", json={"title": "x", "owner_id": worker["id"]}, headers=auth(requester))
    assert r.status_code == 422


# ------------------------------------------------------------------ 关联平台任务
def test_linking_a_platform_task_requires_being_a_party(client, requester, worker):
    from tests.test_task_flow import CLEAN_TASK

    t = client.post("/api/v1/tasks", json=CLEAN_TASK, headers=auth(requester)).json()
    r = client.post(f"{API}/items", json={"title": "盯一下", "linked_task_id": t["id"]}, headers=auth(worker))
    assert r.status_code == 404
    it = _item(client, requester, linked_task_id=t["id"])
    assert it["linked_task"]["id"] == t["id"] and it["progress_source"] == "platform"
    assert it["linked_task"]["status_name"] == "招募中"
    r = client.patch(f"{API}/items/{it['id']}", json={"progress": 30}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "progress_from_platform"


def test_overview_shows_platform_things_waiting_for_me(client, requester, worker):
    from tests.test_task_flow import CLEAN_TASK

    t = client.post("/api/v1/tasks", json=CLEAN_TASK, headers=auth(requester)).json()
    client.post(f"/api/v1/tasks/{t['id']}/applications", json={"message": "我来"}, headers=auth(worker))
    _item(client, requester, title="今天要做", due_at=(utcnow() + timedelta(minutes=5)).isoformat() + "Z")
    ov = client.get(f"{API}/overview", headers=auth(requester)).json()
    assert ov["platform"]["to_choose"][0]["task_id"] == t["id"] and ov["platform"]["to_choose"][0]["applicants"] == 1
    assert ov["counts"]["open"] == 1 and "等你选人" in ov["summary"]


# ------------------------------------------------------------------ 助手
def test_breakdown_is_a_draft_and_confirming_writes_children(client, requester):
    h = auth(requester)
    it = _item(client, requester)
    draft = client.post(f"{API}/items/{it['id']}/breakdown", headers=h).json()
    assert draft["steps"] and all(s["title"] for s in draft["steps"])
    assert client.get(f"{API}/items/{it['id']}", headers=h).json()["children"] == []   # 只是草稿
    r = client.post(f"{API}/items/{it['id']}/children", json={"steps": draft["steps"]}, headers=h)
    assert len(r.json()["children"]) == len(draft["steps"])
    assert any(x["kind"] == "assistant" for x in client.get(f"{API}/items/{it['id']}/logs", headers=h).json())


def test_breakdown_passes_memories_to_a_model_but_not_to_templates(client, requester, monkeypatch):
    from app.modules.decompose import llm

    seen = {}

    class FakeModel:
        def expand(self, db, ctx):
            seen["desc"] = ctx["root"]["description"]
            return {"children": [{"title": "先列清单", "deliverable": "清单", "acceptance": "逐项打勾"},
                                 {"title": "再动手"}], "source": "model", "model_call": True}

    h = auth(requester)
    client.post(f"{API}/memories", json={"content": "周末不安排工作"}, headers=h)
    it = _item(client, requester)
    monkeypatch.setattr(llm, "_gateway", FakeModel())
    draft = client.post(f"{API}/items/{it['id']}/breakdown", headers=h).json()
    assert "周末不安排工作" in seen["desc"] and draft["source"] == "model"
    assert draft["steps"][0]["note"] == "交付：清单；完成标准：逐项打勾"


def test_memories_are_capped(client, requester):
    h = auth(requester)
    for n in range(svc.LIMITS["memories"]):
        assert client.post(f"{API}/memories", json={"content": f"第{n}条"}, headers=h).status_code == 201
    r = client.post(f"{API}/memories", json={"content": "再来一条"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "wb_limit_reached"


# ------------------------------------------------------------------ 例行任务
def _routine(**kw):
    return WbRoutine(owner_id=1, name="r", kind="digest", **{"freq": "daily", "time_of_day": "09:00", **kw})


@pytest.mark.parametrize("routine, after, expect", [
    (dict(freq="daily"), "2026-10-13T00:30", "2026-10-13T01:00"),      # 北京 08:30 → 今天 09:00
    (dict(freq="daily"), "2026-10-13T01:00", "2026-10-14T01:00"),      # 正好 9 点跑过 → 明天
    (dict(freq="weekly", weekday=0), "2026-10-13T02:00", "2026-10-19T01:00"),   # 周二 → 下周一
    (dict(freq="monthly", monthday=31), "2026-02-01T00:00", "2026-02-28T01:00"),  # 小月按月末
    (dict(freq="monthly", monthday=31), "2026-01-31T02:00", "2026-02-28T01:00"),
])
def test_next_run_in_beijing_time(routine, after, expect):
    assert svc.next_run(_routine(**routine), datetime.fromisoformat(after)) == datetime.fromisoformat(expect)


def test_due_routine_runs_notifies_and_reschedules(client, requester):
    h = auth(requester)
    _item(client, requester, title="交房租", due_at=(utcnow() - timedelta(hours=1)).isoformat() + "Z")
    ro = client.post(f"{API}/routines", json={"name": "早报", "kind": "digest", "freq": "daily"}, headers=h).json()
    with SessionLocal() as db:
        r = db.get(WbRoutine, ro["id"])
        r.next_run_at = utcnow() - timedelta(minutes=1)
        db.commit()
    out = client.post(f"{API}/jobs/run-routines", headers=JOB_HEADERS).json()
    assert out["routines_ok"] == 1
    runs = client.get(f"{API}/routines/{ro['id']}/runs", headers=h).json()
    assert runs[0]["status"] == "ok" and "已逾期 1 项" in runs[0]["output"]
    notes = client.get("/api/v1/notifications", headers=h).json()
    notes = notes.get("items", notes) if isinstance(notes, dict) else notes
    assert any(n["title"] == "助手：早报" for n in notes)
    again = client.get(f"{API}/routines", headers=h).json()[0]
    assert again["next_run_at"] > utcnow().isoformat()      # 排到下一次，不会原地重跑
    # 同一分钟再跑一次 job，不会再发
    assert client.post(f"{API}/jobs/run-routines", headers=JOB_HEADERS).json()["routines_ok"] == 0


def test_missed_runs_are_caught_up_once_not_replayed(client, requester):
    h = auth(requester)
    # 每天的时间点放在离现在 12 小时处：默认 09:00 时，北京时间 09:00~09:05 跑这条会真的错过 4 次（不是 3 次），测试就变成看钟点
    far = (utcnow() + timedelta(hours=20)).strftime("%H:%M")
    ro = client.post(f"{API}/routines", json={"name": "早报", "kind": "digest", "freq": "daily", "time_of_day": far},
                     headers=h).json()
    with SessionLocal() as db:
        r = db.get(WbRoutine, ro["id"])
        r.next_run_at = utcnow() - timedelta(days=3, minutes=5)    # 停机三天
        db.commit()
    out = client.post(f"{API}/jobs/run-routines", headers=JOB_HEADERS).json()
    assert out["routines_ok"] == 1
    runs = client.get(f"{API}/routines/{ro['id']}/runs", headers=h).json()
    assert len(runs) == 1 and "错过了 3 次" in runs[0]["output"]


def test_three_failures_pause_the_routine_and_tell_the_owner(client, requester, monkeypatch):
    h = auth(requester)
    ro = client.post(f"{API}/routines", json={"name": "周报", "kind": "review", "freq": "daily"}, headers=h).json()

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(svc, "compose", boom)
    for _ in range(3):
        with SessionLocal() as db:
            r = db.get(WbRoutine, ro["id"])
            r.next_run_at = utcnow() - timedelta(minutes=1)
            db.commit()
        client.post(f"{API}/jobs/run-routines", headers=JOB_HEADERS)
    got = client.get(f"{API}/routines", headers=h).json()[0]
    assert got["enabled"] is False and got["failures"] == 3 and got["last_status"] == "failed"
    notes = client.get("/api/v1/notifications", headers=h).json()
    notes = notes.get("items", notes) if isinstance(notes, dict) else notes
    assert any(n["title"] == "例行任务已暂停" for n in notes)
    # 重新开启：失败计数清零
    again = client.patch(f"{API}/routines/{ro['id']}", json={"enabled": True}, headers=h).json()
    assert again["enabled"] and again["failures"] == 0 and again["next_run_at"]


def test_run_now_does_not_move_the_schedule(client, requester):
    h = auth(requester)
    ro = client.post(f"{API}/routines", json={"name": "提醒喝水", "kind": "reminder", "freq": "daily",
                                              "note": "起来走走"}, headers=h).json()
    r = client.post(f"{API}/routines/{ro['id']}/run", headers=h).json()
    assert r["status"] == "ok" and r["output"] == "起来走走" and r["routine"]["next_run_at"] == ro["next_run_at"]


def test_once_routine_in_the_past_is_refused_and_bad_time_is_422(client, requester):
    h = auth(requester)
    r = client.post(f"{API}/routines", json={"name": "x", "kind": "reminder", "freq": "once",
                                             "run_at": (utcnow() - timedelta(hours=1)).isoformat() + "Z"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "routine_time_passed"
    r = client.post(f"{API}/routines", json={"name": "x", "kind": "digest", "freq": "daily",
                                             "time_of_day": "25:00"}, headers=h)
    assert r.status_code == 422


def test_item_reminder_fires_once(client, requester):
    h = auth(requester)
    it = _item(client, requester, title="给房东打电话", remind_at=(utcnow() - timedelta(minutes=1)).isoformat() + "Z")
    assert client.post(f"{API}/jobs/run-routines", headers=JOB_HEADERS).json()["reminders"] == 1
    assert client.post(f"{API}/jobs/run-routines", headers=JOB_HEADERS).json()["reminders"] == 0
    # 改了提醒时间就重新提醒
    client.patch(f"{API}/items/{it['id']}", json={"remind_at": (utcnow() - timedelta(seconds=5)).isoformat() + "Z"},
                 headers=h)
    assert client.post(f"{API}/jobs/run-routines", headers=JOB_HEADERS).json()["reminders"] == 1


# ------------------------------------------------------------------ 项目
def test_project_with_items_can_be_archived_but_not_deleted(client, requester):
    h = auth(requester)
    p = client.post(f"{API}/projects", json={"name": "装修"}, headers=h).json()
    _item(client, requester, project_id=p["id"])
    r = client.delete(f"{API}/projects/{p['id']}", headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "project_not_empty"
    client.patch(f"{API}/projects/{p['id']}", json={"archived": True}, headers=h)
    assert client.get(f"{API}/projects", headers=h).json() == []
    assert len(client.get(f"{API}/projects?include_archived=true", headers=h).json()) == 1


# ------------------------------------------------------------------ PIPL
def test_export_includes_the_workbench_and_erasure_removes_it(client):
    from app.modules.account.deletion import erase_personal_data
    from app.modules.account.models import User

    u = register(client, "13900016001", "工作台")
    h = auth(u)
    it = _item(client, u, title="私事一件")
    client.post(f"{API}/items/{it['id']}/logs", json={"body": "进展"}, headers=h)
    client.post(f"{API}/memories", json={"content": "我不喝咖啡"}, headers=h)
    client.post(f"{API}/routines", json={"name": "早报", "kind": "digest", "freq": "daily"}, headers=h)
    wb = client.get("/api/v1/users/me/export", headers=h).json()["workbench"]
    assert wb["items"][0]["title"] == "私事一件" and wb["memories"][0]["content"] == "我不喝咖啡"
    assert wb["logs"] and wb["routines"]
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, u["id"]))
        db.commit()
        assert db.query(WbItem).filter(WbItem.owner_id == u["id"]).count() == 0
        assert db.query(WbRoutineRun).filter(WbRoutineRun.owner_id == u["id"]).count() == 0


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_every_workbench_response_matches_the_sdk_types(client, requester):
    """真实响应 vs `packages/core` 的类型声明：多一个键客户端看不见，少一个键客户端读到 undefined。"""
    from tests.test_client_shape_alignment import _assert_inline_shape, _assert_shape
    from tests.test_task_flow import CLEAN_TASK

    h = auth(requester)
    t = client.post("/api/v1/tasks", json=CLEAN_TASK, headers=h).json()
    p = client.post(f"{API}/projects", json={"name": "形状"}, headers=h).json()
    _assert_shape(p, "WbProject")
    _assert_shape(client.patch(f"{API}/projects/{p['id']}", json={"sort": 1}, headers=h).json(), "WbProject")
    it = _item(client, requester, project_id=p["id"], linked_task_id=t["id"],
               due_at=(utcnow() - timedelta(hours=1)).isoformat() + "Z")
    _assert_shape(it, "WbItem")
    _assert_shape(it["linked_task"], "WbLinkedTask")
    plain = _item(client, requester, title="没有关联")
    _assert_shape(client.patch(f"{API}/items/{plain['id']}", json={"status": "doing"}, headers=h).json(), "WbItem")
    for row in client.get(f"{API}/items", headers=h).json():
        _assert_shape(row, "WbItem")
    draft = client.post(f"{API}/items/{plain['id']}/breakdown", headers=h).json()
    _assert_shape(draft, "WbBreakdown")
    _assert_shape(draft["steps"][0], "WbStep")
    detail = client.post(f"{API}/items/{plain['id']}/children", json={"steps": draft["steps"][:2]}, headers=h).json()
    _assert_shape(detail, "WbItemDetail")
    _assert_shape(detail["children"][0], "WbItem")
    _assert_shape(client.get(f"{API}/items/{plain['id']}", headers=h).json(), "WbItemDetail")
    _assert_shape(client.post(f"{API}/items/{plain['id']}/logs", json={"body": "x"}, headers=h).json(), "WbLog")
    for row in client.get(f"{API}/items/{plain['id']}/logs", headers=h).json():
        _assert_shape(row, "WbLog")
    ov = client.get(f"{API}/overview", headers=h).json()
    _assert_shape(ov, "WbOverview")
    _assert_shape(ov["overdue"][0], "WbItem")
    _assert_shape(client.post(f"{API}/memories", json={"content": "m"}, headers=h).json(), "WbMemory")
    _assert_inline_shape(client.get(f"{API}/memories", headers=h).json(), "workbenchMemories")
    ro = client.post(f"{API}/routines", json={"name": "r", "kind": "reminder", "freq": "daily"}, headers=h).json()
    _assert_shape(ro, "WbRoutine")
    _assert_shape(client.patch(f"{API}/routines/{ro['id']}", json={"note": "n"}, headers=h).json(), "WbRoutine")
    for row in client.get(f"{API}/routines", headers=h).json():
        _assert_shape(row, "WbRoutine")
    run = client.post(f"{API}/routines/{ro['id']}/run", headers=h).json()
    _assert_inline_shape(run, "runWorkbenchRoutine")
    _assert_shape(run["routine"], "WbRoutine")
    _assert_shape(client.get(f"{API}/routines/{ro['id']}/runs", headers=h).json()[0], "WbRoutineRun")
    for path, method in ((f"/routines/{ro['id']}", "deleteWorkbenchRoutine"), (f"/items/{plain['id']}", "deleteWorkbenchItem")):
        _assert_inline_shape(client.delete(f"{API}{path}", headers=h).json(), method)
    m = client.get(f"{API}/memories", headers=h).json()["items"][0]
    _assert_inline_shape(client.delete(f"{API}/memories/{m['id']}", headers=h).json(), "deleteWorkbenchMemory")
    empty = client.post(f"{API}/projects", json={"name": "空的"}, headers=h).json()
    _assert_inline_shape(client.delete(f"{API}/projects/{empty['id']}", headers=h).json(), "deleteWorkbenchProject")


def test_assistant_notifications_can_be_turned_off(client, requester):
    """助手通知不是必达的：关掉之后例行任务照常运行、记录照常写，只是不再发通知。"""
    h = auth(requester)
    prefs = client.get("/api/v1/notifications/prefs", headers=h).json()["prefs"]
    assert prefs["assistant"] is True
    assert client.put("/api/v1/notifications/prefs?category=assistant&enabled=false", headers=h).status_code == 200
    ro = client.post(f"{API}/routines", json={"name": "提醒", "kind": "reminder", "freq": "daily", "note": "喝水"},
                     headers=h).json()
    assert client.post(f"{API}/routines/{ro['id']}/run", headers=h).json()["status"] == "ok"
    notes = client.get("/api/v1/notifications", headers=h).json()
    notes = notes.get("items", notes) if isinstance(notes, dict) else notes
    assert not any(n["title"] == "助手：提醒" for n in notes)
