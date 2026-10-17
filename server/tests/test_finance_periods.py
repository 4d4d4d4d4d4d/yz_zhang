"""FIN-061 按期间的平台财务（144 号 spec）；TZ-069 合约导出与证据包写明时区。

此前平台财务只有累计数：「本月佣金多少、本季结算了多少」要靠导出流水自己算——
而按 UTC 切月会把每月 1 日北京时间 0~8 点的单算进上个月。
"""
from datetime import datetime

import pytest

from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.admin.models import AdminAudit
from app.modules.wallet import service as wallet
from app.modules.wallet.models import LedgerEntry
from tests.conftest import auth, make_admin, register, topup
from tests.test_task_flow import match_and_fund, publish_task

API = "/api/v1"


def test_period_bounds_are_beijing_calendar():
    b = wallet.period_bounds("month", "2026-08", "2026-09")
    assert [x[0] for x in b] == ["2026-08", "2026-09"]
    assert b[1][1] == datetime(2026, 8, 31, 16, 0) and b[1][2] == datetime(2026, 9, 30, 16, 0), "北京时间 9 月 1 日零点 = UTC 8 月 31 日 16 点"
    q = wallet.period_bounds("quarter", "2026-05", "2026-11")
    assert [x[0] for x in q] == ["2026-Q2", "2026-Q3", "2026-Q4"]
    assert wallet.period_bounds("month", "2025-12", "2026-01")[1][0] == "2026-01", "跨年"


def test_period_range_limits(client):
    fin = make_admin(client, "13800240001", "财务")
    url = f"{API}/admin/platform-finance/periods"
    r = client.get(url, params={"start": "2020-01", "end": "2026-01"}, headers=auth(fin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "period_range_too_long"
    r = client.get(url, params={"start": "2026-05", "end": "2026-03"}, headers=auth(fin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "period_range_invalid"
    assert client.get(url, params={"start": "2026-13"}, headers=auth(fin)).status_code == 422


def _seed():
    rows = [
        ("fee", 1000, datetime(2026, 8, 15, 3, 0)),
        ("fee", 500, datetime(2026, 8, 31, 16, 30)),       # 北京时间 9 月 1 日 00:30 → 算 9 月
        ("platform_settle", -800, datetime(2026, 9, 10, 2, 0)),
        ("subsidy_out", -200, datetime(2026, 9, 12, 2, 0)),
        ("adjust_in", 50, datetime(2026, 9, 20, 2, 0)),
    ]
    with SessionLocal() as db:
        db.add_all([LedgerEntry(user_id=wallet.PLATFORM_USER_ID, kind=k, amount_cents=a, memo="t", created_at=t)
                    for k, a, t in rows])
        db.add(LedgerEntry(user_id=123, kind="fee", amount_cents=99999, memo="别人的账户不算", created_at=datetime(2026, 9, 5)))
        db.add(LedgerEntry(user_id=123, kind="topup", amount_cents=77777, memo="期初也只算平台账户", created_at=datetime(2026, 7, 5)))
        db.commit()


def test_periods_split_by_beijing_month_with_opening_closing(client):
    _seed()
    fin = make_admin(client, "13800240002", "财务")
    r = client.get(f"{API}/admin/platform-finance/periods", params={"start": "2026-08", "end": "2026-09"}, headers=auth(fin)).json()
    aug, sep = r["periods"]
    assert (aug["fee_cents"], aug["fee_count"], aug["opening_cents"], aug["closing_cents"]) == (1000, 1, 0, 1000)
    assert (sep["fee_cents"], sep["fee_count"], sep["settled_cents"], sep["subsidy_cents"], sep["other_cents"]) == (500, 1, 800, 200, 50)
    assert sep["net_cents"] == -450 and sep["opening_cents"] == 1000 and sep["closing_cents"] == 550
    assert aug["balanced"] and sep["balanced"]
    assert sep["start"] == "2026-08-31T16:00:00Z"
    q = client.get(f"{API}/admin/platform-finance/periods", params={"granularity": "quarter", "start": "2026-07", "end": "2026-07"},
                   headers=auth(fin)).json()
    assert q["periods"][0]["period"] == "2026-Q3" and q["periods"][0]["fee_cents"] == 1500


def test_default_range_is_last_12_months(client):
    fin = make_admin(client, "13800240003", "财务")
    r = client.get(f"{API}/admin/platform-finance/periods", headers=auth(fin)).json()
    assert len(r["periods"]) == 12 and r["granularity"] == "month"
    assert len(client.get(f"{API}/admin/platform-finance/periods", params={"granularity": "quarter"}, headers=auth(fin)).json()["periods"]) == 4


def test_export_labels_timezone_audits_and_needs_finance(client):
    _seed()
    fin = make_admin(client, "13800240004", "财务")
    with SessionLocal() as db:
        db.get(User, fin["id"]).admin_roles = ["finance"]
        db.commit()
    r = client.get(f"{API}/admin/platform-finance/periods/export", params={"start": "2026-09", "end": "2026-09"}, headers=auth(fin)).json()
    head, row = r["csv"].strip().splitlines()
    assert "起（北京时间 UTC+8）" in head and row.startswith("2026-09,2026-09-01 00:00:00,2026-10-01 00:00:00,5.00,1,8.00,2.00,0.50,")
    assert row.endswith(",平") and r["filename"] == "platform-finance-2026-09-2026-09.csv"
    with SessionLocal() as db:
        assert db.query(AdminAudit).filter(AdminAudit.action == "export_platform_finance").one().detail == "month 2026-09~2026-09"
    ops = make_admin(client, "13800240005", "运营")
    with SessionLocal() as db:
        db.get(User, ops["id"]).admin_roles = ["ops"]
        db.commit()
    for path in ("/admin/platform-finance/periods", "/admin/platform-finance/periods/export"):
        assert client.get(f"{API}{path}", headers=auth(ops)).json()["detail"]["code"] == "admin_role_required"


def test_shape(client):
    from tests.test_client_shape_alignment import _assert_shape

    fin = make_admin(client, "13800240006", "财务")
    r = client.get(f"{API}/admin/platform-finance/periods", headers=auth(fin)).json()
    _assert_shape(r, "PlatformFinancePeriods")
    first = r["periods"][0]
    _assert_shape(first, "PlatformFinancePeriod")
    ex = client.get(f"{API}/admin/platform-finance/periods/export", headers=auth(fin)).json()
    _assert_shape(ex, "PlatformFinanceExport")


# ------------------------------------------------------------------ TZ-069
def test_contract_export_times_are_labelled_beijing(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    cid = match_and_fund(client, requester, worker, task)
    text = client.get(f"{API}/contracts/{cid}/export", headers=auth(worker)).json()["text"]
    assert "── 结算凭证（资金流水；时间为北京时间 UTC+8） ──" in text
    ledger_lines = text.split("结算凭证")[1].splitlines()[1:3]
    assert ledger_lines and all("Z " not in ln and ln[:4].isdigit() and ln[10] == " " for ln in ledger_lines if ln.strip())


def test_evidence_package_states_its_time_zone(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    d = client.post(f"{API}/tasks/{task['id']}/disputes", json={"reason": "质量不合格"}, headers=auth(requester)).json()
    pkg = client.get(f"{API}/legal/disputes/{d['id']}/evidence-export", headers=auth(worker)).json()["package"]
    assert pkg["time_zone"].startswith("本文件中的时间均为 UTC")
