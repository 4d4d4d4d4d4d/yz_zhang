"""SC-007b 变更单改期 / 改范围 + IM-009 报价卡两端接上之前补的校验（119 号 spec）。"""
import json
from datetime import timedelta

from app.modules.account.models import utcnow
from tests.conftest import auth, register, topup
from tests.test_task_flow import match_and_fund, publish_task


def _funded(client, requester, worker, **kw):
    topup(client, requester, 50000)
    task = publish_task(client, requester, **kw)
    cid = match_and_fund(client, requester, worker, task)
    return task, cid


def test_change_deadline_and_scope_together_without_touching_money(client, requester, worker):
    task, cid = _funded(client, requester, worker)
    before = client.get("/api/v1/wallet", headers=auth(requester)).json()
    new_deadline = (utcnow() + timedelta(days=9)).replace(microsecond=0)
    r = client.post(f"/api/v1/contracts/{cid}/change-orders",
                    json={"new_deadline": new_deadline.isoformat() + "Z", "scope_change": "增加两个卧室", "reason": "临时加活"},
                    headers=auth(requester))
    assert r.status_code == 201, r.text
    assert r.json()["new_amount_cents"] == 20000 and r.json()["scope_change"] == "增加两个卧室"
    order = client.get(f"/api/v1/contracts/{cid}/change-orders", headers=auth(worker)).json()[0]
    assert order["can_decide"] and order["new_deadline"].startswith(new_deadline.isoformat()[:16])
    c = client.post(f"/api/v1/contracts/{cid}/change-orders/{order['id']}/accept", headers=auth(worker)).json()
    assert c["amount_cents"] == 20000
    assert "截止时间改为" in c["terms"] and "范围调整：增加两个卧室" in c["terms"]
    t = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    assert t["deadline"].startswith(new_deadline.isoformat()[:16]) and "增加两个卧室" in t["description"]
    after = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert after == before                       # 不改价就不动钱


def test_price_and_deadline_in_one_order(client, requester, worker):
    _, cid = _funded(client, requester, worker)
    r = client.post(f"/api/v1/contracts/{cid}/change-orders",
                    json={"new_amount_cents": 26000, "new_deadline": (utcnow() + timedelta(days=5)).isoformat() + "Z",
                          "scope_change": "加做阳台"}, headers=auth(worker))
    order_id = r.json()["id"]
    c = client.post(f"/api/v1/contracts/{cid}/change-orders/{order_id}/accept", headers=auth(requester)).json()
    assert c["amount_cents"] == 26000 and "金额由 200.00 元变更为 260.00 元" in c["terms"] and "加做阳台" in c["terms"]
    w = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert w["escrow_cents"] == 26000


def test_old_price_only_calls_behave_exactly_as_before(client, requester, worker):
    _, cid = _funded(client, requester, worker)
    same = client.post(f"/api/v1/contracts/{cid}/change-orders", json={"new_amount_cents": 20000}, headers=auth(worker))
    assert same.status_code == 400 and same.json()["detail"]["code"] == "invalid_amount"
    empty = client.post(f"/api/v1/contracts/{cid}/change-orders", json={"reason": "随便"}, headers=auth(worker))
    assert empty.status_code == 400 and empty.json()["detail"]["code"] == "change_empty"
    past = client.post(f"/api/v1/contracts/{cid}/change-orders",
                       json={"new_deadline": (utcnow() - timedelta(hours=1)).isoformat() + "Z"}, headers=auth(worker))
    assert past.status_code == 400 and past.json()["detail"]["code"] == "deadline_in_past"
    ok = client.post(f"/api/v1/contracts/{cid}/change-orders", json={"new_amount_cents": 18000, "reason": "少做一间"},
                     headers=auth(worker))
    assert ok.status_code == 201 and ok.json()["new_amount_cents"] == 18000


def test_quote_card_must_be_about_a_real_task_that_concerns_the_other_side(client, requester, worker):
    task = publish_task(client, requester)
    stranger = register(client, "13900020001", "路人甲")
    # 执行方报价给发布方：可以，卡片里带标题快照与发起方角色
    conv = client.post("/api/v1/conversations/direct", json={"user_id": requester["id"]}, headers=auth(worker)).json()
    r = client.post(f"/api/v1/conversations/{conv['id']}/quote-cards",
                    json={"task_id": task["id"], "price_cents": 18000, "note": "两小时搞定"}, headers=auth(worker))
    assert r.status_code == 201, r.text
    card = [m for m in client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth(requester)).json()
            if m["kind"] == "quote"][0]
    payload = json.loads(card["content"])
    assert payload["title"] == task["title"] and payload["from_creator"] is False
    # 给和这单无关的人报这单：拒绝
    c2 = client.post("/api/v1/conversations/direct", json={"user_id": stranger["id"]}, headers=auth(worker)).json()
    r = client.post(f"/api/v1/conversations/{c2['id']}/quote-cards",
                    json={"task_id": task["id"], "price_cents": 18000}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "quote_wrong_party"
    # 发布方报自己的单（我出这个价请你做）：可以，from_creator 为真
    r = client.post(f"/api/v1/conversations/{conv['id']}/quote-cards",
                    json={"task_id": task["id"], "price_cents": 21000}, headers=auth(requester))
    assert r.status_code == 201
    # 不存在的任务
    r = client.post(f"/api/v1/conversations/{conv['id']}/quote-cards",
                    json={"task_id": 999999, "price_cents": 100}, headers=auth(worker))
    assert r.status_code == 404
