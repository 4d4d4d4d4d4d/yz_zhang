"""SCN-213 资质别名在后台维护（334 号 spec，V361）：运营提出「这两个名字是同一张证」，另一位管理员确认才生效。

V359 把「电工」与「低压电工作业操作证」写死在代码里；新出一个叫法就要发版。配错等于放松准入（把两张不同的证
当成一张），所以四眼：提出要写理由、自己不能确认自己的、确认才生效；任何一位都可以收回，收回立刻失效。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.admin.models import AdminAudit
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post

API = "/api/v1"
A = f"{API}/admin/cert-aliases"


def _approve_cert(client, admin, user, name):
    app_id = apply_cert(client, user, name=name, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    r = client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件清晰，姓名一致"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text


def test_an_alias_takes_effect_only_after_a_second_admin_approves_and_stops_when_revoked(client, requester):
    from tests.test_client_shape_alignment import _assert_shape

    ops1, ops2 = make_admin(client, "13600003611", "运营甲"), make_admin(client, "13600003612", "运营乙")
    cat = client.post(f"{API}/admin/categories", json={"name": "别名测试焊接", "required_cert": "焊工证"}, headers=auth(ops1))
    assert cat.status_code == 201, cat.text
    w = make_verified(client, "13600003613")
    _approve_cert(client, ops1, w, "熔化焊接与热切割作业操作证")
    t = _post(client, requester, title="焊个铁门", description="x", category="别名测试焊接").json()
    apply = lambda: client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))   # noqa: E731
    assert apply().status_code == 400, "还没配别名"
    r = client.post(A, json={"a": " 焊工证 ", "b": "熔化焊接与热切割作业操作证", "reason": "焊工证是俗称，证上写的是这个"},
                    headers=auth(ops1))
    assert r.status_code == 201 and r.json()["status"] == "pending", r.text
    _assert_shape(r.json(), "CertAliasItem")
    alias_id = r.json()["id"]
    assert apply().status_code == 400, "提出了还没确认，不生效"
    me = client.post(f"{A}/{alias_id}/approve", headers=auth(ops1))
    assert me.status_code == 403 and me.json()["detail"]["code"] == "cert_alias_self", "不能确认自己提出的"
    ok = client.post(f"{A}/{alias_id}/approve", headers=auth(ops2))
    assert ok.status_code == 200 and ok.json()["status"] == "active" and ok.json()["approved_by"] == ops2["id"]
    _assert_shape(ok.json(), "CertAliasItem")
    assert apply().status_code == 201, "确认后持另一个名字的证能接"
    listed = client.get(A, headers=auth(ops1)).json()
    _assert_shape(listed, "CertAliasList")
    assert ["低压电工作业操作证", "电工"] in listed["builtin"], "代码里写死的那组也列出来"
    assert listed["items"][0]["status"] == "active"
    rv = client.post(f"{A}/{alias_id}/revoke", headers=auth(ops1))
    assert rv.status_code == 200 and rv.json()["status"] == "revoked"
    _assert_shape(rv.json(), "CertAliasItem")
    t2 = _post(client, requester, title="再焊一个", description="x", category="别名测试焊接").json()
    assert client.post(f"{API}/tasks/{t2['id']}/applications", json={}, headers=auth(w)).status_code == 400, "收回立刻失效"
    assert client.post(f"{A}/{alias_id}/approve", headers=auth(ops2)).status_code == 409, "处理过的不能再确认"
    with SessionLocal() as db:
        actions = [a.action for a in db.query(AdminAudit).filter(AdminAudit.target_id == alias_id,
                                                                 AdminAudit.action.like("cert_alias_%"))]
    assert actions == ["cert_alias_propose", "cert_alias_approve", "cert_alias_revoke"], "三步都进审计"


def test_bad_proposals_and_who_may_touch_aliases(client):
    ops1 = make_admin(client, "13600003614", "运营丙")
    r = client.post(A, json={"a": "电工", "b": "低压电工作业操作证", "reason": "已经是一组了"}, headers=auth(ops1))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cert_alias_exists"
    r = client.post(A, json={"a": "甲证", "b": " 甲证 ", "reason": "同一个名字"}, headers=auth(ops1))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "cert_alias_same"
    assert client.post(A, json={"a": "甲证", "b": "乙证", "reason": "短"}, headers=auth(ops1)).status_code == 422, "理由要写"
    first = client.post(A, json={"a": "甲证", "b": "乙证", "reason": "同一张证的两个叫法"}, headers=auth(ops1))
    assert first.status_code == 201
    r = client.post(A, json={"a": "乙证", "b": "甲证", "reason": "再提一次，换个顺序"}, headers=auth(ops1))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cert_alias_pending", "顺序不同也是同一对"
    support = make_admin(client, "13600003615", "客服")
    with SessionLocal() as db:
        db.get(User, support["id"]).admin_roles = ["support"]
        db.commit()
    assert client.get(A, headers=auth(support)).status_code == 403, "只给运营"
    assert client.post(f"{A}/{first.json()['id']}/approve", headers=auth(support)).status_code == 403
    w = make_verified(client, "13600003616")
    assert client.get(A, headers=auth(w)).status_code == 403


def test_aliases_chain_together(client):
    """甲=乙（代码里写死的）、乙=丙（后台配的）：甲丙也是同一张证。"""
    from app.modules.account.cert_service import cert_aliases

    ops1, ops2 = make_admin(client, "13600003617", "运营丁"), make_admin(client, "13600003618", "运营戊")
    r = client.post(A, json={"a": "低压电工作业操作证", "b": "低压电工证", "reason": "证上的旧写法"}, headers=auth(ops1))
    client.post(f"{A}/{r.json()['id']}/approve", headers=auth(ops2))
    with SessionLocal() as db:
        assert cert_aliases("电工", db) == {"电工", "低压电工作业操作证", "低压电工证"}
        assert cert_aliases("电工") == {"电工", "低压电工作业操作证"}, "不给 db 的老调用只看写死的"
