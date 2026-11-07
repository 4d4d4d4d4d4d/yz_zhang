"""SCN-100~110 场景发掘的第二轮（137 号 spec）：自由创作者、小店临时帮手。

用户原话（VISION 1.8）：「场景千变万化，可以提炼一些方法……快速发掘并部署方法到这个平台上。」
skill `scenario-discovery` 说新场景的交付物优先是**一个文件**；这一轮多了一个只读工具（需求单体检），
其余都是数据。
"""
import copy
import json

import pytest

from app.modules.packs import schema
from app.modules.packs import service as psvc
from app.modules.packs.creator import ITEMS, brief_check
from tests.conftest import auth, make_admin

CREATOR = json.loads((psvc.SEEDS / "creator-freelance.json").read_text(encoding="utf-8"))
SHOP = json.loads((psvc.SEEDS / "shop-temp-help.json").read_text(encoding="utf-8"))
API = "/api/v1"


def _publish(client, definition, phones=("13900000501", "13900000502")):
    a, b = make_admin(client, phones[0], "运营甲"), make_admin(client, phones[1], "运营乙")
    pid = client.post(f"{API}/admin/packs", json={"definition": definition}, headers=auth(a)).json()["id"]
    client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    r = client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b))
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ SCN-101 需求单体检
def test_brief_check_lists_what_the_client_did_not_say():
    r = brief_check("甲方要一套门店海报，3 张，竖版 60x90cm，下周五之前交，预算 1500 元，要源文件")
    assert r["present"] == ["用途", "数量", "尺寸规格", "文件格式", "交期", "预算"]
    assert r["missing"] == ["改稿次数", "版权授权", "参考"]
    assert r["questions"][0].startswith("包含几次修改") and len(r["questions"]) == 3
    assert r["score"] == round(6 / len(ITEMS), 2)


def test_brief_check_on_a_one_liner_asks_everything_in_order():
    r = brief_check("帮我做个 logo")
    assert r["present"] == [] and len(r["missing"]) == len(ITEMS) == 9
    assert r["missing"][:2] == ["用途", "数量"], "先问做什么，再问怎么交、怎么算钱"


def test_brief_check_full_brief_has_nothing_missing():
    r = brief_check("用于公众号头图，2 张，900x383 像素，PNG 和 PSD 源文件，10 月 20 日交稿，"
                    "含 2 次修改，版权买断，参考附件里的风格，预算 800 元")
    assert r["missing"] == [] and r["score"] == 1.0


def test_creator_assistant_runs_the_brief_check_only_on_a_pasted_brief(client, requester):
    _publish(client, CREATOR)
    ask = f"{API}/packs/creator-freelance/assistants/brief-coach/ask"
    h = auth(requester)
    r = client.post(ask, json={"q": "甲方的需求是：做一套奶茶店开业海报，3 张，下周五前要，帮我看看缺什么"}, headers=h).json()
    tool = next(c for c in r["citations"] if c["kind"] == "tool")
    assert tool["title"] == "需求单体检（写到 3/9 项）"
    assert "没写：" in tool["snippet"] and "版权授权" in tool["snippet"] and "先问甲方：" in tool["snippet"]
    short = client.post(ask, json={"q": "甲方需求怎么问"}, headers=h).json()
    assert not any(c["kind"] == "tool" for c in short["citations"]), "太短的不是需求单，不该硬算"


def test_brief_tool_is_whitelisted_and_needs_declaring():
    assert "creator.brief" in schema.TOOLS
    d = copy.deepcopy(SHOP)
    d["assistants"][0]["tools"].append("creator.brief")
    assert schema.validate(d)[1] == []
    d["assistants"][0]["tools"].append("creator.payout")
    assert any("白名单外的工具" in p for p in schema.validate(d)[1])


# ------------------------------------------------------------------ SCN-103 按人群的关口
@pytest.mark.parametrize("seed,gate", [(SHOP, "publish"), (SHOP, "money"), (CREATOR, "sign"), (CREATOR, "money")])
def test_segment_gates_cannot_be_dropped(seed, gate):
    d = copy.deepcopy(seed)
    d["assistants"][0]["human_gates"].remove(gate)
    problems = schema.validate(d)[1]
    assert any("缺人工关口" in p and gate in p for p in problems), problems


def test_both_seeds_are_valid_and_cite_sources():
    for seed in (CREATOR, SHOP):
        d, problems = schema.validate(seed)
        assert d is not None and problems == [], problems
        assert d.evidence and all(k.source for k in d.knowledge)
        assert d.assistants[0].fallback_category == "法律咨询"
    assert schema.validate(CREATOR)[0].score.total() == 76.8
    assert schema.validate(SHOP)[0].score.total() == 72.0


# ------------------------------------------------------------------ SCN-104 小店：长期用工不拿临时单凑合
def test_shop_pack_says_temp_jobs_do_not_replace_employment(client, requester):
    _publish(client, SHOP, phones=("13900000503", "13900000504"))
    h = auth(requester)
    for q in ("长期固定上班能用临时单吗", "雇人", "长期要人怎么办"):
        r = client.post(f"{API}/packs/shop-temp-help/assistants/shop-helper/ask", json={"q": q}, headers=h).json()
        assert any(c["title"] == "平台上的临时单不能替代用工合同" for c in r["citations"]), (q, r)
    templates = {t["key"]: t for t in SHOP["task_templates"]}
    assert all(t["acceptance"] for t in templates.values())
    assert "不需要接触收银与顾客信息" in templates["opening-helper"]["description"]


def test_import_seeds_picks_up_the_new_packs_as_drafts(client):
    a = make_admin(client, "13900000505", "运营甲")
    out = client.post(f"{API}/admin/packs/import-seeds", headers=auth(a)).json()
    assert {"creator-freelance", "shop-temp-help"} <= set(out["created"]) and out["invalid"] == []
