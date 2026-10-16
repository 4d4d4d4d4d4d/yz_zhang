"""SCN-117 多天名额的每天时段（178 号 spec，V205）。

「5 个人干 3 天」只写了哪几天，没写几点到几点：时段只能写在说明里，名额标题上看不到。
现在发单时写每天几点到几点（北京时间），名额带着、标题写明；格式、先后、成对都校验。
"""
from datetime import timedelta

from tests.conftest import auth
from tests.test_multiday_slots import _post, _today


def test_slots_carry_the_shift_and_say_it_in_the_title(client, requester):
    start = _today() + timedelta(days=3)
    r = _post(client, requester, people_needed=1, days=2, start_date=start.isoformat(), shift_start="09:00", shift_end="18:30")
    assert r.status_code == 201, r.text
    t = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(t["slots"][0], "Task")
    assert t["shift_start"] == "09:00" and t["shift_end"] == "18:30"
    assert all(s["shift_start"] == "09:00" and s["shift_end"] == "18:30" for s in t["slots"])
    assert t["slots"][0]["title"] == f"周末快闪店帮手 · 第1天（{start.month:02d}-{start.day:02d} 09:00–18:30）· 名额1/1"


def test_without_a_shift_titles_and_fields_stay_as_before(client, requester):
    start = _today() + timedelta(days=3)
    t = _post(client, requester, people_needed=1, days=2, start_date=start.isoformat(), shift_start=" ", shift_end="").json()
    assert t["shift_start"] == "" and t["shift_end"] == ""
    assert t["slots"][0]["title"] == f"周末快闪店帮手 · 第1天（{start.month:02d}-{start.day:02d}）· 名额1/1"


def test_shift_rules(client, requester):
    start = (_today() + timedelta(days=3)).isoformat()
    cases = [
        ({"shift_start": "09:00"}, "shift_incomplete"),
        ({"shift_end": "18:00"}, "shift_incomplete"),
        ({"shift_start": "9:00", "shift_end": "18:00"}, "shift_invalid"),
        ({"shift_start": "09:00", "shift_end": "24:00"}, "shift_invalid"),
        ({"shift_start": "18:00", "shift_end": "09:00"}, "shift_order"),
        ({"shift_start": "09:00", "shift_end": "09:00"}, "shift_order"),
    ]
    for extra, code in cases:
        r = _post(client, requester, people_needed=1, days=2, start_date=start, **extra)
        assert r.status_code == 400 and r.json()["detail"]["code"] == code, (extra, r.text)


def test_a_single_task_can_say_its_hours_too(client, requester):
    r = _post(client, requester, shift_start="14:00", shift_end="16:00")
    assert r.status_code == 201 and r.json()["shift_start"] == "14:00"
    got = client.get(f"/api/v1/tasks/{r.json()['id']}", headers=auth(requester)).json()
    assert (got["shift_start"], got["shift_end"]) == ("14:00", "16:00")


def test_surrounding_spaces_are_trimmed_before_storing(client, requester):
    r = _post(client, requester, shift_start=" 08:30", shift_end="12:00 ")
    assert r.status_code == 201 and (r.json()["shift_start"], r.json()["shift_end"]) == ("08:30", "12:00")
