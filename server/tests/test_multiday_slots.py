"""SCN-107 一单多人、多天的临时帮手（167 号 spec，V194）。

小店办活动「要 5 个人干 3 天」：以前一单只能多人、不能多天，只好发三张单——三套说明、三次付款、三张招募互相抢人。
现在一单写「几个人 × 连续几天 × 从哪天开始」，每天每人一个名额，名额写明第几天、哪一天，截止到那天结束。
"""
from datetime import datetime, timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.task.models import Task
from tests.conftest import auth

API = "/api/v1/tasks"


def _today():
    return (utcnow() + timedelta(hours=8)).date()


def _post(client, u, **kw):
    body = {"ip_assignment": "assign", "title": "周末快闪店帮手", "description": "理货、引导、收银协助",
            "category": "跑腿", "budget_cents": 10000, "is_remote": False, "city": "上海", "lat": 31.23, "lng": 121.47,
            "publish_now": True, **kw}
    return client.post(API, json=body, headers=auth(u))


def test_people_times_days_slots_with_dates_deadlines_and_conserved_budget(client, requester):
    start = _today() + timedelta(days=3)
    r = _post(client, requester, people_needed=2, days=3, start_date=start.isoformat())
    assert r.status_code in (200, 201), r.text
    t = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    parent_view = {k: v for k, v in t.items() if k != "slots"}   # SDK 里是 Task & { slots?: Task[] }
    _assert_shape(parent_view, "Task")
    one_slot = t["slots"][0]
    _assert_shape(one_slot, "Task")
    assert t["days"] == 3 and t["work_date"] == start.isoformat()
    slots = t["slots"]
    assert len(slots) == 6, "2 人 × 3 天 = 6 个名额"
    days = [start + timedelta(days=d) for d in range(3)]
    assert [s["work_date"] for s in slots] == [d.isoformat() for d in days for _ in range(2)]
    assert slots[0]["title"] == f"周末快闪店帮手 · 第1天（{days[0].month:02d}-{days[0].day:02d}）· 名额1/2"
    assert slots[5]["title"].endswith(f"第3天（{days[2].month:02d}-{days[2].day:02d}）· 名额2/2")
    budgets = [s["budget_cents"] for s in slots]
    assert sum(budgets) == 10000 and budgets[:5] == [1666] * 5 and budgets[5] == 1670, "余数给最后一个名额，一分不丢"
    with SessionLocal() as db:
        first = db.get(Task, slots[0]["id"])
        end = datetime(days[0].year, days[0].month, days[0].day, 23, 59, 59) - timedelta(hours=8)
        assert first.deadline == end, "名额截止到那天结束（北京时间 23:59:59，库里存 UTC）"
        parent = db.get(Task, t["id"])
        assert parent.deadline == datetime(days[2].year, days[2].month, days[2].day, 23, 59, 59) - timedelta(hours=8)
    assert all(s["status"] == "published" for s in slots)


def test_single_day_multi_person_keeps_the_old_titles_and_no_dates(client, requester):
    r = _post(client, requester, people_needed=3, budget_cents=10000)
    slots = r.json()["slots"]
    assert [s["title"] for s in slots] == [f"周末快闪店帮手 · 名额{i}/3" for i in (1, 2, 3)]
    assert all(s["work_date"] is None for s in slots) and r.json()["days"] == 1


def test_one_person_several_days_also_splits(client, requester):
    start = _today()
    r = _post(client, requester, days=2, start_date=start.isoformat())
    assert len(r.json()["slots"]) == 2 and "第2天" in r.json()["slots"][1]["title"]


def test_rules_start_date_range_cap_and_recurrence(client, requester):
    no_start = _post(client, requester, days=2)
    assert no_start.status_code == 400 and no_start.json()["detail"]["code"] == "start_date_required"
    past = _post(client, requester, days=2, start_date=(_today() - timedelta(days=1)).isoformat())
    assert past.json()["detail"]["code"] == "start_date_in_past"
    far = _post(client, requester, days=2, start_date=(_today() + timedelta(days=61)).isoformat())
    assert far.json()["detail"]["code"] == "start_date_too_far"
    many = _post(client, requester, people_needed=10, days=6, start_date=_today().isoformat(), budget_cents=100000)
    assert many.status_code == 400 and many.json()["detail"]["code"] == "too_many_slots" and "10 × 6" in many.json()["detail"]["message"]
    rec = _post(client, requester, days=2, start_date=_today().isoformat(), recurrence="weekly")
    assert rec.json()["detail"]["code"] == "days_with_recurrence"
    with SessionLocal() as db:
        assert db.query(Task).filter(Task.title.like("周末快闪店帮手%")).count() == 0, "被拒的一张都不留"


def test_machine_api_still_refuses_multi_day():
    from app.modules.openapi import machine
    import inspect

    assert "body.days != 1" in inspect.getsource(machine.publish)


