"""SCN-212 资质名别名（332 号 spec，V359）：「电工」与「低压电工作业操作证」是同一张证。

种子类目「电工维修」一直要「电工」；V352 的「水电维修」要证上的正式名称「低压电工作业操作证」。
以前持其中一个名字的人接不了另一个类目的单，还能把同一张证再申请一遍。现在：持任一个名字，两个类目都能接；
已经持有或在审其中一个，不能再申请另一个；拦下时提示里写明「持另一个名字的也可以」；没有别名的类目提示一字不变。
"""
from datetime import timedelta

from app.modules.account.cert_service import cert_aliases
from app.modules.account.models import utcnow
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post

API = "/api/v1"


def _approve(client, admin, app_id):
    r = client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件清晰，姓名一致"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text


def test_either_name_opens_both_electrician_categories(client, requester):
    admin = make_admin(client, "13600003591")
    legacy = make_verified(client, "13600003592")
    formal = make_verified(client, "13600003593")
    _approve(client, admin, apply_cert(client, legacy, name="电工").json()["id"])
    _approve(client, admin, apply_cert(client, formal, name="低压电工作业操作证",
                                       expires_at=(utcnow() + timedelta(days=365 * 5)).isoformat()).json()["id"])
    for cat in ("电工维修", "水电维修"):
        for who in (legacy, formal):
            t = _post(client, requester, title=f"{cat}的活", description="插座", category=cat).json()
            r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(who))
            assert r.status_code == 201, (cat, r.text)


def test_the_same_certificate_cannot_be_applied_for_twice_under_two_names(client):
    admin = make_admin(client, "13600003594")
    w = make_verified(client, "13600003595")
    first = apply_cert(client, w, name="电工").json()["id"]
    r = apply_cert(client, w, name="低压电工作业操作证", expires_at=(utcnow() + timedelta(days=365)).isoformat())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "application_pending", "在审的算同一张"
    _approve(client, admin, first)
    r = apply_cert(client, w, name="低压电工作业操作证", expires_at=(utcnow() + timedelta(days=365)).isoformat())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "certification_exists", "持有的算同一张"


def test_the_refusal_mentions_the_other_name_and_other_categories_read_the_same(client, requester):
    w = make_verified(client, "13600003596")
    t = _post(client, requester, title="配电箱检修", description="x", category="电工维修").json()
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert r.json()["detail"]["message"] == "该类目需「电工」职业资质（持「低压电工作业操作证」也可以），请提交证件影像并通过平台核验后接单"
    t = _post(client, requester, title="钥匙锁屋里了", description="x", category="上门开锁").json()
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert r.json()["detail"]["message"] == "该类目需「开锁备案证明」职业资质，请提交证件影像并通过平台核验后接单", "没有别名的一字不变"
    assert cert_aliases("健康证明") == {"健康证明"}
