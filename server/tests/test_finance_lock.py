"""FIN-063 已出期间的报表锁账（223 号 spec，V250）。

以前按期间的报表每次打开都现算：报给记账代理、交过税的那个月，之后只要再有一笔流水落进那个月，
数就变了，谁也不知道。现在可以「锁到某月」：锁过的月份只读快照，之后才记进去的（补记）
记到第一个未锁的月份并写明，已出的数一分不变。
"""
from datetime import datetime

from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from app.modules.wallet import service as wallet
from app.modules.wallet.models import LedgerEntry
from tests.conftest import auth, make_admin
from tests.test_ticket_assign_reply import _admin

API = "/api/v1"
URL = f"{API}/admin/platform-finance/periods"


def _add(*rows):
    with SessionLocal() as db:
        db.add_all([LedgerEntry(user_id=wallet.PLATFORM_USER_ID, kind=k, amount_cents=a, memo="t", created_at=t)
                    for k, a, t in rows])
        db.commit()


def _seed():
    _add(("fee", 1000, datetime(2025, 1, 10, 3)), ("fee", 400, datetime(2025, 2, 10, 3)),
         ("platform_settle", -300, datetime(2025, 2, 20, 3)), ("fee", 700, datetime(2025, 3, 5, 3)))


def _months(client, h, start="2025-01", end="2025-04"):
    r = client.get(URL, params={"start": start, "end": end}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_lock_rules_and_audit(client):
    fin = make_admin(client, "13800322001", "财务")
    h = auth(fin)
    lock = f"{API}/admin/platform-finance/lock"
    r = client.post(lock, json={"through": "2099-01"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "period_not_ended"
    assert "还没过完" in r.json()["detail"]["message"]
    support = _admin(client, "13800322002", ["support"])
    assert client.post(lock, json={"through": "2025-02"}, headers=auth(support)).status_code == 403
    assert client.post(lock, json={"through": "2025-2"}, headers=h).status_code == 422
    _seed()
    r = client.post(lock, json={"through": "2025-02"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["months"] == ["2025-01", "2025-02"], "第一次锁从有流水的第一个月起逐月锁"
    r = client.post(lock, json={"through": "2025-01"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "period_already_closed"
    assert client.post(lock, json={"through": "2025-02"}, headers=h).json()["detail"]["code"] == "period_already_closed"
    r = client.post(lock, json={"through": "2025-03"}, headers=h)
    assert r.json()["months"] == ["2025-03"], "之后从上次锁到的下一个月起"
    with SessionLocal() as db:
        notes = [a.detail for a in db.query(AdminAudit).filter(AdminAudit.action == "lock_platform_finance")]
    assert notes == ["锁到 2025-02（2025-01~2025-02，2 个月）", "锁到 2025-03（2025-03~2025-03，1 个月）"]


def test_no_lock_is_unchanged_plus_default_fields(client):
    _seed()
    fin = make_admin(client, "13800322003", "财务")
    d = _months(client, auth(fin))
    assert d["locked_through"] is None and d["locked_at"] is None
    feb = d["periods"][1]
    assert (feb["fee_cents"], feb["settled_cents"], feb["opening_cents"], feb["closing_cents"]) == (400, 300, 1000, 1100)
    assert all(not r["closed"] and r["late_cents"] == 0 and r["carried_in_cents"] == 0 for r in d["periods"])
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(d, "PlatformFinancePeriods")
    _assert_shape(feb, "PlatformFinancePeriod")


def test_locked_month_is_frozen_and_late_entries_post_to_first_open_month(client):
    _seed()
    fin = make_admin(client, "13800322004", "财务")
    h = auth(fin)
    before = _months(client, h)
    client.post(f"{API}/admin/platform-finance/lock", json={"through": "2025-02"}, headers=h)
    locked = _months(client, h)
    assert locked["locked_through"] == "2025-02" and locked["locked_at"]
    keys = ("fee_cents", "fee_count", "settled_cents", "net_cents", "opening_cents", "closing_cents")
    for b, a in zip(before["periods"], locked["periods"]):
        assert {k: b[k] for k in keys} == {k: a[k] for k in keys}, "刚锁的时候数和锁之前一样"
    assert [r["closed"] for r in locked["periods"]] == [True, True, False, False]

    # 锁账之后又有一笔记进 2 月（补记）：2 月的数不变，写明多了什么；这笔记到 3 月
    _add(("fee", 250, datetime(2025, 2, 25, 3)), ("adjust_out", -50, datetime(2025, 1, 31, 3)))
    after = _months(client, h)
    jan, feb, mar, apr = after["periods"]
    assert {k: feb[k] for k in keys} == {k: locked["periods"][1][k] for k in keys}, "已锁的月份一分不变"
    assert (feb["late_cents"], feb["late_count"]) == (250, 1)
    assert (jan["late_cents"], jan["late_count"]) == (-50, 1)
    assert (mar["carried_in_cents"], mar["carried_in_count"]) == (200, 2)
    assert mar["fee_cents"] == 700 + 250 and mar["fee_count"] == 2 and mar["other_cents"] == -50
    assert mar["opening_cents"] == feb["closing_cents"], "第一个未锁月份的期初接得上已锁的期末"
    assert mar["balanced"] and mar["closing_cents"] == 1000 + 400 - 300 + 700 + 250 - 50
    assert apr["carried_in_cents"] == 0 and apr["opening_cents"] == mar["closing_cents"]

    # 再锁 3 月：3 月的快照带着补记；之后 4 月不再重复记它们
    client.post(f"{API}/admin/platform-finance/lock", json={"through": "2025-03"}, headers=h)
    again = _months(client, h)
    assert again["periods"][2]["fee_cents"] == 950 and again["periods"][2]["closed"]
    assert again["periods"][3]["carried_in_cents"] == 0 and again["periods"][3]["opening_cents"] == mar["closing_cents"]


def test_quarter_rolls_up_months_and_export_says_locked(client):
    _seed()
    fin = make_admin(client, "13800322005", "财务")
    h = auth(fin)
    client.post(f"{API}/admin/platform-finance/lock", json={"through": "2025-03"}, headers=h)
    _add(("fee", 90, datetime(2025, 3, 30, 3)))
    q = client.get(URL, params={"granularity": "quarter", "start": "2025-01", "end": "2025-06"}, headers=h).json()
    q1, q2 = q["periods"]
    assert q1["period"] == "2025-Q1" and q1["closed"] and not q2["closed"]
    assert (q1["fee_cents"], q1["fee_count"], q1["opening_cents"], q1["closing_cents"]) == (2100, 3, 0, 1800)
    assert q1["late_cents"] == 90 and q2["carried_in_cents"] == 90 and q2["fee_cents"] == 90
    assert q2["opening_cents"] == q1["closing_cents"] and q2["balanced"]
    r = client.get(f"{URL}/export", params={"start": "2025-02", "end": "2025-04"}, headers=h).json()
    lines = r["csv"].strip().splitlines()
    assert lines[0].endswith("锁账,锁账后又记进本期（元，已记到下一个未锁月份）,本期含补记以前期间（元）,自检")
    assert lines[2].split(",")[-4:] == ["已锁", "0.90", "0.00", "平"]
    assert lines[3].split(",")[-4:] == ["未锁", "0.00", "0.90", "平"]


def test_partly_locked_quarter_and_backdated_entry_before_first_month(client):
    _seed()
    fin = make_admin(client, "13800322006", "财务")
    h = auth(fin)
    client.post(f"{API}/admin/platform-finance/lock", json={"through": "2025-02"}, headers=h)
    q1 = client.get(URL, params={"granularity": "quarter", "start": "2025-01", "end": "2025-03"}, headers=h).json()["periods"][0]
    assert not q1["closed"], "季度要三个月都锁了才算已锁"
    # 锁账之后补记一笔到比最早流水还早的月份：那个月也算已锁（锁到 2 月 = 2 月以前全锁），补记记到 3 月
    _add(("adjust_in", 30, datetime(2024, 12, 15, 3)))
    dec, jan, feb, mar = _months(client, h, "2024-12", "2025-03")["periods"]
    assert dec["closed"] and dec["fee_cents"] == 0 and dec["closing_cents"] == 0 and (dec["late_cents"], dec["late_count"]) == (30, 1)
    assert jan["opening_cents"] == 0, "已锁的数不因补记改变"
    assert mar["carried_in_cents"] == 30 and mar["opening_cents"] == feb["closing_cents"] and mar["balanced"]
