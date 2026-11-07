"""SCN-116 多天名额按天汇总（174 号 spec，V201）。

「5 个人干 3 天」发出去以后，发单人最先问的是「哪天还缺几个人」。母任务的进度接口按天汇总：
每天几个名额、招到几个、还缺几个、做完几个、取消几个；单天多人与项目拆解没有日期，汇总为空，原样只出一排子任务。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.task.models import Task
from tests.conftest import auth
from tests.test_multiday_slots import _post, _today

API = "/api/v1/tasks"


def _set(slot_id, status, executor_id=None):
    with SessionLocal() as db:
        t = db.get(Task, slot_id)
        t.status, t.executor_id = status, executor_id
        db.commit()


def test_tree_groups_slots_by_day_with_filled_open_done_and_closed(client, requester, worker):
    start = _today() + timedelta(days=2)
    t = _post(client, requester, people_needed=2, days=3, start_date=start.isoformat()).json()
    s = t["slots"]   # 第 1 天 s[0] s[1]，第 2 天 s[2] s[3]，第 3 天 s[4] s[5]
    wid = client.get("/api/v1/users/me", headers=auth(worker)).json()["id"]
    _set(s[0]["id"], "matched", wid)         # 第 1 天招到一个
    _set(s[2]["id"], "completed", wid)       # 第 2 天一个做完了（也算招到）
    _set(s[3]["id"], "cancelled")            # 第 2 天一个取消了：不算缺，也不算招到
    _set(s[4]["id"], "cancelled", wid)       # 接了又取消：不算招到
    tree = client.get(f"{API}/{t['id']}/tree", headers=auth(requester)).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(tree, "TaskTree")
    _assert_shape(tree["children"][0], "TaskTreeChild")
    _assert_shape(tree["by_day"][0], "TaskDaySummary")
    d = [start + timedelta(days=i) for i in range(3)]
    assert tree["by_day"] == [
        {"date": d[0].isoformat(), "slots": 2, "filled": 1, "open": 1, "done": 0, "closed": 0},
        {"date": d[1].isoformat(), "slots": 2, "filled": 1, "open": 0, "done": 1, "closed": 1},
        {"date": d[2].isoformat(), "slots": 2, "filled": 0, "open": 1, "done": 0, "closed": 1},
    ]
    assert [c["work_date"] for c in tree["children"]] == [x.isoformat() for x in d for _ in range(2)]


def test_days_come_out_in_date_order_even_if_slots_were_created_out_of_order(client, requester):
    start = _today() + timedelta(days=5)
    t = _post(client, requester, people_needed=1, days=3, start_date=start.isoformat()).json()
    with SessionLocal() as db:   # 把第 1 个名额挪到最后一天之后：汇总按日期排，不按名额 id
        first = db.get(Task, t["slots"][0]["id"])
        first.work_date = start + timedelta(days=9)
        db.commit()
    dates = [x["date"] for x in client.get(f"{API}/{t['id']}/tree", headers=auth(requester)).json()["by_day"]]
    assert dates == sorted(dates) and len(dates) == 3


def test_single_day_multi_person_has_no_day_summary(client, requester):
    t = _post(client, requester, people_needed=3).json()
    tree = client.get(f"{API}/{t['id']}/tree", headers=auth(requester)).json()
    assert tree["by_day"] == [] and len(tree["children"]) == 3
    # 客户端靠 people_needed 知道这是装名额的母任务，才去拉子任务进度（以前只有项目型才拉，名额看不到）
    assert client.get(f"{API}/{t['id']}", headers=auth(requester)).json()["people_needed"] == 3
    assert all(c["work_date"] is None for c in tree["children"])
