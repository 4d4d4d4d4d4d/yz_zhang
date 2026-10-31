"""SCN-196 / SCN-197 第十八轮场景发掘：陪诊、家具安装（322 号 spec，V349）。

交付物是两个数据文件、两个新类目（都不要资质）。陪诊的关口是「只陪不替」：不给医疗建议、不代签字、挂号只走官方渠道
（加价倒卖号源的单发单时就被拦下）；家具安装的关口是高柜固定上墙、打孔前查管线。
"""
import pytest

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_escort_pack_accompanies_but_never_decides():
    d, problems = schema.validate(_load("hospital-escort"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "sign", "publish", "share_personal"} <= set(a.human_gates)
    assert any("倒卖号源" in f for f in a.forbidden) and any("医疗建议" in f for f in a.forbidden)
    assert any("签字" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["陪诊"]
    t = d.task_templates[0]
    assert "官方渠道" in t.description and "不代签字" in t.description and "记医嘱" in t.visit_checklist


def test_assembly_pack_anchors_tall_furniture_and_checks_the_wall():
    d, problems = schema.validate(_load("furniture-assembly"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不固定上墙" in f for f in a.forbidden) and any("暗管暗线" in f for f in a.forbidden)
    assert any("凑合" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["家具安装"]
    t = d.task_templates[0]
    assert "固定上墙" in t.description and "高柜上墙" in t.visit_checklist


def test_escort_orders_go_through_but_scalping_appointments_is_stopped(client, requester):
    ok = _post(client, requester, title="陪我妈去复诊", description="号已在医院 App 挂好，陪着取药、记医嘱", category="陪诊")
    assert ok.status_code in (200, 201), ok.text
    w = make_verified(client, "13600003491")
    assert client.post(f"{API}/tasks/{ok.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201
    bad = _post(client, requester, title="陪诊加抢号", description="加价帮我弄个专家号，弄到转卖给别人", category="陪诊")
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "errand_restricted", bad.text
    sofa = _post(client, requester, title="装两个抽屉柜", description="要固定上墙", category="家具安装").json()
    assert client.post(f"{API}/tasks/{sofa['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("hospital-escort", "escort-helper", ("13900003491", "13900003492"), "客户问我能不能弄到专家号", "挂号只走官方渠道：不加号、不抢号、不倒卖号源"),
    ("hospital-escort", "escort-helper", ("13900003493", "13900003494"), "医生要家属签手术同意书怎么办", "签字、做决定是病人和家属的事"),
    ("furniture-assembly", "assembly-helper", ("13900003495", "13900003496"), "抽屉柜要不要固定在墙上", "抽屉柜、书柜、衣柜：一定固定上墙，防倾倒"),
    ("furniture-assembly", "assembly-helper", ("13900003497", "13900003498"), "配件少了一颗螺丝怎么办", "配件缺了：拍照告诉客户，不拿别的凑"),
    # 人们真正会说的话：正文里没有这些词，靠标签接住
    ("hospital-escort", "escort-helper", ("13900003499", "13900003500"), "老人让我替他在单子上签名", "签字、做决定是病人和家属的事"),
    ("furniture-assembly", "assembly-helper", ("13900003501", "13900003502"), "柜子会不会翻倒压到小孩", "抽屉柜、书柜、衣柜：一定固定上墙，防倾倒"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
