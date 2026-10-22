"""ESCA-061 按类别分派客服（234 号 spec，V261）。

以前没人接手的工单超时，提醒发给所有客服：钱没到账的工单叫醒了只会处理账号问题的人，
懂资金的那位淹没在一堆提醒里。现在客服自己声明负责哪几类，超时提醒优先叫负责这一类的人；
队列可以只看自己负责的类别。没声明的客服视为什么都管。
"""
from app.core.db import SessionLocal
from app.modules.support import escalation
from app.modules.support.models import Ticket
from tests.conftest import auth, register
from tests.test_ticket_assign_reply import _admin

API = "/api/v1"


def _ticket(client, phone, category):
    u = register(client, phone, "提问的人")
    return client.post(f"{API}/support/tickets", json={"subject": "有个问题", "category": category}, headers=auth(u)).json()["id"]


def test_declare_scope_and_validation(client):
    a = _admin(client, "13800334001", ["support"])
    r = client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()
    assert r["declared"] is False and r["categories"] == ["funds", "account", "general"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r, "SupportScope")
    r = client.put(f"{API}/admin/support/my-categories", json={"categories": ["funds"]}, headers=auth(a)).json()
    assert r == {"categories": ["funds"], "declared": True, "labels": r["labels"]}
    bad = client.put(f"{API}/admin/support/my-categories", json={"categories": ["vip"]}, headers=auth(a))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "ticket_bad_category"
    empty = client.put(f"{API}/admin/support/my-categories", json={"categories": []}, headers=auth(a))
    assert empty.json()["detail"]["code"] == "support_categories_empty"
    fin = _admin(client, "13800334002", ["finance"])
    assert client.get(f"{API}/admin/support/my-categories", headers=auth(fin)).status_code == 403


def test_unclaimed_overdue_ticket_wakes_agents_covering_its_category(client):
    funds = _admin(client, "13800334011", ["support"])
    account = _admin(client, "13800334012", ["support"])
    anyone = _admin(client, "13800334013", ["support"])          # 没声明：什么都管
    client.put(f"{API}/admin/support/my-categories", json={"categories": ["funds"]}, headers=auth(funds))
    client.put(f"{API}/admin/support/my-categories", json={"categories": ["account", "general"]}, headers=auth(account))
    tid = _ticket(client, "13800334014", "funds")
    with SessionLocal() as db:
        t = db.get(Ticket, tid)
        assert sorted(escalation.level1_recipients(db, t)) == sorted([funds["id"], anyone["id"]])
        t.category = "account"
        assert sorted(escalation.level1_recipients(db, t)) == sorted([account["id"], anyone["id"]])
    # 一个负责资金类的都没有：照旧叫全部，不能没人管
    client.put(f"{API}/admin/support/my-categories", json={"categories": ["general"]}, headers=auth(anyone))
    client.put(f"{API}/admin/support/my-categories", json={"categories": ["account"]}, headers=auth(funds))
    with SessionLocal() as db:
        t = db.get(Ticket, tid)
        assert t.category == "funds"
        assert sorted(escalation.level1_recipients(db, t)) == sorted([funds["id"], account["id"], anyone["id"]])


def test_queue_filter_only_my_categories(client):
    a = _admin(client, "13800334021", ["support"])
    f = _ticket(client, "13800334022", "funds")
    g = _ticket(client, "13800334023", "general")
    url = f"{API}/admin/tickets"
    assert {f, g} <= {x["id"] for x in client.get(url, params={"my_categories": True}, headers=auth(a)).json()}, "没声明不筛"
    client.put(f"{API}/admin/support/my-categories", json={"categories": ["funds"]}, headers=auth(a))
    ids = {x["id"] for x in client.get(url, params={"my_categories": True}, headers=auth(a)).json()}
    assert f in ids and g not in ids
    assert {f, g} <= {x["id"] for x in client.get(url, headers=auth(a)).json()}, "不勾就照旧全看"
