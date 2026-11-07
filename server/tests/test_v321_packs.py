"""SCN-164 / SCN-165 第十轮场景发掘：跑腿代办的规矩、活动跟拍（294 号 spec，V321）。

交付物是两个数据文件、一个新类目「活动跟拍」，外加发单时拦下两类平台不能接的跑腿活：替人代开 / 代买处方药与
精神类药品，加价倒卖号源与门票（与 213 号拦中小学学科类家教同一种写法）。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


@pytest.mark.parametrize("text,kind", [
    ("帮我去医院代开两盒安眠药", "rx"), ("代买阿普唑仑，有处方单", "rx"), ("跑腿帮忙买处方药送到家", "rx"),
    ("替我开点佐匹克隆", "rx"), ("演唱会门票加价转让，帮忙代抢", "resale"), ("代挂专家号，高价转给需要的人", "resale"),
])
def test_restricted_errands_are_recognized(text, kind):
    assert restricted_errand(text) == kind, text


@pytest.mark.parametrize("text", [
    "代买退烧药和感冒药送到家", "帮我去医院挂号排队，我本人看病", "代取快递三件", "处方药、安眠药等精神类药品不代买",
    "帮忙排队买网红面包", "演唱会当天帮忙拿行李", "取到的号只给本人用，不转给别人", "帮忙把闲置自行车转卖掉",
])
def test_ordinary_errands_are_not(text):
    assert restricted_errand(text) is None, text


def test_publishing_and_drafts_refuse_them_with_the_reason(client, requester):
    for kw in ({"publish_now": True}, {"publish_now": False}):
        r = _post(client, requester, title="帮我去医院代开安眠药", description="两盒，送到小区门口", category="跑腿", **kw)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "errand_restricted", kw
        assert "凭处方" in r.json()["detail"]["message"] and "非处方药可以照常发单" in r.json()["detail"]["message"]
    r = _post(client, requester, title="代抢演唱会门票", description="抢到后加价转让", category="跑腿")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "errand_restricted"
    assert "倒卖" in r.json()["detail"]["message"]
    ok = _post(client, requester, title="代买退烧药", description="布洛芬一盒，送到家", category="跑腿")
    assert ok.status_code in (200, 201), ok.text


def test_a_draft_edited_into_a_restricted_errand_cannot_be_published(client, requester):
    t = _post(client, requester, title="跑腿", description="帮忙买东西", category="跑腿", publish_now=False).json()
    from app.core.db import SessionLocal
    from app.modules.task.models import Task

    with SessionLocal() as db:
        db.get(Task, t["id"]).description = "其实是去医院代开安眠药"
        db.commit()
    r = client.post(f"{API}/tasks/{t['id']}/publish", headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "errand_restricted"


def test_errand_pack_keeps_drugs_resale_and_parcels_behind_the_line():
    d, problems = schema.validate(_load("errand-runner"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("处方药" in f for f in a.forbidden) and any("号源" in f for f in a.forbidden)
    assert a.fallback_category == "跑腿" and {t.category for t in d.task_templates} == {"跑腿"}
    assert all(restricted_errand(f"{t.title} {t.description}") is None for t in d.task_templates), "模板本身发得出去"


def test_photography_pack_and_category():
    d, problems = schema.validate(_load("event-photography"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("线下定金" in f for f in a.forbidden) and any("未成年人" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["活动跟拍"]
    assert {t.category for t in d.task_templates} == {"活动跟拍"} and a.fallback_category == "活动跟拍"
    assert all(t.visits_planned >= 1 and t.visit_checklist for t in d.task_templates)


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("errand-runner", "errand-helper", ("13900003211", "13900003212"), "客户让我顺路帮他开点安眠药可以吗", "处方药、安眠药不代开不代买"),
    ("errand-runner", "errand-helper", ("13900003213", "13900003214"), "代取快递能拍面单发群里吗", "代取快递：面单打码，不外传"),
    ("event-photography", "event-photo-helper", ("13900003215", "13900003216"), "拍的婚礼照片能放作品集吗", "放作品集、发网上：先问，客户在平台上授权"),
    ("event-photography", "event-photo-helper", ("13900003217", "13900003218"), "照片的版权归谁", "照片的版权归谁：单里写清"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]])
