"""LLM 网关抽象（04.E）。

- TemplateLLM：知识库模板 + 规则的离线实现，保证测试可跑与降级可用。
- AnthropicLLM：生产实现，接入 claude-opus-4-8 做任务分解，强制 JSON Schema
  结构化输出并做服务端校验；任何异常（无 Key / 超时 / 输出不合规）自动降级到
  TemplateLLM —— 这正是 04.E「不合规自动重试/降级为人工模板」的降级路径。

网关的选择由环境变量驱动：设置 ANTHROPIC_API_KEY 即启用 AnthropicLLM。
"""
import json
import os
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.knowledge import service as kb


class LLMGateway(Protocol):
    def decompose(self, db: Session, title: str, description: str, category: str,
                  budget_cents: int) -> list[dict]: ...


class TemplateLLM:
    """模板驱动分解：知识库模板命中 → 按预算比例拆分；未命中 → 通用三段式。"""

    GENERIC_ITEMS = [
        {"title": "方案与准备", "skills": [], "budget_ratio_bps": 2000, "depends_on": []},
        {"title": "主体执行", "skills": [], "budget_ratio_bps": 6000, "depends_on": [0]},
        {"title": "收尾与验收材料", "skills": [], "budget_ratio_bps": 2000, "depends_on": [1]},
    ]

    def decompose(self, db, title, description, category, budget_cents) -> list[dict]:
        tpl = kb.find_template(db, category, title + " " + description)
        items = tpl["items"] if tpl else self.GENERIC_ITEMS
        source = tpl["source"] if tpl else "generic"
        out = []
        allocated = 0
        for i, item in enumerate(items):
            if i == len(items) - 1:
                amount = budget_cents - allocated  # 尾差全部给最后一项，保证总额守恒
            else:
                amount = budget_cents * item.get("budget_ratio_bps", 0) // 10000
                allocated += amount
            out.append(
                {
                    "title": f"{title} - {item['title']}",
                    "description": item.get("description", item["title"]),
                    "required_skills": item.get("skills", []),
                    "budget_cents": amount,
                    "depends_on_idx": item.get("depends_on", []),
                    "source": source,
                }
            )
        return out


# 04.E 结构化输出 Schema：模型必须严格返回该形状，否则服务端校验失败并降级
DECOMPOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "subtasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "required_skills": {"type": "array", "items": {"type": "string"}},
                    "budget_ratio_bps": {"type": "integer"},
                    "depends_on_idx": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title", "description", "required_skills",
                             "budget_ratio_bps", "depends_on_idx"],
            },
        }
    },
    "required": ["subtasks"],
}

SYSTEM_PROMPT = (
    "你是任务协作平台的项目分解助手。把用户的大任务拆成 2-6 个可独立发布、"
    "可独立结算的子任务。每个子任务给出标题、简述、所需技能标签、占总预算的比例"
    "（万分比，全部子任务之和必须等于 10000）、以及依赖的前置子任务下标（从 0 开始，"
    "不能依赖自己或形成环）。只返回结构化数据。"
)


class AnthropicLLM:
    """生产实现：claude-opus-4-8 分解，JSON Schema 强约束 + 校验，失败降级模板。"""

    def __init__(self, model: str = "claude-opus-4-8"):
        self.model = model
        self._fallback = TemplateLLM()

    def _call_model(self, title: str, description: str, category: str) -> list[dict]:
        # 延迟导入，未安装 anthropic 时抛异常并触发降级
        from anthropic import Anthropic

        client = Anthropic()  # 从环境解析凭据
        prompt = (
            f"任务标题：{title}\n类目：{category}\n描述：{description or '（无）'}\n"
            "请给出子任务分解。"
        )
        # 结构化输出（04.E）：output_config.format 约束为上面的 JSON Schema
        message = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": DECOMPOSE_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
        return json.loads(text)["subtasks"]

    def decompose(self, db, title, description, category, budget_cents) -> list[dict]:
        try:
            raw = self._call_model(title, description, category)
            if not raw:
                raise ValueError("模型返回空分解")
            out = []
            allocated = 0
            for i, item in enumerate(raw):
                if i == len(raw) - 1:
                    amount = budget_cents - allocated  # 预算守恒兜底
                else:
                    ratio = int(item.get("budget_ratio_bps", 0))
                    amount = budget_cents * ratio // 10000
                    allocated += amount
                if amount <= 0:
                    raise ValueError("子任务预算非正，输出不合规")
                out.append(
                    {
                        "title": f"{title} - {item['title']}",
                        "description": item.get("description", item["title"]),
                        "required_skills": list(item.get("required_skills", [])),
                        "budget_cents": amount,
                        "depends_on_idx": [int(x) for x in item.get("depends_on_idx", [])],
                        "source": "anthropic:" + self.model,
                    }
                )
            return out
        except Exception:
            # 04.E 降级路径：任何失败（无 Key/超时/输出不合规）回落模板引擎
            return self._fallback.decompose(db, title, description, category, budget_cents)


def _default_gateway() -> LLMGateway:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicLLM(os.environ.get("PLATFORM_LLM_MODEL", "claude-opus-4-8"))
    return TemplateLLM()


_gateway: LLMGateway = _default_gateway()


def get_gateway() -> LLMGateway:
    return _gateway


def set_gateway(gateway: LLMGateway) -> None:
    """测试/生产替换实现。"""
    global _gateway
    _gateway = gateway
