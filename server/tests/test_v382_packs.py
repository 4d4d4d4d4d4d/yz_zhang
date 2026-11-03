"""SCN-249 / SCN-250 第三十五轮场景发掘：游泳私教、除虫灭鼠（355 号 spec，V382）。

两个数据文件、两个新类目：「游泳私教」要审核通过的游泳社会体育指导员证书（游泳是高危险性体育项目），
这张证进高风险全抽名单；「除虫灭鼠」不要资质。
游泳：持证、只在有救生员的泳池、视线不离、先看水性、不承诺包会；除虫：先找源头、只用登记过的药、
孩子宠物先说、施工须知、不承诺断根。
"""
from datetime import timedelta

import pytest

from app.modules.account import cert_spot
from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import SWIM_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_swim_coach_pack_needs_a_licence_and_a_lifeguarded_pool():
    d, problems = schema.validate(_load("swim-coach"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("野外水域" in f for f in a.forbidden) and any("包会" in f for f in a.forbidden)
    assert any("没有游泳社会体育指导员证书" in f for f in a.forbidden)
    assert _categories()["游泳私教"]["required_cert"] == SWIM_CERT
    t = d.task_templates[0].description
    assert "有救生员值守" in t and "不承诺包会" in t and "视线不离" in t


def test_swim_licence_is_always_spot_checked():
    assert SWIM_CERT in cert_spot.high_risk_certs()


def test_pest_control_pack_bans_illegal_poisons_and_one_shot_promises():
    d, problems = schema.validate(_load("pest-control"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("毒鼠强" in f for f in a.forbidden) and any("断根" in f for f in a.forbidden)
    assert any("够得着" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["除虫灭鼠"]
    t = d.task_templates[0].description
    assert "农药登记" in t and "复查" in t
    assert d.task_templates[0].visits_planned == 2


@pytest.mark.parametrize("key", ["swim-coach", "pest-control"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_only_a_reviewed_swim_licence_can_take_a_lesson(client, requester):
    ops = make_admin(client, "13600003821", "运营")
    t = _post(client, requester, title="成人零基础学蛙泳", description="小区会所泳池，有救生员", category="游泳私教").json()
    w = make_verified(client, "13600003822")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and SWIM_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=SWIM_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证书编号可查"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    pest = _post(client, requester, title="厨房灭蟑螂", description="老小区一楼", category="除虫灭鼠")
    assert pest.status_code in (200, 201), pest.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("swim-coach", "swim-coach-helper", ("13900004001", "13900004002"), "家长想让我带孩子去水库练", "只在有救生员的正规泳池上课"),
    ("swim-coach", "swim-coach-helper", ("13900004003", "13900004004"), "我一个人带八个孩子行吗", "一对一或小班，人在水里视线不离"),
    ("swim-coach", "swim-coach-helper", ("13900004005", "13900004006"), "孩子怕水不敢下", "第一节先看水性，怕水的不硬拉"),
    ("swim-coach", "swim-coach-helper", ("13900004007", "13900004008"), "家长要我保证十节课包会", "课时和目标写清，不承诺包会"),
    ("swim-coach", "swim-coach-helper", ("13900004009", "13900004010"), "我还没考证能先接单吗", "持游泳社会体育指导员证书上岗"),
    ("pest-control", "pest-control-helper", ("13900004011", "13900004012"), "客户问用的什么药", "只用登记过的药，按标签用量"),
    ("pest-control", "pest-control-helper", ("13900004013", "13900004014"), "家里有猫和鱼缸怎么办", "家里有孩子宠物先说，药饵放在够不着的地方"),
    ("pest-control", "pest-control-helper", ("13900004015", "13900004016"), "客户要我保证一次断根", "写清复查几次，不承诺一次断根"),
    ("pest-control", "pest-control-helper", ("13900004017", "13900004018"), "喷完药多久能进屋", "施工前收好食物餐具，讲清多久能回屋"),
    ("pest-control", "pest-control-helper", ("13900004019", "13900004020"), "老鼠洞要不要堵", "先找源头，堵洞清源再下药"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("swim-coach", "swim-coach-helper", ("13900004021", "13900004022"), "能去江边练吗", "只在有救生员的正规泳池上课"),
    ("swim-coach", "swim-coach-helper", ("13900004023", "13900004024"), "上课能看手机吗", "一对一或小班，人在水里视线不离"),
    ("swim-coach", "swim-coach-helper", ("13900004025", "13900004026"), "多久能学会", "课时和目标写清，不承诺包会"),
    ("pest-control", "pest-control-helper", ("13900004027", "13900004028"), "有没有猛药", "只用登记过的药，按标签用量"),
    ("pest-control", "pest-control-helper", ("13900004029", "13900004030"), "孕妇在家行不行", "家里有孩子宠物先说，药饵放在够不着的地方"),
    ("pest-control", "pest-control-helper", ("13900004031", "13900004032"), "过一个月又有了", "写清复查几次，不承诺一次断根"),
    ("pest-control", "pest-control-helper", ("13900004033", "13900004034"), "蟑螂到底从哪来的", "先找源头，堵洞清源再下药"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
