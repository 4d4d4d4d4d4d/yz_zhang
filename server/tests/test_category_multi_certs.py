"""SCN-181 一个类目要多张资质（307 号 spec，V334）。

V333 的「母婴护理」照护的是新生儿：只要健康证明不够，还应要无犯罪记录证明（与「陪练看护」同一道关）。类目以前只能设一张
资质（required_cert），现在可以再设几张（extra_certs），张张都要有；报名时说清还缺哪几张。只设一张的类目一切照旧。
"""
from app.core.db import SessionLocal
from app.modules.task.models import Category
from app.modules.task.service import category_certs
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post

API = "/api/v1"


def _approve(client, worker, name, admin):
    extra = {"issuer": "上海市公安局某派出所"} if name == "无犯罪记录证明" else {}
    app_id = apply_cert(client, worker, name=name, **extra).json()["id"]
    r = client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件清晰，姓名一致"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text


def test_category_certs_lists_required_first_then_extras_without_blanks_or_repeats():
    assert category_certs(None) == []
    assert category_certs(Category(name="x", required_cert="", extra_certs=[])) == []
    assert category_certs(Category(name="x", required_cert="健康证明", extra_certs=[" 无犯罪记录证明 ", "", "健康证明"])) \
        == ["健康证明", "无犯罪记录证明"]
    assert category_certs(Category(name="x", required_cert="", extra_certs=["律师"])) == ["律师"]


def test_infant_care_needs_both_and_says_which_one_is_missing(client, requester):
    cats = {c["name"]: c for c in client.get(f"{API}/categories").json()}
    assert cats["母婴护理"]["required_cert"] == "健康证明" and cats["母婴护理"]["extra_certs"] == ["无犯罪记录证明"]
    assert "extra_certs" not in cats["上门做饭"], "只要一张的类目不出这个字段"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(cats["母婴护理"], "Category")

    t = _post(client, requester, title="找育儿嫂", description="宝宝三个月", category="母婴护理").json()
    w = make_verified(client, "13600003341")
    admin = make_admin(client, "13800334101")
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    d = r.json()["detail"]
    assert r.status_code == 400 and d["code"] == "certification_required"
    assert d["message"].startswith("该类目需「健康证明」「无犯罪记录证明」2 项职业资质，你还缺「健康证明」「无犯罪记录证明」"), d
    _approve(client, w, "健康证明", admin)
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert r.status_code == 400 and "你还缺「无犯罪记录证明」：" in r.json()["detail"]["message"], "只说还缺的那张"
    _approve(client, w, "无犯罪记录证明", admin)
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201

    cook = _post(client, requester, title="上门做饭", description="三口之家", category="上门做饭").json()
    w2 = make_verified(client, "13600003342")
    r = client.post(f"{API}/tasks/{cook['id']}/applications", json={}, headers=auth(w2))
    assert r.json()["detail"]["message"] == "该类目需「健康证明」职业资质，请提交证件影像并通过平台核验后接单", "单张的文案一字不差"


def test_ops_can_set_extra_certs_and_the_risk_hint_lists_them(client, requester):
    ops = make_admin(client, "13800334102")
    c = client.post(f"{API}/admin/categories", json={"name": "高空清洗", "required_cert": "高处作业操作证",
                                                     "extra_certs": ["健康证明", " ", "高处作业操作证"]}, headers=auth(ops))
    assert c.status_code == 201, c.text
    with SessionLocal() as db:
        assert db.get(Category, c.json()["id"]).extra_certs == ["健康证明"], "去空、去掉与主资质重复的"
    u = client.patch(f"{API}/admin/categories/{c.json()['id']}?extra_certs=健康证明、无犯罪记录证明", headers=auth(ops))
    assert u.status_code == 200 and u.json()["extra_certs"] == ["健康证明", "无犯罪记录证明"]
    clear = client.patch(f"{API}/admin/categories/{c.json()['id']}?extra_certs=", headers=auth(ops))
    assert "extra_certs" not in clear.json(), "清空后只要主资质"
    many = client.patch(f"{API}/admin/categories/{c.json()['id']}?extra_certs=甲,乙,丙,丁,戊,己", headers=auth(ops))
    assert many.status_code == 400 and many.json()["detail"]["code"] == "too_many_certs"

    from app.modules.profiles.service import task_profile

    with SessionLocal() as db:
        risks = task_profile(db, {"title": "找育儿嫂", "description": "宝宝三个月", "category": "母婴护理"})["risks"]
    assert {"kind": "cert", "text": "这个类目要求「健康证明」「无犯罪记录证明」资质，没有的人报不了名"} in risks
