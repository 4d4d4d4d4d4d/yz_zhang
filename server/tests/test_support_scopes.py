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
    assert r == {"categories": ["funds"], "declared": True, "labels": r["labels"], "auto_assign": False}
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


# --------------------------------- ESCA-064 新工单按类别自动指派（237 号 spec，V264）
def test_new_tickets_go_to_the_least_loaded_opted_in_agent(client):
    from tests.test_ticket_assign_reply import _titles

    a = _admin(client, "13800334031", ["support"])
    b = _admin(client, "13800334032", ["support"])
    lazy = _admin(client, "13800334033", ["support"])
    put = f"{API}/admin/support/my-categories"
    client.put(put, json={"categories": ["funds"], "auto_assign": True}, headers=auth(a))
    client.put(put, json={"categories": ["funds", "account"], "auto_assign": True}, headers=auth(b))
    client.put(put, json={"categories": ["funds"]}, headers=auth(lazy))            # 没打开：不分给他
    assert client.get(put, headers=auth(b)).json()["auto_assign"] is True
    asker = register(client, "13800334040", "常来问的人")      # 一个人提多张，免得注册太多次被限流

    def post(cat):
        return client.post(f"{API}/support/tickets", json={"subject": "有个问题", "category": cat}, headers=auth(asker)).json()["id"]

    t1, t2, t3 = (post("funds") for _ in range(3))
    with SessionLocal() as db:
        got = [db.get(Ticket, t).assignee_id for t in (t1, t2, t3)]
    assert got == [a["id"], b["id"], a["id"]], "手上未结的最少的先分，一样多时编号小的先"
    assert any("新工单 #" in t for t in _titles(client, a))
    acc = post("account")
    gen = post("general")
    with SessionLocal() as db:
        assert db.get(Ticket, acc).assignee_id == b["id"], "只负责资金的不分账号类"
        assert db.get(Ticket, gen).assignee_id is None, "没人负责就不分，照旧进公共队列"
    # 已结的不算手上的量：甲手上三张都结了（总数比乙多），下一张仍给甲（乙手上还有两张开着）
    extra = post("funds")
    with SessionLocal() as db:
        assert db.get(Ticket, extra).assignee_id == a["id"]
        for t in (t1, t3, extra):
            db.get(Ticket, t).status = "resolved"
        db.commit()
    nxt = post("funds")
    with SessionLocal() as db:
        assert db.get(Ticket, nxt).assignee_id == a["id"]
    # 关掉之后不再分；改类别时不传 auto_assign 保持原样
    client.put(put, json={"categories": ["funds"]}, headers=auth(b))
    assert client.get(put, headers=auth(b)).json()["auto_assign"] is True
    client.put(put, json={"categories": ["funds"], "auto_assign": False}, headers=auth(b))
    client.put(put, json={"categories": ["funds"], "auto_assign": False}, headers=auth(a))
    t4 = post("funds")
    with SessionLocal() as db:
        assert db.get(Ticket, t4).assignee_id is None


def test_faq_escalation_ticket_is_auto_assigned_too(client):
    a = _admin(client, "13800334061", ["support"])
    client.put(f"{API}/admin/support/my-categories", json={"categories": ["general"], "auto_assign": True}, headers=auth(a))
    u = register(client, "13800334062", "提问的人")
    r = client.post(f"{API}/support/ask", json={"question": "一个知识库里绝对没有的奇怪问题 xyzzy"}, headers=auth(u)).json()
    assert r["escalate_to_human"] is True
    with SessionLocal() as db:
        assert db.get(Ticket, r["ticket_id"]).assignee_id == a["id"]
