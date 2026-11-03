"""SCN-255 / SCN-256 第三十八轮场景发掘：燃气灶与热水器安装、成人外语口语陪练（362 号 spec，V389）。

「燃气具安装」要审核通过的从业资格证明，这张证进高风险全抽名单（燃气爆炸、一氧化碳中毒不可挽回）；
「外语陪练」不要资质，但只面向成年人：中小学学科辅导照旧被 K12 规则拦下（213 号 spec）。
"""
from datetime import timedelta

import pytest

from app.modules.account import cert_spot
from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.k12 import is_k12_subject_tutoring
from app.modules.task.service import GAS_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_gas_pack_needs_a_licence_and_never_repipes_or_flame_tests():
    d, problems = schema.validate(_load("gas-appliance-install"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("表前管道" in f for f in a.forbidden) and any("明火" in f for f in a.forbidden)
    assert any("浴室" in f for f in a.forbidden) and any("没有从业资格" in f for f in a.forbidden)
    assert _categories()["燃气具安装"]["required_cert"] == GAS_CERT
    t = d.task_templates[0].description
    assert "不改燃气管" in t and "肥皂水检漏" in t and "烟管伸出室外" in t


def test_gas_licence_is_always_spot_checked():
    assert GAS_CERT in cert_spot.high_risk_certs()


def test_language_pack_is_for_adults_and_never_guarantees_scores():
    d, problems = schema.validate(_load("language-practice"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("保过" in f for f in a.forbidden) and any("中小学" in f for f in a.forbidden)
    assert any("录音" in f for f in a.forbidden) and "share_personal" in a.human_gates
    assert "required_cert" not in _categories()["外语陪练"]
    t = d.task_templates[0].description
    assert "成年人" in t and "不承诺提分保过" in t


@pytest.mark.parametrize("key", ["gas-appliance-install", "language-practice"])
def test_templates_do_not_trip_the_errand_or_k12_guards(key):
    t = _load(key)["task_templates"][0]
    text = f"{t['title']} {t['description']}"
    assert restricted_errand(text) is None and not is_k12_subject_tutoring(text)


def test_a_childs_english_tutoring_order_is_still_blocked(client, requester):
    """同一个类目，写成给孩子补英语就是中小学学科辅导：K12 规则照拦。"""
    assert is_k12_subject_tutoring("外语陪练：给初二的孩子补习英语")
    r = _post(client, requester, title="英语陪练", description="给初二的孩子补习英语", category="外语陪练")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "k12_subject_tutoring", r.text
    ok = _post(client, requester, title="面试英语口语陪练", description="我下个月外企面试，练自我介绍", category="外语陪练")
    assert ok.status_code in (200, 201), ok.text


def test_only_a_reviewed_gas_licence_can_take_an_install(client, requester):
    ops = make_admin(client, "13600038901", "运营")
    t = _post(client, requester, title="换燃气热水器", description="阳台，天然气", category="燃气具安装").json()
    w = make_verified(client, "13600038902")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and GAS_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=GAS_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证书编号可查"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("gas-appliance-install", "gas-install-helper", ("13900004301", "13900004302"), "客户要把燃气表挪个位置", "只装机器，不改燃气管和燃气表"),
    ("gas-appliance-install", "gas-install-helper", ("13900004303", "13900004304"), "装完能用打火机试漏吗", "装完肥皂水检漏，绝不用明火试"),
    ("gas-appliance-install", "gas-install-helper", ("13900004305", "13900004306"), "热水器能装浴室里吗", "热水器烟管伸出室外，不装浴室卧室"),
    ("gas-appliance-install", "gas-install-helper", ("13900004307", "13900004308"), "软管可以穿墙吗", "软管用合格的专用管，不穿墙不暗埋"),
    ("gas-appliance-install", "gas-install-helper", ("13900004309", "13900004310"), "我还没资质能接吗", "持燃气具安装维修资格上岗"),
    ("language-practice", "language-practice-helper", ("13900004311", "13900004312"), "家长想让我给中学生补课", "只陪成年人练，中小学学科辅导不接"),
    ("language-practice", "language-practice-helper", ("13900004313", "13900004314"), "学员要我保证雅思7分", "不承诺提分保过，不代考不代写"),
    ("language-practice", "language-practice-helper", ("13900004315", "13900004316"), "学员要准备外企面试", "按场景定目标，每次给几条具体改进"),
    ("language-practice", "language-practice-helper", ("13900004317", "13900004318"), "学员说私下转账便宜点", "在平台约课付款，不私下转账"),
    ("language-practice", "language-practice-helper", ("13900004319", "13900004320"), "上课能录音吗", "录音录像先问同意，只给对方本人"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("gas-appliance-install", "gas-install-helper", ("13900004321", "13900004322"), "客户想挪位置", "只装机器，不改燃气管和燃气表"),
    ("gas-appliance-install", "gas-install-helper", ("13900004323", "13900004324"), "怎么试漏", "装完肥皂水检漏，绝不用明火试"),
    ("gas-appliance-install", "gas-install-helper", ("13900004325", "13900004326"), "卡箍要不要换", "软管用合格的专用管，不穿墙不暗埋"),
    ("language-practice", "language-practice-helper", ("13900004327", "13900004328"), "来问的是未成年", "只陪成年人练，中小学学科辅导不接"),
    ("language-practice", "language-practice-helper", ("13900004329", "13900004330"), "能包过吗", "不承诺提分保过，不代考不代写"),
    ("language-practice", "language-practice-helper", ("13900004331", "13900004332"), "学员给我发红包", "在平台约课付款，不私下转账"),
    ("gas-appliance-install", "gas-install-helper", ("13900004333", "13900004334"), "好像漏气了", "装完肥皂水检漏，绝不用明火试"),
    ("language-practice", "language-practice-helper", ("13900004335", "13900004336"), "能帮忙补课吗", "只陪成年人练，中小学学科辅导不接"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
