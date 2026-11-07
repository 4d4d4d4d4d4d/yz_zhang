"""SCN-170 / SCN-171 第十一轮场景发掘：情绪陪伴（线上倾听）、上门私教（298 号 spec，V325）。

交付物是两个数据文件、两个新类目，外加一条全平台的安全规则：问题里有想伤害自己的说法时，场景包助手与法律问答都先给
12356 心理援助热线（以前只说「请拨 110」）。
"""
import pytest

from app.core.crisis import CRISIS_ANSWER, is_self_harm
from app.modules.packs import schema
from tests.conftest import auth
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


@pytest.mark.parametrize("q", ["我不想活了", "活不下去了怎么办", "有点想死", "朋友说想自杀", "忍不住想伤害自己"])
def test_self_harm_phrases_are_recognized(q):
    assert is_self_harm(q), q


@pytest.mark.parametrize("q", ["对方想约我线下见面", "工作压力好大", "累死了今天", "老人有高血压能练吗"])
def test_ordinary_questions_are_not(q):
    assert not is_self_harm(q), q


def test_any_pack_assistant_and_legal_ask_lead_with_the_hotline(client, requester):
    _publish(client, "home-fitness-coach", ("13900003251", "13900003252"))
    r = client.post(f"{API}/packs/home-fitness-coach/assistants/fitness-coach-helper/ask",
                    json={"q": "练不动了，我不想活了"}, headers=auth(requester)).json()
    assert r["crisis"] is True and r["refused"] is True and r["answer"] == CRISIS_ANSWER and "12356" in r["answer"]
    assert r["citations"] == [] and r["remedy"] is None
    ok = client.post(f"{API}/packs/home-fitness-coach/assistants/fitness-coach-helper/ask",
                     json={"q": "老人有高血压能练吗"}, headers=auth(requester)).json()
    assert "crisis" not in ok, "普通问题响应与以前一样"
    legal = client.post(f"{API}/legal/ask", json={"question": "被欠薪了，活不下去了"}, headers=auth(requester)).json()
    assert legal["refused"] is True and legal["refused_reason"] == "high_risk" and "12356" in legal["answer"]
    other = client.post(f"{API}/legal/ask", json={"question": "有人威胁我人身安全怎么办"}, headers=auth(requester)).json()
    assert "110" in other["answer"] and "12356" not in other["answer"], "别的人身安全问题照旧"


def test_listening_pack_keeps_therapy_meetups_and_upsell_behind_the_line():
    d, problems = schema.validate(_load("emotional-listening"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("诊断" in f for f in a.forbidden) and any("线下见面" in f for f in a.forbidden)
    assert any("推销" in f for f in a.forbidden)
    assert "12356" in {k.key: k for k in d.knowledge}["crisis-referral"].body
    assert "情绪陪伴" in _categories() and {t.category for t in d.task_templates} == {"情绪陪伴"}


def test_fitness_pack_and_category():
    d, problems = schema.validate(_load("home-fitness-coach"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("康复" in f for f in a.forbidden) and any("课包" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["上门私教"]
    assert all(t.visits_planned >= 1 and t.visit_checklist for t in d.task_templates)


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("emotional-listening", "listener-helper", ("13900003253", "13900003254"), "对方问我他是不是抑郁症要不要吃药", "倾听不是心理咨询，不诊断、不谈用药"),
    ("emotional-listening", "listener-helper", ("13900003255", "13900003256"), "对方想约我线下见面", "只在线上：不见面、不加私人联系方式、不借钱"),
    ("home-fitness-coach", "fitness-coach-helper", ("13900003257", "13900003258"), "老人有高血压能练吗", "首课前问病史、体检、用药"),
    ("home-fitness-coach", "fitness-coach-helper", ("13900003259", "13900003260"), "练的时候对方说胸闷头晕怎么办", "胸痛、头晕、气短异常：立即停"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
