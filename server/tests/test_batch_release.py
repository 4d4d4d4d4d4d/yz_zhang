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


# --------------------------------- SC-016 批量放款接入通用幂等键（225 号 spec，V252）
def test_same_key_retry_replays_first_result_and_moves_money_once(client, requester, worker):
    """网络断了用同一个键重试：拿到第一次的结果（已放款），而不是一句「第 1 期不是待验收」。"""
    cid, _ = _three_stage(client, requester, worker)
    _deliver(client, worker, cid, 1, 2)
    h = {**auth(requester), "Idempotency-Key": "rel-1"}
    body = {"idxs": [1, 2], "expected_total_cents": 50000}
    first = client.post(URL.format(cid=cid), json=body, headers=h)
    again = client.post(URL.format(cid=cid), json={"idxs": [2, 1], "expected_total_cents": 50000}, headers=h)
    assert first.status_code == again.status_code == 200, again.text
    assert again.json() == first.json(), "期号顺序不同也是同一次操作"
    with SessionLocal() as db:
        n = db.query(LedgerEntry).filter(LedgerEntry.contract_id == cid, LedgerEntry.kind == "fee").count()
    assert n == 2, "钱只放了一次"
    # 同一个键换了内容：写给开发者的冲突，不会被当成重试静默吞掉
    r = client.post(URL.format(cid=cid), json={"idxs": [1], "expected_total_cents": 20000}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "idempotency_key_conflict"
    r = client.post(URL.format(cid=cid), json={"idxs": [1, 2], "expected_total_cents": 49999}, headers=h)
    assert r.json()["detail"]["code"] == "idempotency_key_conflict", "界面上给人看的合计变了，也是另一次操作"
    # 不带键：照旧（放过的期第二次被拒）
    r = client.post(URL.format(cid=cid), json=body, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "invalid_milestone_state"


def test_failed_attempt_is_not_cached(client, requester, worker):
    """失败不缓存：合计对不上被拒后，同一个键改对了再提交会真的再试一次（104 号的约定）。"""
    cid, _ = _three_stage(client, requester, worker)
    _deliver(client, worker, cid, 1)
    h = {**auth(requester), "Idempotency-Key": "rel-2"}
    r = client.post(URL.format(cid=cid), json={"idxs": [1], "expected_total_cents": 19999}, headers=h)
    assert r.json()["detail"]["code"] == "batch_total_mismatch"
    _deliver(client, worker, cid, 2)
    r = client.post(URL.format(cid=cid), json={"idxs": [1, 2], "expected_total_cents": 50000}, headers=h)
    assert r.status_code == 200 and r.json()["released_cents"] == 50000
