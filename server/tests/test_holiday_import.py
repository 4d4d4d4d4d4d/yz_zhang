"""ESCA-072 按国务院放假通知一次导入全年放假与调休（288 号 spec，V315）。

解析在共享 SDK（`parseHolidayNotice`）里出草稿，主管核对后调这个接口一次保存：要么全存、要么一条不存；
已经录过的日子跳过、不覆盖手工录的。
"""
from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from app.modules.support.models import SupportHoliday
from tests.conftest import auth
from tests.test_client_shape_alignment import _assert_shape
from tests.test_support_scopes import API
from tests.test_ticket_assign_reply import _admin

HOL = f"{API}/admin/support/holidays"
BULK = f"{HOL}/bulk"

ITEMS = [
    {"day": "2027-02-06", "kind": "off", "label": "春节", "as_weekday": None},
    {"day": "2027-02-05", "kind": "off", "label": "春节", "as_weekday": None},
    {"day": "2027-02-14", "kind": "workday", "label": "春节调休上班", "as_weekday": 4},
]


def _days():
    with SessionLocal() as db:
        return {(str(h.day), h.kind, h.as_weekday, h.label) for h in db.query(SupportHoliday)}


def test_bulk_saves_the_reviewed_draft_and_skips_days_already_entered(client):
    boss = _admin(client, "13800380001", ["super"])
    hand = client.post(HOL, json={"day": "2027-02-06", "kind": "off", "label": "手工录的"}, headers=auth(boss))
    assert hand.status_code == 200
    r = client.post(BULK, json={"items": ITEMS}, headers=auth(boss))
    assert r.status_code == 200, r.text
    _assert_shape(r.json(), "SupportHolidayBulkResult")
    assert [h["day"] for h in r.json()["created"]] == ["2027-02-05", "2027-02-14"], "按日期排好"
    assert r.json()["skipped"] == ["2027-02-06"]
    assert _days() == {("2027-02-05", "off", None, "春节"), ("2027-02-06", "off", None, "手工录的"),
                       ("2027-02-14", "workday", 4, "春节调休上班")}, "已录的不覆盖"
    with SessionLocal() as db:
        a = db.query(AdminAudit).filter(AdminAudit.action == "support_holiday_bulk_add").one()
        assert "导入 2 天" in a.detail and "跳过已录的 1 天" in a.detail


def test_bulk_is_all_or_nothing_and_only_for_supervisors(client):
    boss = _admin(client, "13800380002", ["super"])
    agent = _admin(client, "13800380003", ["support"])
    assert client.post(BULK, json={"items": ITEMS}, headers=auth(agent)).status_code == 403, "只有主管能导入"
    dup = client.post(BULK, json={"items": ITEMS + [ITEMS[0]]}, headers=auth(boss))
    assert dup.status_code == 400 and dup.json()["detail"]["code"] == "holiday_duplicate_in_batch"
    assert "2027-02-06" in dup.json()["detail"]["message"]
    no_wd = client.post(BULK, json={"items": ITEMS[:2] + [{**ITEMS[2], "as_weekday": None}]}, headers=auth(boss))
    assert no_wd.status_code == 400 and no_wd.json()["detail"]["code"] == "holiday_weekday_required"
    assert "2027-02-14" in no_wd.json()["detail"]["message"]
    assert _days() == set(), "前面的几条也没存"
    assert client.post(BULK, json={"items": []}, headers=auth(boss)).status_code == 422
    off_with_wd = client.post(BULK, json={"items": [{**ITEMS[0], "as_weekday": 2}]}, headers=auth(boss))
    assert off_with_wd.json()["created"][0]["as_weekday"] is None, "放假的那天不带按周几"


# ---------------------------------------------------------------- ESCA-074（293 号 spec，V320）
def test_supervisors_are_reminded_in_nov_to_jan_when_next_year_is_empty(client):
    from datetime import date, datetime, timedelta

    from app.modules.notification.models import Notification
    from app.modules.support.escalation import remind_holiday_import
    from tests.conftest import JOB_HEADERS
    from tests.test_support_schedule import SCHED

    boss = _admin(client, "13800380011", ["super"])
    agent = _admin(client, "13800380012", ["support"])
    nov = datetime(2026, 10, 31, 17, 0)                          # UTC 还是 10 月，北京时间已是 11-01 01:00

    def run(now):
        with SessionLocal() as db:
            r = remind_holiday_import(db, now)
            db.commit()
            return r

    assert run(nov)["reason"] == "没有客服设排班，节假日不影响派单"
    client.put(SCHED, json={"windows": [{"weekday": 0, "start": "09:00", "end": "18:00"}]}, headers=auth(agent))
    assert run(datetime(2026, 10, 31, 15, 0))["reason"] == "不在提醒的月份", "UTC 10-31 15:00 是北京时间 10-31 23:00，还没到 11 月"
    assert run(datetime(2026, 2, 3, 2, 0))["reason"] == "不在提醒的月份"
    r = run(nov)
    assert r == {"reminded": 1, "year": 2027}
    with SessionLocal() as db:
        n = db.query(Notification).filter(Notification.title == "该导入 2027 年的放假安排了").one()
        assert n.user_id == boss["id"] and "按国务院放假通知导入" in n.body, "只提醒主管（客服不收）"
        n.created_at = nov                                           # 让站内信的时间与这里的「现在」对齐
        db.commit()
    assert run(nov + timedelta(days=3))["reason"] == "这周已经提醒过"
    assert run(datetime(2027, 1, 10, 2, 0))["year"] == 2027, "1 月提醒的是当年"
    with SessionLocal() as db:
        db.add(SupportHoliday(day=date(2027, 1, 1), kind="off", label="元旦", created_by=boss["id"]))
        db.commit()
    assert run(datetime(2027, 1, 20, 2, 0))["reason"] == "2027 年已经录过"
    assert client.post(f"{API}/admin/jobs/remind-holiday-import").status_code == 403, "没有 job 密钥被拒"
    assert client.post(f"{API}/admin/jobs/remind-holiday-import", headers=JOB_HEADERS).status_code == 200
