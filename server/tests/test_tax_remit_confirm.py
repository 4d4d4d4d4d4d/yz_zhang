"""PAY-042d 税款缴库前的人工确认（287 号 spec，V314）。

缴库原来是每天的 job、直接把专户余额划出，没有人看过。现在待缴达到
`PLATFORM_TAX_REMIT_CONFIRM_CENTS` 时 job 只生成草稿、通知财务；财务与申报数核对后确认才划出，
划的是草稿上那个数。线下照旧一步完成（`test_tax_withholding.py::test_tax045_*` 不变）。
"""
import pytest

from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from app.modules.notification.models import Notification
from app.modules.tax import service as tax
from tests.conftest import JOB_HEADERS, auth
from tests.test_client_shape_alignment import _assert_shape
from tests.test_tax_withholding import run_loop
from tests.test_ticket_assign_reply import _admin

API = "/api/v1"
JOB = f"{API}/finance/jobs/remit-tax"
R = f"{API}/finance/tax-remits"


@pytest.fixture()
def low_line(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "TAX_REMIT_CONFIRM_CENTS", 1)


def _balance():
    with SessionLocal() as db:
        return tax.account_balance(db)


def test_large_remit_waits_for_finance_and_moves_exactly_the_draft(client, requester, worker, withholding, low_line):
    fin = _admin(client, "13800370001", ["finance"])
    ops = _admin(client, "13800370002", ["ops"])
    run_loop(client, requester, worker)
    before = _balance()
    assert before > 0
    first = client.post(JOB, headers=JOB_HEADERS).json()
    assert first["remitted_cents"] == 0 and first["pending_cents"] == before, "达到线不动钱"
    assert _balance() == before
    again = client.post(JOB, headers=JOB_HEADERS).json()
    assert again["pending_request_id"] == first["pending_request_id"], "已有草稿时不再生成第二份"
    with SessionLocal() as db:
        got = {n.user_id for n in db.query(Notification).filter(Notification.title == "有一笔代扣税款等你确认缴库")}
    assert got == {fin["id"]}, "只通知财务、只通知一次"

    rows = client.get(R, headers=auth(fin)).json()
    assert [r["id"] for r in rows] == [first["pending_request_id"]]
    _assert_shape(rows[0], "TaxRemitRequestRow")
    assert client.get(R, headers=auth(ops)).status_code == 403, "只有财务能看能批"

    # 草稿之后又代扣了一笔：确认只划草稿上的数，新的留到下一次
    run_loop(client, requester, worker)
    more = _balance() - before
    assert more > 0
    ok = client.post(f"{R}/{first['pending_request_id']}/confirm", headers=auth(fin))
    assert ok.status_code == 200, ok.text
    _assert_shape(ok.json(), "TaxRemitConfirmed")
    assert ok.json()["status"] == "remitted" and ok.json()["balance_cents"] == more == _balance()
    twice = client.post(f"{R}/{first['pending_request_id']}/confirm", headers=auth(fin))
    assert twice.status_code == 409 and twice.json()["detail"]["code"] == "tax_remit_already_decided"

    from app.modules.risk import service as risk

    with SessionLocal() as db:
        assert tax.expected_balance(db) == more
        assert risk.reconcile(db)["mismatches"] == [], "缴库草稿不破坏全局守恒"
        assert db.query(AdminAudit).filter(AdminAudit.action == "tax_remit_confirm").count() == 1


def test_reject_needs_a_reason_keeps_the_money_and_the_next_run_drafts_again(client, requester, worker, withholding, low_line):
    fin = _admin(client, "13800370003", ["finance"])
    run_loop(client, requester, worker)
    before = _balance()
    rid = client.post(JOB, headers=JOB_HEADERS).json()["pending_request_id"]
    bare = client.post(f"{R}/{rid}/reject", json={"reason": " "}, headers=auth(fin))
    assert bare.status_code == 400 and bare.json()["detail"]["code"] == "reason_required"
    r = client.post(f"{R}/{rid}/reject", json={"reason": "与本月申报表差 12 元"}, headers=auth(fin))
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["decision_reason"] == "与本月申报表差 12 元"
    assert _balance() == before, "驳回不动钱"
    assert client.get(R, headers=auth(fin)).json() == []
    assert [x["id"] for x in client.get(f"{R}?status=rejected", headers=auth(fin)).json()] == [rid]
    nxt = client.post(JOB, headers=JOB_HEADERS).json()
    assert nxt["pending_request_id"] != rid and nxt["pending_cents"] == before


def test_confirm_refuses_when_the_account_holds_less_than_the_draft(client, requester, worker, withholding, low_line):
    fin = _admin(client, "13800370004", ["finance"])
    run_loop(client, requester, worker)
    rid = client.post(JOB, headers=JOB_HEADERS).json()["pending_request_id"]
    from app.modules.tax.models import TaxRemitRequest

    with SessionLocal() as db:
        db.get(TaxRemitRequest, rid).amount_cents += 1
        db.commit()
    before = _balance()
    r = client.post(f"{R}/{rid}/confirm", headers=auth(fin))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "tax_remit_insufficient"
    assert "对账" in r.json()["detail"]["message"] and _balance() == before


def test_below_the_line_the_job_still_remits_in_one_step(client, requester, worker, withholding):
    run_loop(client, requester, worker)
    before = _balance()
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert r["remitted_cents"] == before and "pending_request_id" not in r, "线下响应与以前一样"
