"""SCN-183 / SCN-184 第十四轮场景发掘：管道疏通、求职辅导（310 号 spec，V337）。

交付物是两个数据文件、两个新类目（都不要资质）。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.k12 import is_k12_subject_tutoring
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_drain_pack_keeps_bait_pricing_and_upselling_behind_the_line():
    d, problems = schema.validate(_load("drain-unblocking"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("翻倍" in f for f in a.forbidden) and any("疏通剂" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["管道疏通"]
    t = d.task_templates[0]
    assert "报总价" in t.description and "变更单" in t.description
    assert "先看再报价" in t.visit_checklist and "放水验收" in t.visit_checklist


def test_coaching_pack_never_promises_offers_or_fakes_a_resume():
    d, problems = schema.validate(_load("job-seeker-coaching"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "sign", "publish", "share_personal"} <= set(a.human_gates)
    for word in ("编造学历", "代考", "保 offer", "内推费"):
        assert any(word in f for f in a.forbidden), word
    assert "required_cert" not in _categories()["求职辅导"]
    t = d.task_templates[0]
    assert "不保 offer" in t.description and "交付后删除" in t.description
    assert not restricted_errand(t.description) and not is_k12_subject_tutoring(t.title + t.description)


def test_both_categories_take_applications_without_certificates(client, requester):
    w = make_verified(client, "13600003371")
    for title, cat in (("厨房下水堵了", "管道疏通"), ("改简历", "求职辅导")):
        r = _post(client, requester, title=title, description="尽快", category=cat)
        assert r.status_code in (200, 201), r.text
        t = r.json()
        assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201, cat


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("drain-unblocking", "drain-helper", ("13900003371", "13900003372"), "电话里说30元通马桶到了能加价吗", "先看后报价：看完报总价，同意了再动手"),
    ("drain-unblocking", "drain-helper", ("13900003373", "13900003374"), "通到一半要换管要砸地面怎么办", "要加长钻头、换管、砸开地面：先停下，走变更单"),
    ("job-seeker-coaching", "career-coach-helper", ("13900003375", "13900003376"), "可以承诺保offer包就业吗", "不承诺「保 offer」「包就业」"),
    ("job-seeker-coaching", "career-coach-helper", ("13900003377", "13900003378"), "简历能不能把学历经历写得好看一点编一下", "简历照真实经历写，不编学历、经历、证书"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
