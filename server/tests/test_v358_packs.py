"""SCN-208 / SCN-209 / SCN-210 / SCN-211 第二十一轮场景发掘（331 号 spec，V358）。

两个数据文件（文案代写、上门装监控）、两个新类目，外加发单拦截的两类：代写学位论文与代考（SCN-210）、
刷单刷好评与虚假评价（SCN-211）。普通文案、简历、论文润色辅导、写明是合作的探店照常发。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_copywriting_pack_refuses_thesis_ghostwriting_fake_reviews_and_absolute_claims():
    d, problems = schema.validate(_load("copywriting"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "sign"} <= set(a.human_gates)
    assert any("代写学位论文" in f for f in a.forbidden) and any("刷单" in f for f in a.forbidden)
    assert any("绝对化用语" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["文案写作"]
    assert "不代写学位论文" in d.task_templates[0].description


def test_camera_pack_only_films_your_own_home():
    d, problems = schema.validate(_load("camera-install"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("对着邻居" in f for f in a.forbidden) and any("默认密码" in f for f in a.forbidden)
    assert any("偷拍" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["监控安装"]
    t = d.task_templates[0]
    assert "改默认密码" in t.visit_checklist and "不拍邻居门窗" in t.description


@pytest.mark.parametrize("text,kind", [
    ("帮我代写毕业论文", "ghostwrite"), ("硕士论文代写包过", "ghostwrite"), ("找人替考英语四级", "ghostwrite"),
    ("代考科目一", "ghostwrite"), ("淘宝店刷单", "fake_review"), ("好评返现，写五星", "fake_review"),
    ("代写公众号文案", None),
    # 否定说法不算
    ("不代写学位论文、不写刷单好评", None), ("不是代写论文，只要润色建议", None), ("本店不刷单", None),
    ("禁止刷好评，按真实体验写", None), ("不想自己写，代写毕业论文", "ghostwrite"), ("帮我写简历", None), ("论文润色建议", None), ("帮我写一篇探店真实体验，写明是合作", None),
])
def test_what_the_new_guards_catch(text, kind):
    assert restricted_errand(text) == kind


def test_publishing_stops_ghostwriting_and_fake_reviews_but_not_ordinary_copy(client, requester):
    r = _post(client, requester, title="毕业论文", description="找人代写毕业论文，一万字", category="文案写作", is_remote=True)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "academic_ghostwriting", r.text
    assert "润色建议" in r.json()["detail"]["message"], "说清什么可以发"
    r = _post(client, requester, title="店铺好评", description="招人刷好评，每单 5 元", category="文案写作", is_remote=True)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "fake_review", r.text
    ok = _post(client, requester, title="新品详情页文案", description="三百字，写清材质", category="文案写作", is_remote=True)
    assert ok.status_code in (200, 201), ok.text
    w = make_verified(client, "13600003581")
    assert client.post(f"{API}/tasks/{ok.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201
    cam = _post(client, requester, title="门口装个摄像头", description="只拍自家门口", category="监控安装")
    assert cam.status_code in (200, 201), cam.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("copywriting", "copywriting-helper", ("13900003581", "13900003582"), "有人找我当枪手写毕设", "不接代写学位论文、代考"),
    ("copywriting", "copywriting-helper", ("13900003583", "13900003584"), "客户让我写一批水军评论", "不编好评、不刷单"),
    ("copywriting", "copywriting-helper", ("13900003585", "13900003586"), "详情页能不能写全网第一", "广告文案不用「最」「第一」「国家级」"),
    ("camera-install", "camera-helper", ("13900003587", "13900003588"), "摄像头能对着对门吗", "只拍自家：不对着邻居的门、窗、院子"),
    ("camera-install", "camera-helper", ("13900003589", "13900003590"), "怎么防止摄像头被破解", "改掉默认密码，账号在客户名下"),
    ("camera-install", "camera-helper", ("13900003591", "13900003592"), "门铃要不要开录音", "录音默认关"),
    # 人们真正会说的话：正文与标题里没有这个词，靠标签接住
    ("camera-install", "camera-helper", ("13900003593", "13900003594"), "装了会被起诉吗", "只拍自家：不对着邻居的门、窗、院子"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
