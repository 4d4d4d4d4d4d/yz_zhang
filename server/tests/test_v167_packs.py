"""SCN-108 第三轮场景发掘的三个场景包（153 号 spec）：家庭事务、社区活动组织者、学生作品接单。

交付物是三个数据文件；这里核对它们真的能上线、能答出最要紧的那几句话。
"""
import json

import pytest

from app.modules.packs import schema
from app.modules.packs import service as psvc
from tests.conftest import auth, make_admin

API = "/api/v1"
NEW = ("household-chores", "community-organizer", "student-portfolio")


def _load(key):
    return json.loads((psvc.SEEDS / f"{key}.json").read_text(encoding="utf-8"))


def _publish(client, definition, phones):
    a, b = make_admin(client, phones[0], "运营甲"), make_admin(client, phones[1], "运营乙")
    pid = client.post(f"{API}/admin/packs", json={"definition": definition}, headers=auth(a)).json()["id"]
    client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    assert client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b)).status_code == 200


@pytest.mark.parametrize("key", NEW)
def test_new_packs_pass_the_platform_red_lines(key):
    d, problems = schema.validate(_load(key))
    assert d is not None and not problems, problems
    for a in d.assistants:
        assert {"money", "publish"} <= set(a.human_gates) or {"money", "sign"} <= set(a.human_gates)
        assert a.forbidden and a.fallback_category
    assert all(k.source for k in d.knowledge) and all(t.acceptance for t in d.task_templates)
    from app.modules.task.service import ADDED_CATEGORIES, SEED_CATEGORIES

    names = {c["name"] for c in SEED_CATEGORIES + ADDED_CATEGORIES}
    assert {t.category for t in d.task_templates} <= names, "模板用了不存在的类目"


@pytest.mark.parametrize("key,assistant,questions,title", [
    ("household-chores", "home-helper", ("换燃气灶找谁", "修电路要什么资质"), "燃气和电路作业要持证"),
    ("household-chores", "home-helper", ("干活时受伤了谁负责",), "个人之间雇人干活，受伤或弄坏东西谁负责"),
    ("community-organizer", "event-organizer", ("办个市集多少人要报公安许可", "大型活动要许可吗"), "多大规模的活动要公安安全许可"),
    ("community-organizer", "event-organizer", ("志愿者要买保险吗",), "志愿者的保险"),
    ("student-portfolio", "student-gig-coach", ("对方让我借银行卡走流水", "出借手机卡有风险吗"), "出借、出售银行卡和手机卡的法律风险"),
    ("student-portfolio", "student-gig-coach", ("做完的海报能放作品集吗", "版权归谁"), "受委托创作的作品，著作权归谁"),
])
def test_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, questions, title):
    phones = {"household-chores": ("13900000601", "13900000602"), "community-organizer": ("13900000603", "13900000604"),
              "student-portfolio": ("13900000605", "13900000606")}[key]
    _publish(client, _load(key), phones)
    for q in questions:
        r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
        assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]])


def test_import_seeds_picks_up_the_three_new_packs(client):
    a = make_admin(client, "13900000607", "运营甲")
    out = client.post(f"{API}/admin/packs/import-seeds", headers=auth(a)).json()
    assert set(NEW) <= set(out["created"]) and out["invalid"] == []
