"""SC-017 每一期挂各自的交付附件（304 号 spec，V331）。

V323 一次交付多期只能共用一份交付说明，V324 的交付文件挂在整份合约上、放款完毕才解锁原图：验收时分不清哪份文件对
哪一期，分期付款的人付了第一期也拿不到第一期的原图。现在交付文件可以挂到某一期上，那一期放款后原图就解锁；
不写期数的照旧挂整份合约（V324 的行为不变）。
"""
from tests.conftest import auth
from tests.test_batch_release import _deliver, _three_stage
from tests.test_contract_deliverables import _upload

API = "/api/v1"


def test_an_original_tied_to_a_stage_unlocks_when_that_stage_is_paid(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    D = f"{API}/contracts/{cid}/deliverables"
    one = client.post(D, json={"ref": _upload(client, worker, b"\x41"), "kind": "original", "milestone_idx": 1},
                      headers=auth(worker))
    two = client.post(D, json={"ref": _upload(client, worker, b"\x42"), "kind": "original", "milestone_idx": 2},
                      headers=auth(worker))
    whole = client.post(D, json={"ref": _upload(client, worker, b"\x43"), "kind": "original"}, headers=auth(worker))
    assert one.status_code == 201 and two.status_code == 201 and whole.status_code == 201, (one.text, two.text)
    assert one.json()["milestone_idx"] == 1 and "milestone_idx" not in whole.json(), "不写期数时不出这个字段"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(one.json(), "ContractDeliverable")

    _deliver(client, worker, cid, 1)
    acc = client.post(f"{API}/contracts/{cid}/milestones/1/accept", headers=auth(requester))
    assert acc.status_code == 200, acc.text
    _deliver(client, worker, cid, 2)        # 第 2 期交付了、还没放款：原图照旧锁着
    rows = {r["id"]: r for r in client.get(D, headers=auth(requester)).json()}
    assert rows[one.json()["id"]]["locked"] is False and rows[one.json()["id"]]["url"], "第 1 期放款了，第 1 期的原图解锁"
    assert rows[two.json()["id"]]["locked"] is True and rows[two.json()["id"]]["url"] is None, "第 2 期还没放款"
    assert rows[whole.json()["id"]]["locked"] is True, "挂整份合约的照旧等全部放完"
    assert client.get(f"{D}/{one.json()['id']}/file", headers=auth(requester)).status_code == 200
    r = client.get(f"{D}/{two.json()['id']}/file", headers=auth(requester))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "deliverable_locked"
    assert client.get(f"{D}/{whole.json()['id']}/file", headers=auth(requester)).status_code == 403


def test_the_stage_must_exist_and_not_be_paid_yet(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    D = f"{API}/contracts/{cid}/deliverables"
    r = client.post(D, json={"ref": _upload(client, worker, b"\x51"), "kind": "preview", "milestone_idx": 4},
                    headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "milestone_not_found" and "第 4 期" in r.json()["detail"]["message"]
    _deliver(client, worker, cid, 1)
    assert client.post(f"{API}/contracts/{cid}/milestones/1/accept", headers=auth(requester)).status_code == 200
    r = client.post(D, json={"ref": _upload(client, worker, b"\x52"), "kind": "original", "milestone_idx": 1},
                    headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "invalid_milestone_state" and "已经放款" in r.json()["detail"]["message"]
    delivered_not_paid = client.post(D, json={"ref": _upload(client, worker, b"\x53"), "kind": "preview", "milestone_idx": 2},
                                     headers=auth(worker))
    assert delivered_not_paid.status_code == 201, "还没放款的期（不论交没交付）都能补挂"
    assert client.post(D, json={"ref": _upload(client, worker, b"\x54"), "kind": "preview", "milestone_idx": 0},
                       headers=auth(worker)).status_code == 422
