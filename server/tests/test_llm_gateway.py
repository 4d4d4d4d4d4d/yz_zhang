"""04.E 真实 LLM 网关：AnthropicLLM 结构化输出解析 + 失败降级 / KB-024 供需看板"""
import json
from unittest.mock import MagicMock, patch

from app.core.db import SessionLocal
from app.modules.decompose.llm import AnthropicLLM, TemplateLLM

from .conftest import auth, topup
from .test_task_flow import match_and_fund, publish_task


def _fake_message(subtasks):
    """构造一个模拟的 anthropic messages.create 返回值。"""
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps({"subtasks": subtasks})
    msg = MagicMock()
    msg.content = [block]
    return msg


def test_anthropic_llm_parses_structured_output(client):
    llm = AnthropicLLM(model="claude-opus-4-8")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_message([
        {"title": "设计", "description": "出稿", "required_skills": ["设计"],
         "budget_ratio_bps": 3000, "depends_on_idx": []},
        {"title": "开发", "description": "实现", "required_skills": ["开发"],
         "budget_ratio_bps": 7000, "depends_on_idx": [0]},
    ])
    with patch("anthropic.Anthropic", return_value=fake_client):
        with SessionLocal() as db:
            items = llm.decompose(db, "官网", "响应式官网", "软件开发", 100000)
    # 预算守恒 + 依赖保留 + 来源标记
    assert sum(i["budget_cents"] for i in items) == 100000
    assert items[0]["budget_cents"] == 30000 and items[1]["budget_cents"] == 70000
    assert items[1]["depends_on_idx"] == [0]
    assert all(i["source"].startswith("anthropic:") for i in items)
    # 调用参数符合 04.E：adaptive thinking + json_schema 结构化输出
    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["model"] == "claude-opus-4-8"


def test_anthropic_llm_falls_back_on_error(client):
    """模型调用抛异常 → 自动降级模板引擎（04.E 降级路径）。"""
    llm = AnthropicLLM()
    with patch("anthropic.Anthropic", side_effect=RuntimeError("no api key")):
        with SessionLocal() as db:
            items = llm.decompose(db, "官网建设", "含后台", "软件开发", 100000)
    # 降级后仍产出合法分解（模板来源），预算守恒
    assert len(items) >= 2 and sum(i["budget_cents"] for i in items) == 100000
    assert all(not i["source"].startswith("anthropic:") for i in items)


def test_anthropic_llm_rejects_non_conforming_output(client):
    """模型返回非正预算 → 判定不合规并降级。"""
    llm = AnthropicLLM()
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_message([
        {"title": "首项超配", "description": "x", "required_skills": [],
         "budget_ratio_bps": 20000, "depends_on_idx": []},  # 首项 200% 预算
        {"title": "尾项", "description": "y", "required_skills": [],
         "budget_ratio_bps": 0, "depends_on_idx": [0]},  # → 尾项 = 100000-200000 < 0
    ])
    with patch("anthropic.Anthropic", return_value=fake_client):
        with SessionLocal() as db:
            items = llm.decompose(db, "任务", "描述", "软件开发", 100000)
    assert all(i["source"] != "anthropic:claude-opus-4-8" for i in items)  # 已降级
    assert sum(i["budget_cents"] for i in items) == 100000


def test_template_llm_still_default_offline(client):
    from app.modules.decompose.llm import get_gateway

    # 测试环境无 ANTHROPIC_API_KEY → 默认仍是模板引擎，端到端分解可跑
    assert isinstance(get_gateway(), TemplateLLM)


def test_kb024_category_demand_dashboard(client, requester, worker):
    # 制造一条保洁需求（招募中）+ 一条闭环
    topup(client, requester, 60000)
    publish_task(client, requester, title="招募中的保洁", category="保洁")
    task = publish_task(client, requester, title="已完成保洁", category="保洁", budget_cents=20000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    # 执行者具备保洁技能 → 供给 +1
    client.patch("/api/v1/users/me", json={"skills": ["保洁"]}, headers=auth(worker))

    board = client.get("/api/v1/knowledge/category-demand").json()
    cleaning = [r for r in board if r["category"] == "保洁"][0]
    assert cleaning["open_demand"] == 1  # 招募中的保洁（已完成的不算）
    assert cleaning["completed"] == 1 and cleaning["gmv_cents"] == 20000
    assert cleaning["supply"] == 1 and cleaning["demand_supply_ratio"] == 1.0
