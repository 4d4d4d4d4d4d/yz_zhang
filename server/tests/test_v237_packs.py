"""SCN-141 第六轮场景发掘：小店直播与短视频帮手（209 号 spec，V237）。

交付物是一个数据文件；这里核对它过得了平台红线、能答出最要紧的那几句。
"""
import json

import pytest

from app.modules.packs import schema
from app.modules.packs import service as psvc
from tests.conftest import auth, make_admin

API = "/api/v1"
KEY = "live-selling-helper"


def _load():
    return json.loads((psvc.SEEDS / f"{KEY}.json").read_text(encoding="utf-8"))


def _publish(client):
    a, b = make_admin(client, "13900002091", "运营甲"), make_admin(client, "13900002092", "运营乙")
    pid = client.post(f"{API}/admin/packs", json={"definition": _load()}, headers=auth(a)).json()["id"]
    client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    assert client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b)).status_code == 200


def test_the_pack_passes_the_platform_red_lines():
    d, problems = schema.validate(_load())
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("密码" in f for f in a.forbidden), "不索要、不保管店铺账号密码"
    assert any("断定" in f for f in a.forbidden), "不替人断定一定合规"
    assert any("开播" in f or "发布" in f for f in a.forbidden), "不替人开播、发布"
    from app.modules.task.service import ADDED_CATEGORIES, SEED_CATEGORIES

    names = {c["name"] for c in SEED_CATEGORIES + ADDED_CATEGORIES}
    assert {t.category for t in d.task_templates} <= names and a.fallback_category in names
    live = next(t for t in d.task_templates if t.key == "live-session-assistant")
    assert any("没有代收任何款项" in x for x in live.acceptance), "验收写明没碰主账号、没代收钱"
    edit = next(t for t in d.task_templates if t.key == "short-video-edit")
    assert any("授权" in x for x in edit.acceptance) and any("绝对化用语" in x for x in edit.acceptance)


@pytest.mark.parametrize("questions,title", [
    (("直播能说全网最低吗", "可以说我们是第一吗"), "广告里不能用「最高级」「最佳」这类绝对化用语"),
    (("划线价怎么写", "原价随便写可以吗"), "划线价、原价怎么标才不算价格欺诈"),
    (("要把店铺账号密码给助理吗",), "助理用子账号或协作权限，不给主账号密码"),
    (("朋友出镜要同意吗",), "店员、朋友出镜要本人同意"),
    (("能找人刷单刷点赞吗",), "直播带货要真实、准确、全面，不能编数据"),
    (("剪辑用的音乐要授权吗",), "剪辑用的音乐、字体、图片要有授权"),
])
def test_the_assistant_answers_the_questions_that_matter_most(client, requester, questions, title):
    _publish(client)
    for q in questions:
        r = client.post(f"{API}/packs/{KEY}/assistants/live-shop-advisor/ask", json={"q": q}, headers=auth(requester)).json()
        assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]])
