"""SCN-246 / SCN-247 第三十四轮场景发掘：接送孩子、婚恋介绍（353 号 spec，V380）。

接送孩子复用「陪练看护」类目（要审核通过的无犯罪记录证明）；婚恋介绍是新类目、不要资质。
接送：只交给约定的人、固定路线位置共享、头盔与儿童座椅、不喂药不拍照、走散马上联系；
婚恋：不包成费用分阶段、资料真实不用婚托、资料本人同意才给、见面安全、不做彩礼中间人。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import MINOR_CARE_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"
MINOR = {"minor_involved": True, "guardian_mode": "public_place", "guardian_consented": True}


def test_child_pickup_pack_hands_over_only_to_agreed_adults():
    d, problems = schema.validate(_load("child-pickup"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("带回自己家" in f for f in a.forbidden) and any("没约定的人" in f for f in a.forbidden)
    assert any("吃药" in f for f in a.forbidden) and any("头盔" in f for f in a.forbidden)
    assert a.fallback_category == "陪练看护" and _categories()["陪练看护"]["required_cert"] == MINOR_CARE_CERT
    t = d.task_templates[0]
    assert t.category == "陪练看护" and "全程位置共享" in t.description and "开位置共享" in t.visit_checklist


def test_matchmaking_pack_never_guarantees_and_never_uses_fake_dates():
    d, problems = schema.validate(_load("matchmaking"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("包成" in f for f in a.forbidden) and any("婚托" in f for f in a.forbidden)
    assert any("彩礼" in f for f in a.forbidden) and any("对方资料" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["婚恋介绍"]
    assert "按阶段付费" in d.task_templates[0].description


@pytest.mark.parametrize("key", ["child-pickup", "matchmaking"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_only_a_reviewed_criminal_record_certificate_can_pick_up_children(client, requester):
    ops = make_admin(client, "13600003801", "运营")
    r = _post(client, requester, title="放学接送", description="小学二年级，四点半放学，交给奶奶", category="陪练看护", **MINOR)
    assert r.status_code in (200, 201), r.text
    t = r.json()
    w = make_verified(client, "13600003802")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and MINOR_CARE_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=MINOR_CARE_CERT, expires_at=(utcnow() + timedelta(days=180)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "派出所证明清晰"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    m = _post(client, requester, title="想找个人介绍对象", description="三十岁，在上海", category="婚恋介绍", is_remote=True)
    assert m.status_code in (200, 201), m.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("child-pickup", "child-pickup-helper", ("13900003931", "13900003932"), "家里没人能把孩子带回我家吗", "只交给约定的人"),
    ("child-pickup", "child-pickup-helper", ("13900003933", "13900003934"), "路上能顺便去趟超市吗", "走固定路线，全程位置共享"),
    ("child-pickup", "child-pickup-helper", ("13900003935", "13900003936"), "骑电动车接孩子要注意什么", "步行牵手，电动车戴头盔用儿童座椅"),
    ("child-pickup", "child-pickup-helper", ("13900003937", "13900003938"), "孩子说肚子疼", "不喂药，不给孩子拍照发出去"),
    ("child-pickup", "child-pickup-helper", ("13900003939", "13900003940"), "到了没接到孩子", "没接到、走散了，马上联系家长和学校"),
    ("matchmaking", "matchmaking-helper", ("13900003941", "13900003942"), "客户要我保证能结婚", "不承诺包成，费用分阶段"),
    ("matchmaking", "matchmaking-helper", ("13900003943", "13900003944"), "发现对方其实已婚", "资料真实，不用婚托"),
    ("matchmaking", "matchmaking-helper", ("13900003945", "13900003946"), "能把女方照片发给别人看吗", "对方资料本人同意才给"),
    ("matchmaking", "matchmaking-helper", ("13900003947", "13900003948"), "对方见了两次就借钱", "首次见面公共场所，提醒不借钱不转账"),
    ("matchmaking", "matchmaking-helper", ("13900003949", "13900003950"), "男方家想让我帮着谈彩礼", "不做彩礼和借贷的中间人"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("child-pickup", "child-pickup-helper", ("13900003951", "13900003952"), "有人冒充家长", "只交给约定的人"),
    ("child-pickup", "child-pickup-helper", ("13900003953", "13900003954"), "孩子能坐后座吗", "步行牵手，电动车戴头盔用儿童座椅"),
    ("child-pickup", "child-pickup-helper", ("13900003955", "13900003956"), "孩子找不到了", "没接到、走散了，马上联系家长和学校"),
    ("matchmaking", "matchmaking-helper", ("13900003957", "13900003958"), "怎么核实", "资料真实，不用婚托"),
    ("matchmaking", "matchmaking-helper", ("13900003959", "13900003960"), "网恋对象约见面", "首次见面公共场所，提醒不借钱不转账"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
