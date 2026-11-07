"""SCN-229 / SCN-230 / SCN-231 第二十七轮场景发掘：宠物洗护美容、代办年检，发单拦下年检「包过」「不上线」（342 号 spec，V369）。

两个数据文件、两个新类目（宠物美容不要资质；代办年检要开别人的车，要审核通过的驾驶证），外加发单拦截一类
（fake_inspection）。年检结果看车况：代办跑腿、在 12123 申领电子标志照常发；包过、不上线、找关系拦下。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import DRIVER_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_pet_grooming_pack_checks_first_never_sedates_and_watches_the_dryer():
    d, problems = schema.validate(_load("pet-grooming"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("镇静药" in f for f in a.forbidden) and any("烘干箱" in f for f in a.forbidden)
    assert any("剪伤了不告诉" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["宠物美容"]
    t = d.task_templates[0]
    assert "不用镇静药" in t.description and "吹干时人不离开" in t.visit_checklist


def test_inspection_runner_pack_checks_the_year_and_never_guarantees_a_pass():
    d, problems = schema.validate(_load("vehicle-inspection-runner"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("包过" in f for f in a.forbidden) and any("上线费" in f for f in a.forbidden)
    assert _categories()["代办年检"]["required_cert"] == DRIVER_CERT
    k = {x.key: x for x in d.knowledge}
    assert k["which-year-online"].kind == "policy" and k["which-year-online"].valid_until is not None, "政策要有效期"
    assert "不承诺包过" in d.task_templates[0].description


@pytest.mark.parametrize("text,kind", [
    ("年检包过，不用上线", "fake_inspection"), ("代办车检保过", "fake_inspection"), ("验车走关系花钱过", "fake_inspection"),
    ("年检不上线也能拿标", "fake_inspection"), ("帮我搞定检测，年检那天我没空", "fake_inspection"),
    ("代办年检，帮我开到检测站排队", None), ("车满两年，帮我在12123申领电子标志", None),
    ("代办年检，结果看车况，不承诺包过", None), ("年检：10 年内免上线的年份帮我申领", None),
    ("包过的雅思课", None),                      # 没说年检
    # 之前几轮的边界照旧
    ("不想自己写，代写毕业论文", "ghostwrite"), ("本店不刷单", None), ("抖音刷粉一万", "fake_traffic"),
])
def test_what_the_inspection_guard_catches(text, kind):
    assert restricted_errand(text) == kind


@pytest.mark.parametrize("key", ["pet-grooming", "vehicle-inspection-runner"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_publishing_stops_guaranteed_pass_and_says_what_is_allowed(client, requester):
    r = _post(client, requester, title="年检", description="年检包过，不用上线，价格好说", category="代办年检")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "fake_inspection", r.text
    msg = r.json()["detail"]["message"]
    assert "交管 12123" in msg and "代办年检" in msg and "申请人工复核" in msg, "说清什么可以发、有复核的路"
    rv = client.post(f"{API}/tasks/errand-reviews", json={"title": "年检", "description": "年检包过，不用上线，价格好说",
                                                           "explanation": "我想说的是不确定能不能过"}, headers=auth(requester))
    assert rv.status_code == 200 and rv.json()["kind_label"] == "年检包过不上线", "能申请复核，类别名写清"


def test_only_a_reviewed_driver_license_can_run_an_inspection(client, requester):
    ops = make_admin(client, "13600003691", "运营")
    t = _post(client, requester, title="代办年检", description="车满六年，帮我开到检测站排队", category="代办年检").json()
    w = make_verified(client, "13600003692")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and DRIVER_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=DRIVER_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件清晰，驾龄满三年"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    pet = _post(client, requester, title="给猫洗澡", description="英短，两岁", category="宠物美容")
    assert pet.status_code in (200, 201), pet.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("pet-grooming", "pet-grooming-helper", ("13900003731", "13900003732"), "猫太闹能不能给它打一针", "不给宠物用镇静药或麻醉"),
    ("pet-grooming", "pet-grooming-helper", ("13900003733", "13900003734"), "刚打完疫苗能洗吗", "洗前看状况，有病有伤先不洗"),
    ("pet-grooming", "pet-grooming-helper", ("13900003735", "13900003736"), "放烘干箱里我去忙别的行吗", "吹干时人不离开，不长时间关在热风烘干箱里"),
    ("pet-grooming", "pet-grooming-helper", ("13900003737", "13900003738"), "剪指甲剪出血了", "剪伤了马上告诉主人，严重的送医"),
    ("vehicle-inspection-runner", "inspection-runner-helper", ("13900003739", "13900003740"), "车子第四年要不要去检测站", "先查这辆车今年要不要上线"),
    ("vehicle-inspection-runner", "inspection-runner-helper", ("13900003741", "13900003742"), "客户问能不能包过", "不承诺「包过」「不上线」"),
    ("vehicle-inspection-runner", "inspection-runner-helper", ("13900003743", "13900003744"), "有违章没处理能检吗", "违章、事故先处理，交强险要有效"),
    ("vehicle-inspection-runner", "inspection-runner-helper", ("13900003745", "13900003746"), "检测费和代办费怎么写", "检测费和代办费分开写"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("pet-grooming", "pet-grooming-helper", ("13900003747", "13900003748"), "巴哥要注意啥", "洗前看状况，有病有伤先不洗"),
    ("pet-grooming", "pet-grooming-helper", ("13900003749", "13900003750"), "用吹风机要注意啥", "吹干时人不离开，不长时间关在热风烘干箱里"),
    ("vehicle-inspection-runner", "inspection-runner-helper", ("13900003751", "13900003752"), "我这车今年是不是免检", "先查这辆车今年要不要上线"),
    ("vehicle-inspection-runner", "inspection-runner-helper", ("13900003753", "13900003754"), "车子怕过不了", "不承诺「包过」「不上线」"),
    ("vehicle-inspection-runner", "inspection-runner-helper", ("13900003755", "13900003756"), "跑腿费怎么收", "检测费和代办费分开写"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
