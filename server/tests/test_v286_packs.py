"""SCN-150 / SCN-151 第七轮场景发掘：孩子的兴趣陪练、自由译者（259 号 spec，V286）。

交付物是两个数据文件；这里核对它们过得了平台红线、和已有的关口（212~216 号）对得上、能答出最要紧的那几句。
"""
import json

import pytest

from app.modules.packs import schema
from app.modules.packs import service as psvc
from tests.conftest import auth, make_admin

API = "/api/v1"


def _load(key):
    return json.loads((psvc.SEEDS / f"{key}.json").read_text(encoding="utf-8"))


def _publish(client, key, phones):
    a, b = make_admin(client, phones[0], "运营甲"), make_admin(client, phones[1], "运营乙")
    pid = client.post(f"{API}/admin/packs", json={"definition": _load(key)}, headers=auth(a)).json()["id"]
    client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    assert client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b)).status_code == 200


def _categories():
    from app.modules.task.service import ADDED_CATEGORIES, SEED_CATEGORIES

    return {c["name"]: c for c in SEED_CATEGORIES + ADDED_CATEGORIES}


def test_hobby_pack_lines_up_with_the_minor_gates():
    d, problems = schema.validate(_load("kids-hobby-practice"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("学科" in f for f in a.forbidden), "不帮人把学科辅导改写成别的说法"
    assert any("单独相处" in f for f in a.forbidden)
    cats = _categories()
    assert {t.category for t in d.task_templates} == {"陪练看护"} and cats["陪练看护"].get("required_cert"), "走要无犯罪记录证明的类目"
    assert all(t.visits_planned > 0 and t.visit_checklist for t in d.task_templates), "按次回报（216 号）"


def test_hobby_templates_are_not_blocked_as_k12_tutoring():
    """模板文字本身不能踩 213 号的学科类家教拦截（否则家长照着模板发都发不出去）。"""
    from app.modules.task.k12 import is_k12_subject_tutoring

    for t in schema.validate(_load("kids-hobby-practice"))[0].task_templates:
        assert not is_k12_subject_tutoring(t.title + "\n" + t.description), t.key


def test_translation_pack_has_its_category_and_gates():
    d, problems = schema.validate(_load("translation-freelance"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "sign"} <= set(a.human_gates) and "creator.brief" in a.tools
    assert any("盖章" in f for f in a.forbidden), "不冒充翻译机构盖章"
    assert "翻译" in _categories() and a.fallback_category == "翻译"
    assert {t.category for t in d.task_templates} == {"翻译"}


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("kids-hobby-practice", "hobby-coach-helper", ("13900002861", "13900002862"), "能找人给孩子补数学吗", "中小学学科类有偿家教平台不接"),
    ("kids-hobby-practice", "hobby-coach-helper", ("13900002863", "13900002864"), "陪练要有无犯罪记录吗", "接这类单的人要有无犯罪记录证明"),
    ("translation-freelance", "translator-helper", ("13900002865", "13900002866"), "证件翻译要盖章吗", "证件、公证用的翻译：先问使用单位的要求"),
    ("translation-freelance", "translator-helper", ("13900002867", "13900002868"), "客户的合同资料能传到在线翻译工具吗", "客户资料里的个人信息"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]])
