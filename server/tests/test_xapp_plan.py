"""XAPP-015 跨 App 助手：一句目标出计划草稿（161 号 spec，V191）。

计划只是草稿：本人看过再发起。规则计划与本机（隐私沙箱）计划同一个算法——两边读同一份例子文件；
配了模型就由模型出，但模型不能越过授权：不在授权里的 App 丢掉、红线由服务端判。
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.db import SessionLocal
from app.modules.decompose import llm as llm_mod
from app.modules.decompose.llm import AnthropicLLM
from app.modules.xapp import planner
from tests.conftest import auth

API = "/api/v1/xapp"
MAP, CHAT, PAY = "com.autonavi.minimap", "com.tencent.mm", "com.eg.android.AlipayGphone"
CASES = Path(__file__).resolve().parents[2] / "packages/core/src/xapp-plan-cases.json"


def _grant(client, u, apps=(MAP, CHAT), actions=("open", "fill", "read")):
    r = client.post(f"{API}/grants", json={"apps": list(apps), "actions": list(actions), "days": 7}, headers=auth(u))
    assert r.status_code == 201, r.text
    return r.json()


def _plan(client, u, gid, goal):
    return client.post(f"{API}/plan", json={"grant_id": gid, "goal": goal}, headers=auth(u))


def test_shared_cases_match_the_server_rules_both_ways():
    data = json.loads(CASES.read_text(encoding="utf-8"))
    assert data["rules"] == planner.rules(), "例子文件里的规则表过期了：按 161 号 spec 第 6 节重新生成，两端一起过"
    assert len(data["cases"]) >= 8
    for c in data["cases"]:
        got = [{k: s[k] for k in ("app", "action", "channel", "red_line")} for s in planner.plan_by_rules(c["goal"], c["apps"])]
        assert got == c["expect"], c["goal"]


def test_rules_plan_follows_channel_order_and_marks_red_line(client, requester):
    g = _grant(client, requester)
    r = _plan(client, requester, g["id"], "用高德查一下去客户公司要多久，然后在微信里告诉客户预计到达时间")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["source"] == "rules" and p["grant_id"] == g["id"]
    assert [(s["app"], s["action"], s["channel"]) for s in p["steps"]] == [
        (MAP, "open", "deeplink"), (MAP, "fill", "a11y"), (MAP, "read", "a11y"), (CHAT, "open", "a11y"), (CHAT, "send_message", "a11y")]
    assert [s["red_line"] for s in p["steps"]] == [False, False, False, False, True]
    assert p["steps"][-1]["action_label"] == "对外发消息"
    assert p["ready"] is True and p["missing_actions"] == []
    assert any("亲手完成" in n for n in p["notes"])
    # 草稿能原样拿去发起（形状与发起接口认的一致），发起后红线步要本人确认
    steps = [{k: s[k] for k in ("app", "action", "intent", "channel", "vision_where")} for s in p["steps"]]
    run = client.post(f"{API}/runs", json={"grant_id": g["id"], "goal": p["goal"], "executor": "mock", "confirm_mode": "red_only",
                                           "steps": steps}, headers=auth(requester))
    assert run.status_code == 201, run.text
    assert [s["needs_confirm"] for s in run.json()["steps"]] == [False, False, False, False, True]


def test_app_name_is_not_an_action_and_missing_actions_are_listed(client, requester):
    g = _grant(client, requester, apps=(PAY, MAP), actions=("open",))
    p = _plan(client, requester, g["id"], "在支付宝给房东转账两千块").json()
    assert [s["action"] for s in p["steps"]] == ["open", "transfer"], "「支付宝」里的「支付」被当成了付款"
    q = _plan(client, requester, g["id"], "到公司要多久").json()
    assert q["missing_actions"] == ["read"] and q["ready"] is False
    assert any("读取页面" in n for n in q["notes"])


def test_plan_needs_an_active_grant_of_my_own(client, requester, worker):
    g = _grant(client, requester)
    other = _plan(client, worker, g["id"], "打开微信")
    assert other.status_code == 404, "别人的授权一律 404"
    client.delete(f"{API}/grants/{g['id']}", headers=auth(requester))
    gone = _plan(client, requester, g["id"], "打开微信")
    assert gone.status_code == 409 and gone.json()["detail"]["code"] == "xapp_grant_inactive"


def test_sandbox_blocks_the_plan_endpoint_and_the_catalog_carries_the_rules(client, requester):
    g = _grant(client, requester)
    cat = client.get(f"{API}/catalog", headers=auth(requester)).json()
    assert cat["plan_rules"] == planner.rules()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(cat, "XappCatalog")
    assert client.put("/api/v1/users/me/sandbox", json={"enabled": True}, headers=auth(requester)).status_code == 200
    r = _plan(client, requester, g["id"], "打开微信")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sandbox_cloud_ai_blocked", "沙箱里目标原文不该发到服务端"


class _FakeModel:
    """模型网关替身：故意越权（不在授权里的 App）、故意把红线动作当普通动作、乱写通道。"""

    def __init__(self, steps=None, boom=False):
        self.steps, self.boom = steps or [], boom

    def plan_xapp(self, db, goal, apps):
        if self.boom:
            raise TimeoutError("模型超时")
        return self.steps


def test_model_plan_cannot_widen_the_grant(client, requester, monkeypatch):
    g = _grant(client, requester)
    monkeypatch.setattr(llm_mod, "_gateway", _FakeModel([
        {"app": MAP, "action": "open", "intent": "打开地图", "channel": "deeplink", "why": "先打开"},
        {"app": "com.bank.app", "action": "open", "intent": "打开银行", "channel": "a11y", "why": "顺便"},
        {"app": CHAT, "action": "send_message", "intent": "发消息", "channel": "teleport", "why": "告诉客户"},
        {"app": CHAT, "action": "hack", "intent": "?", "channel": "a11y", "why": ""},
    ]))
    p = _plan(client, requester, g["id"], "查路线并告诉客户").json()
    assert p["source"] == "model"
    assert [s["app"] for s in p["steps"]] == [MAP, CHAT], "不在授权里的 App 必须丢掉"
    assert p["steps"][1]["red_line"] is True, "红线由服务端判，模型说了不算"
    assert p["steps"][1]["channel"] == "a11y", "不认识的通道按规则挑"
    assert any("com.bank.app" in n for n in p["notes"]) and any("hack" in n for n in p["notes"])
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(p, "XappPlan")


def test_model_failure_falls_back_to_rules_visibly(client, requester, monkeypatch):
    g = _grant(client, requester)
    monkeypatch.setattr(llm_mod, "_gateway", _FakeModel(boom=True))
    p = _plan(client, requester, g["id"], "打开微信").json()
    assert p["source"] == "rules" and [s["action"] for s in p["steps"]] == ["open"]
    assert any("按规则出的" in n for n in p["notes"])
    monkeypatch.setattr(llm_mod, "_gateway", _FakeModel([{"app": "x.y", "action": "open", "intent": "", "channel": "a11y", "why": ""}]))
    q = _plan(client, requester, g["id"], "打开微信").json()
    assert q["source"] == "rules" and any("都不能用" in n for n in q["notes"])


def test_anthropic_plan_uses_structured_output_and_releases_the_connection():
    block = MagicMock()
    block.type, block.text = "text", json.dumps({"steps": [{"app": MAP, "action": "open", "intent": "打开", "channel": "deeplink", "why": ""}]})
    fake = MagicMock()
    fake.messages.create.return_value = MagicMock(content=[block])
    with patch("anthropic.Anthropic", return_value=fake), SessionLocal() as db:
        steps = AnthropicLLM(model="claude-opus-4-8").plan_xapp(db, "打开地图", [MAP])
    assert steps[0]["app"] == MAP
    _, kw = fake.messages.create.call_args
    assert kw["output_config"]["format"]["schema"] == planner.XAPP_PLAN_SCHEMA
    assert "亲手完成" in kw["system"]
