"""SCN-128 按时段撮合（180 号 spec，V207）。

V205 让名额写明「哪天几点到几点」，推荐却还在按「截止前有没有空」比。现在名额有时段时按那一段比：
本人设的每周时段整段盖住它 → 加分并写进理由；只沾一部分 → 不加不减；一点不沾 → 只降权、不写进理由（不替他公开日程）。
"""
from datetime import date, timedelta

import pytest

from app.modules.matching.service import shift_fit
from tests.conftest import auth
from tests.test_availability import _person
from tests.test_multiday_slots import _post, _today

MON = date(2030, 1, 7)   # 星期一


@pytest.mark.parametrize("slots,expect", [
    ([{"d": 0, "from": "08:00", "to": "19:00"}], "covers"),
    ([{"d": 0, "from": "09:00", "to": "18:30"}], "covers"),           # 刚好盖住
    ([{"d": 0, "from": "00:00", "to": "24:00"}], "covers"),
    ([{"d": 0, "from": "10:00", "to": "12:00"}], "overlap"),
    ([{"d": 0, "from": "18:30", "to": "20:00"}], "none"),             # 首尾相接不算沾
    ([{"d": 1, "from": "00:00", "to": "24:00"}], "none"),             # 别的星期
    ([{"d": 0, "from": "06:00", "to": "08:00"}, {"d": 0, "from": "08:00", "to": "20:00"}], "covers"),
    ([], "none"),
])
def test_shift_fit(slots, expect):
    assert shift_fit(slots, MON, "09:00", "18:30") == expect


def test_recommendations_on_a_slot_use_its_shift(client, requester):
    start = _today() + timedelta(days=3)
    # 多天的单用第一个名额（名额带着日期与时段）
    t = _post(client, requester, people_needed=1, days=2, start_date=start.isoformat(),
              shift_start="09:00", shift_end="18:00").json()
    slot = t["slots"][0]
    wd = start.weekday()
    covers = _person(client, "13900028001", "整天有空")
    partial = _person(client, "13900028002", "上午有空")
    misses = _person(client, "13900028003", "晚上有空")
    nothing = _person(client, "13900028004", "没设时段")
    client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": wd, "from": "08:00", "to": "20:00"}]}, headers=auth(covers))
    client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": wd, "from": "09:00", "to": "12:00"}]}, headers=auth(partial))
    client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": wd, "from": "19:00", "to": "22:00"}]}, headers=auth(misses))
    recs = {r["user_id"]: r for r in client.get(f"/api/v1/tasks/{slot['id']}/recommendations", headers=auth(requester)).json()}
    label = f"{start.month:02d}-{start.day:02d} 09:00–18:00 有空（按本人设的时段）"
    assert label in recs[covers["id"]]["reasons"]
    for u in (partial, misses, nothing):
        assert not any("有空" in x or "时段" in x for x in recs[u["id"]]["reasons"]), "没盖住的不写，更不公开他的日程"
    assert recs[covers["id"]]["score"] > recs[partial["id"]]["score"] == recs[nothing["id"]]["score"] > recs[misses["id"]]["score"]


def test_without_a_shift_the_old_deadline_rule_still_applies(client, requester):
    """没写时段的单照旧按「截止前有没有空」（V143 的规则不变）。"""
    from tests.test_availability import test_free_before_deadline_is_said_but_a_busy_schedule_is_never_shown as old

    old(client, requester)
