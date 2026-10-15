"""SC-014 只放已交付的那几期（146 号 spec）。

分期合约三期都交付了，此前发布方只能点三次「验收本期」，或者点「整单验收」——而后者会放掉**剩余全部**期，
包括还没交付的。这里给出第三种：一次放掉点名的、已交付的期，不动没交付的。
"""
from app.core.db import SessionLocal
from app.modules.wallet.models import LedgerEntry
from tests.conftest import auth
from tests.test_contract_v1 import _matched_contract, _sign_and_fund

URL = "/api/v1/contracts/{cid}/milestones/release-delivered"


def _three_stage(client, requester, worker):
    cid, task = _matched_contract(client, requester, worker, budget=90000)
    client.post(f"/api/v1/contracts/{cid}/milestones", headers=auth(requester), json={"items": [
        {"title": "设计", "amount_cents": 20000}, {"title": "施工", "amount_cents": 30000}, {"title": "收尾", "amount_cents": 40000}]})
    _sign_and_fund(client, requester, worker, cid)
    return cid, task


def _deliver(client, worker, cid, *idxs):
    for i in idxs:
        assert client.post(f"/api/v1/contracts/{cid}/milestones/{i}/deliver", headers=auth(worker)).status_code == 200


def test_releases_only_the_named_delivered_stages(client, requester, worker):
    cid, task = _three_stage(client, requester, worker)
    _deliver(client, worker, cid, 1, 2)
    r = client.post(URL.format(cid=cid), json={"idxs": [2, 1], "expected_total_cents": 50000}, headers=auth(requester))
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["released_cents"] == 50000 and c["status"] == "funded", "第 3 期没交付，不动"
    assert [m["status"] for m in c["milestones"]] == ["released", "released", "pending"]
    with SessionLocal() as db:
        fees = [e.amount_cents for e in db.query(LedgerEntry).filter(LedgerEntry.contract_id == cid, LedgerEntry.kind == "fee")
                .order_by(LedgerEntry.id)]
    assert fees == [20000 * 800 // 10000, 30000 * 800 // 10000], "按期号顺序逐期放，佣金与单期验收一样"
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()["status"] != "completed"


def test_last_stages_close_the_task(client, requester, worker):
    cid, task = _three_stage(client, requester, worker)
    _deliver(client, worker, cid, 1, 2, 3)
    r = client.post(URL.format(cid=cid), json={"idxs": [1, 2, 3], "expected_total_cents": 90000}, headers=auth(requester)).json()
    assert r["status"] == "released"
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()["status"] == "completed"


def test_refuses_undelivered_stale_total_and_bad_input_all_or_nothing(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    _deliver(client, worker, cid, 1)
    url, h = URL.format(cid=cid), auth(requester)
    r = client.post(url, json={"idxs": [1, 2], "expected_total_cents": 50000}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "invalid_milestone_state" and "第 2 期" in r.json()["detail"]["message"]
    r = client.post(url, json={"idxs": [1], "expected_total_cents": 19999}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "batch_total_mismatch"
    assert client.post(url, json={"idxs": [1, 1], "expected_total_cents": 40000}, headers=h).json()["detail"]["code"] == "batch_duplicate"
    assert client.post(url, json={"idxs": [9], "expected_total_cents": 1}, headers=h).json()["detail"]["code"] == "milestone_not_found"
    c = client.get(f"/api/v1/contracts/{cid}", headers=h).json()
    assert c["released_cents"] == 0, "被拒的批次一分钱没动"
    # 只有发布方能放
    r = client.post(url, json={"idxs": [1], "expected_total_cents": 20000}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_party"


def test_frozen_contract_releases_nothing(client, requester, worker):
    cid, task = _three_stage(client, requester, worker)
    _deliver(client, worker, cid, 1, 2)
    client.post(f"/api/v1/tasks/{task['id']}/disputes", json={"reason": "质量有争议"}, headers=auth(requester))
    r = client.post(URL.format(cid=cid), json={"idxs": [1, 2], "expected_total_cents": 50000}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "contract_frozen"
    assert client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()["released_cents"] == 0
