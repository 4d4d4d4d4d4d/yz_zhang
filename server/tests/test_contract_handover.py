"""SCN-205 建站交付的账号交接清单（330 号 spec，V357）：域名、小程序、服务器、支付商户号逐项登记，
发单人逐项确认「已在我名下」。账号卡在开发方手里是建站最常见的纠纷，口头说「都给你了」对不上。
"""
from app.core.db import SessionLocal
from app.modules.contract.models import Contract
from app.modules.notification.models import Notification
from tests.conftest import auth, register
from tests.test_batch_release import _three_stage

API = "/api/v1"


def test_executor_lists_accounts_and_the_requester_confirms_them(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_shape

    cid, _ = _three_stage(client, requester, worker)
    H = f"{API}/contracts/{cid}/handover"
    r = client.post(H, json={"kind": "domain", "name": " xiaodian.com ", "note": "阿里云"}, headers=auth(worker))
    assert r.status_code == 201, r.text
    _assert_shape(r.json()[0], "ContractHandoverItem")
    client.post(H, json={"kind": "miniapp", "name": "小店点单"}, headers=auth(worker))
    rows = client.get(H, headers=auth(requester)).json()
    assert [(x["kind"], x["name"], x["confirmed_at"]) for x in rows] == [("domain", "xiaodian.com", None), ("miniapp", "小店点单", None)]
    assert client.post(f"{H}/{rows[0]['id']}/confirm", headers=auth(worker)).status_code == 403, "执行方不能替发单人确认"
    r = client.post(f"{H}/{rows[0]['id']}/confirm", headers=auth(requester))
    assert r.status_code == 200 and r.json()[0]["confirmed_at"] and r.json()[1]["confirmed_at"] is None
    again = client.post(f"{H}/{rows[0]['id']}/confirm", headers=auth(requester)).json()
    assert again[0]["confirmed_at"] == r.json()[0]["confirmed_at"], "再点一次不改时间"
    with SessionLocal() as db:
        n = db.query(Notification).filter(Notification.user_id == worker["id"], Notification.title == "发单人确认了一项账号交接").count()
    assert n == 1, "确认时通知执行方一次"
    d = client.delete(f"{H}/{rows[0]['id']}", headers=auth(worker))
    assert d.status_code == 409 and d.json()["detail"]["code"] == "handover_confirmed", "确认过的不能删"
    assert client.delete(f"{H}/{rows[1]['id']}", headers=auth(worker)).status_code == 200


def test_only_the_executor_lists_only_while_funded_and_confirming_works_after_release(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    H = f"{API}/contracts/{cid}/handover"
    item = {"kind": "server", "name": "云服务器"}
    r = client.post(H, json=item, headers=auth(requester))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_party", "发单人不能替执行方登记"
    for bad in ({**item, "kind": "email"}, {**item, "name": ""}, {**item, "x": 1}):
        assert client.post(H, json=bad, headers=auth(worker)).status_code == 422, bad
    first = client.post(H, json=item, headers=auth(worker)).json()[0]
    assert client.delete(f"{H}/{first['id']}", headers=auth(requester)).status_code == 403
    stranger = register(client, "13600003571", "路人")
    assert client.get(H, headers=auth(stranger)).status_code == 403
    other, _ = _three_stage(client, requester, worker)
    assert client.post(f"{API}/contracts/{other}/handover/{first['id']}/confirm", headers=auth(requester)).status_code == 404
    with SessionLocal() as db:
        c = db.get(Contract, cid)
        c.status = "released"
        db.commit()
    r = client.post(H, json=item, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_active", "放款以后清单就定了"
    assert client.post(f"{H}/{first['id']}/confirm", headers=auth(requester)).status_code == 200, "放款后发单人照样能确认"
