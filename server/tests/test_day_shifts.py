"""SCN-127 多天单每天不同时段（201 号 spec，V225）。

周末快闪店：周六 9:00–18:00、周日 10:00–16:00。以前一单只能写一个统一时段，只能拆成两张单。
现在可以按天给时段（长度等于天数，某天留空就沿用统一时段）；名额带着各自那天的时段、标题照写；
撮合、接单推送按名额自己的时段走（V207 / V220 不用改）。
"""
from datetime import timedelta

from tests.test_multiday_slots import _post, _today


def test_each_day_gets_its_own_shift_and_blank_days_fall_back(client, requester):
    start = _today() + timedelta(days=3)
    r = _post(client, requester, people_needed=1, days=3, start_date=start.isoformat(), shift_start="09:00", shift_end="18:00",
              day_shifts=[None, {"start": " 10:00", "end": "16:00 "}, {"start": "", "end": ""}])
    assert r.status_code == 201, r.text
    slots = r.json()["slots"]
    assert [(s["shift_start"], s["shift_end"]) for s in slots] == [("09:00", "18:00"), ("10:00", "16:00"), ("09:00", "18:00")]
    d2 = start + timedelta(days=1)
    assert slots[1]["title"] == f"周末快闪店帮手 · 第2天（{d2.month:02d}-{d2.day:02d} 10:00–16:00）· 名额1/1"


def test_day_shifts_without_a_default(client, requester):
    start = _today() + timedelta(days=3)
    r = _post(client, requester, people_needed=2, days=2, start_date=start.isoformat(),
              day_shifts=[{"start": "08:00", "end": "12:00"}, None])
    slots = r.json()["slots"]
    assert [(s["shift_start"], s["shift_end"]) for s in slots] == [("08:00", "12:00")] * 2 + [("", "")] * 2, "两个名额同一天同一时段"


def test_rules(client, requester):
    start = (_today() + timedelta(days=3)).isoformat()
    cases = [
        ({"days": 1, "day_shifts": [{"start": "09:00", "end": "18:00"}]}, "day_shifts_without_days"),
        ({"days": 2, "start_date": start, "day_shifts": [None]}, "day_shifts_length"),
        ({"days": 2, "start_date": start, "day_shifts": [{"start": "09:00", "end": ""}, None]}, "shift_incomplete"),
        ({"days": 2, "start_date": start, "day_shifts": [None, {"start": "9:00", "end": "18:00"}]}, "shift_invalid"),
        ({"days": 2, "start_date": start, "day_shifts": [{"start": "18:00", "end": "09:00"}, None]}, "shift_order"),
    ]
    for extra, code in cases:
        r = _post(client, requester, people_needed=1, **extra)
        assert r.status_code == 400 and r.json()["detail"]["code"] == code, (extra, r.text)
    r = _post(client, requester, people_needed=1, days=2, start_date=start, day_shifts=[None, {"start": "09:00", "end": "10:00"}])
    assert r.status_code == 201
    r = _post(client, requester, people_needed=1, days=2, start_date=start, day_shifts=[None, {"start": "09:00", "end": "18:00", "x": 1}])
    assert r.status_code == 422, "多收字段一律不收"


def test_the_error_message_says_which_day(client, requester):
    start = (_today() + timedelta(days=3)).isoformat()
    r = _post(client, requester, people_needed=1, days=3, start_date=start, day_shifts=[None, None, {"start": "18:00", "end": "08:00"}])
    assert "第 3 天" in r.json()["detail"]["message"]
