"""LLM 网关抽象（04.E）。

- TemplateLLM：知识库模板 + 规则的离线实现，保证测试可跑与降级可用。
- AnthropicLLM：生产实现，接入 claude-opus-4-8 做任务分解，强制 JSON Schema
  结构化输出并做服务端校验；任何异常（无 Key / 超时 / 输出不合规）自动降级到
  TemplateLLM —— 这正是 04.E「不合规自动重试/降级为人工模板」的降级路径。

网关的选择由环境变量驱动：设置 ANTHROPIC_API_KEY 即启用 AnthropicLLM。
"""
import json
import logging
import os
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.knowledge import service as kb

logger = logging.getLogger(__name__)

# AGT-054 降级计数：按异常类型分桶，暴露到 /metrics。
# 「降级了多少次、因为什么」必须看得见——否则一个过期的型号字面量
# 可以在生产里静默生效好几个月。
_fallbacks: dict[str, int] = {}


def record_fallback(kind: str) -> None:
    _fallbacks[kind] = _fallbacks.get(kind, 0) + 1


def fallback_counts() -> dict[str, int]:
    return dict(_fallbacks)


def reset_fallbacks() -> None:
    _fallbacks.clear()


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


# AGT-054 默认模型。**这个字面量过期过一次**：写下的是 `claude-opus-4-8`，
# 而那个型号早已不在售。配上 Key 之后，每一次分解都会 404，
# 然后被下面那个 `except Exception` 静默吞掉、回落模板——
# 平台看起来一切正常，`真实 LLM 分解已接入` 这句话却从来没有成立过。
#
# 所以这里同时留一张**在售型号表**，由测试钉住（见 test_llm_model_id.py）：
# 型号会换，而一个过期的字面量不该靠人偶然发现。
DEFAULT_MODEL = "claude-opus-5"

# 当前 Claude 5 家族 + 仍在售的 4.5。配置成表外的型号，生产启动自检会拒。
KNOWN_MODELS = frozenset({
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5-1",
    "claude-haiku-4-5-20251001",
})


class AnthropicLLM:
    """生产实现：JSON Schema 强约束 + 校验，失败降级模板。"""

    def __init__(self, model: str = DEFAULT_MODEL):
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
        except Exception as exc:
            # 04.E 降级路径：任何失败（无 Key/超时/输出不合规）回落模板引擎。
            #
            # **但降级不能是静默的。** 改造前这里是裸 `except Exception: return 模板`：
            # 一个过期的型号字面量让每次调用都 404，而平台看起来完全正常——
            # 「有 Key 即用」这句话不成立，却没有任何信号说出来。
            #
            # 降级本身是对的（宁可给模板结果也不要让发布卡住），
            # 要的是**它发生过这件事被记下来**。
            record_fallback(type(exc).__name__)
            logger.warning(
                "llm_decompose_fallback",
                extra={"model": self.model, "error_type": type(exc).__name__,
                       # 异常文本可能带上游返回内容，交给既有的日志脱敏
                       "error": str(exc)[:200]},
            )
            return self._fallback.decompose(db, title, description, category, budget_cents)


def _default_gateway() -> LLMGateway:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicLLM(os.environ.get("PLATFORM_LLM_MODEL", DEFAULT_MODEL))
    return TemplateLLM()


_gateway: LLMGateway = _default_gateway()


def get_gateway() -> LLMGateway:
    return _gateway


def set_gateway(gateway: LLMGateway) -> None:
    """测试/生产替换实现。"""
    global _gateway
    _gateway = gateway
