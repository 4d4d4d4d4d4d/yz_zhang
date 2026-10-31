"""SCN-177 发单时拦下「没驾照找人陪练学车」（303 号 spec，V330）。

V329 的「陪驾」类目只管接单的人要有驾驶证（三年以上驾龄）；发单的人没有驾照、想找私人陪练学车，是无证驾驶。
和 294 号拦代开处方药同一种写法：纯文本规则，发单与发布草稿时都查，错误信息说清为什么、去哪里学。
"""
import json
from pathlib import Path

import pytest

from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_multiday_slots import _post

API = "/api/v1"
SEEDS = Path(__file__).resolve().parents[1] / "app" / "modules" / "packs" / "seeds"


@pytest.mark.parametrize("text", [
    "没驾照，想找人陪练学车", "还没考驾照，找个老司机周末教我开", "驾照还没下来，先找人陪我上路练练",
    "没有驾驶证，想私下找人练车，不去驾校", "无证学车，找人陪练，比驾校便宜", "没拿到驾照，求陪练",
])
def test_learner_driving_without_a_license_is_recognized(text):
    assert restricted_errand(text) == "learner", text


@pytest.mark.parametrize("text", [
    "刚拿驾照，实习期想找老司机陪我上高速", "已有驾照三年没开，找人陪练找回手感", "没驾照，想找人陪我去驾校报名学车",
    "没驾照，请人开车送我去机场", "陪练羽毛球，周末两小时", "驾照考试科目二在驾校练车，找人帮忙接送",
])
def test_licensed_practice_and_ordinary_tasks_are_not(text):
    assert restricted_errand(text) is None, text


def test_publishing_and_drafts_refuse_it_with_the_reason(client, requester):
    for kw in ({"publish_now": True}, {"publish_now": False}):
        r = _post(client, requester, title="找人陪练学车", description="我还没考驾照，想周末练车", category="陪驾", **kw)
        assert r.status_code == 400, r.text
        d = r.json()["detail"]
        assert d["code"] == "unlicensed_driving_practice", kw
        assert "无证驾驶" in d["message"] and "驾校" in d["message"] and "教练随车指导" in d["message"] and "照常发「陪驾」单" in d["message"]
    ok = _post(client, requester, title="实习期上高速找人陪驾", description="刚拿驾照，想找三年以上驾龄的老司机陪同",
               category="陪驾")
    assert ok.status_code in (200, 201), ok.text


def test_a_draft_edited_into_learner_driving_cannot_be_published(client, requester):
    t = _post(client, requester, title="陪驾", description="找人陪着练胆", category="陪驾", publish_now=False).json()
    from app.core.db import SessionLocal
    from app.modules.task.models import Task

    with SessionLocal() as db:
        db.get(Task, t["id"]).description = "其实还没驾照，想找人陪练学车"
        db.commit()
    r = client.post(f"{API}/tasks/{t['id']}/publish", headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unlicensed_driving_practice"


def test_no_seed_task_template_trips_the_guard():
    """仓库里的模板一发出去就被拦，等于没写。"""
    for f in sorted(SEEDS.glob("*.json")):
        for t in json.loads(f.read_text(encoding="utf-8")).get("task_templates", []):
            assert restricted_errand(f"{t.get('title', '')} {t.get('description', '')}") is None, (f.name, t.get("key"))


def test_clients_have_the_words_for_the_code():
    i18n = (Path(__file__).resolve().parents[2] / "packages" / "core" / "src" / "i18n.ts").read_text(encoding="utf-8")
    assert "unlicensed_driving_practice:" in i18n
