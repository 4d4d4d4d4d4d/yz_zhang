"""SCN-131 第五轮场景发掘：异地租房代看房（191 号 spec，V219）。

交付物是一个数据文件 + 「跑腿」概念的两个别名 + 法律主题「租房买房」的三个词；这里核对它能上线、能答出最要紧的那几句。
"""
import json

import pytest

from app.modules.packs import schema
from app.modules.packs import service as psvc
from app.modules.packs.topics import LEGAL_TOPICS, topic_of
from tests.conftest import auth, make_admin

API = "/api/v1"
KEY = "rental-viewing-proxy"


def _load():
    return json.loads((psvc.SEEDS / f"{KEY}.json").read_text(encoding="utf-8"))


def _publish(client):
    a, b = make_admin(client, "13900001901", "运营甲"), make_admin(client, "13900001902", "运营乙")
    pid = client.post(f"{API}/admin/packs", json={"definition": _load()}, headers=auth(a)).json()["id"]
    client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    assert client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b)).status_code == 200


def test_the_pack_passes_the_platform_red_lines():
    d, problems = schema.validate(_load())
    assert d is not None and not problems, problems
    for a in d.assistants:
        assert {"money", "publish", "share_personal"} <= set(a.human_gates), a.key
        assert any("费" in f or "钱" in f for f in a.forbidden), "代交任何费用要写进禁止动作"
        assert any("签" in f for f in a.forbidden), "代签要写进禁止动作"
    advisor = next(a for a in d.assistants if a.key == "renter-advisor")
    assert any("断定" in f for f in advisor.forbidden), "不替人断定房源真假，只给核对办法"
    from app.modules.task.service import ADDED_CATEGORIES, SEED_CATEGORIES

    names = {c["name"] for c in SEED_CATEGORIES + ADDED_CATEGORIES}
    assert {t.category for t in d.task_templates} <= names and {a.fallback_category for a in d.assistants} <= names
    tpl = d.task_templates[0]
    assert any("没有代交任何费用" in x for x in tpl.acceptance), "验收标准里写明没代交钱、没代签"
    assert "门牌接单后给" in tpl.description, "具体门牌接单后才给"


@pytest.mark.parametrize("assistant,questions,title", [
    ("renter-advisor", ("看房前要先交看房费吗", "对方让我先交定金"), "看房前不交钱：看房费、定金先别付"),
    ("renter-advisor", ("二房东能转租给我吗",), "二房东转租，要有房东同意"),
    ("renter-advisor", ("租一年要签合同吗",), "租期六个月以上要签书面合同"),
    ("viewing-proxy-coach", ("阳台隔出来的房间能租吗",), "厨房、卫生间、阳台不能单独出租住人"),
    ("viewing-proxy-coach", ("怎么核对房东是不是真的",), "怎么核对出租人有没有权出租"),
])
def test_assistants_answer_the_questions_that_matter_most(client, requester, assistant, questions, title):
    _publish(client)
    for q in questions:
        r = client.post(f"{API}/packs/{KEY}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
        assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]])


def test_import_seeds_picks_up_the_new_pack(client):
    a = make_admin(client, "13900001903", "运营甲")
    out = client.post(f"{API}/admin/packs/import-seeds", headers=auth(a)).json()
    assert KEY in out["created"] and out["invalid"] == []


def test_questions_about_sublets_land_in_the_rental_legal_topic():
    assert topic_of("二房东跑路了怎么办", LEGAL_TOPICS) == "租房买房"
    assert topic_of("转租合同有效吗", LEGAL_TOPICS) == "租房买房"


def test_proxy_viewing_is_understood_as_an_errand_skill():
    from app.modules.skills.service import canonical, index

    idx = index()
    assert canonical("代看房", idx) == canonical("帮看房", idx) == "跑腿"
