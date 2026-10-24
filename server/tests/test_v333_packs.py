"""SCN-179 / SCN-180 第十三轮场景发掘：小件搬家、母婴护理（306 号 spec，V333）。

交付物是两个数据文件、两个新类目；「母婴护理」要审核通过的健康证明（一年一检）。
"""
import pytest

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_moving_pack_keeps_roadside_hikes_behind_the_line():
    d, problems = schema.validate(_load("small-moving"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("再加价" in f for f in a.forbidden) and any("扣着" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["搬家"]
    t = d.task_templates[0]
    assert "变更单" in t.description and "全包价" in t.description
    assert "搬前拍照" in t.visit_checklist and "卸完拍照" in t.visit_checklist


def test_infant_pack_and_category_need_a_health_certificate():
    d, problems = schema.validate(_load("infant-care"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("喂药" in f for f in a.forbidden) and any("不就医" in f for f in a.forbidden)
    assert any("医疗诊断" in f for f in a.forbidden)
    assert _categories()["母婴护理"].get("required_cert") == "健康证明"
    assert {t.category for t in d.task_templates} == {"母婴护理"}
    assert d.task_templates[0].visits_planned >= 4, "按周回报"


def test_only_health_certified_carers_can_take_infant_orders(client, requester):
    t = _post(client, requester, title="找月嫂 26 天", description="宝宝出生第 3 天，母乳", category="母婴护理").json()
    w = make_verified(client, "13600003331")
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"
    assert "健康证明" in r.json()["detail"]["message"]
    move = _post(client, requester, title="两居室搬家", description="三楼无电梯到五楼有电梯", category="搬家").json()
    assert client.post(f"{API}/tasks/{move['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("small-moving", "moving-helper", ("13900003331", "13900003332"), "搬到一半发现东西多了能现场加价吗", "多出来的活走变更单，不坐地起价、不扣东西"),
    ("small-moving", "moving-helper", ("13900003333", "13900003334"), "搬家怎么报价楼层电梯大件怎么算", "报全包价：楼层、距离、大件、拆装都算进去"),
    ("infant-care", "infant-care-helper", ("13900003335", "13900003336"), "宝宝发烧黄疸怎么办", "这些情况马上就医：宝宝发烧、黄疸加重、吃奶差，产妇出血多"),
    ("infant-care", "infant-care-helper", ("13900003337", "13900003338"), "上户要健康证吗", "上户前要有健康证明，一年一检"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
