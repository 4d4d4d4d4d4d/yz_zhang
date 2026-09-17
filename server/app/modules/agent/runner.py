"""AGT agent 的执行后端（平台买的那个 API）。

与 `app/vendors/` 的抽象同一套路数：Protocol + 本地实现 + 生产实现，
生产启动自检拒绝非生产实现（见 AGT 在 `vendors/registry.py` 的登记）。

**关键差别在降级方向**：`decompose/llm.py` 失败时降级到模板引擎，那是对的——
模板分解仍然有用，而且发布方会自己看一眼再确认。这里**不降级**：
交付物降级成模板，就是拿废品换钱。所以拿不到模型就抛 `AgentUnavailable`，
让 run 落 `failed`。
"""
import json
import os
from dataclasses import dataclass
from typing import Protocol

# 默认模型。此前 `decompose/llm.py` 里写死的 `claude-opus-4-8` 已过时（AGT-054）。
DEFAULT_MODEL = os.environ.get("PLATFORM_AGENT_MODEL", "claude-opus-5")


class AgentUnavailable(RuntimeError):
    """执行后端不可用：无 Key / 超时 / 输出不合规。**不降级，直接失败。**"""


@dataclass
class RunResult:
    output: str
    confidence_bps: int
    cost_cents: int


class AgentRunner(Protocol):
    def run(self, *, model: str, system_prompt: str, title: str,
            description: str, category: str) -> RunResult: ...


class LocalRunner:
    """本地实现：**不接任何模型**，用于测试与未配置生产密钥时。

    它产出一段明确标注「本地实现」的文本，并且**置信度恒为 0**——
    于是它必然低于任何阈值、必然被 AGT-013 拦成 `escalated`。
    这是有意的：本地实现不能看起来像能干活的样子。
    """

    name = "local"
    production_ready = False

    def run(self, *, model, system_prompt, title, description, category) -> RunResult:
        body = (
            f"【本地实现产出 · 非模型输出】\n"
            f"任务：{title}\n类目：{category}\n"
            f"说明：当前未配置 AI 执行后端，本条内容不可用于交付。"
        )
        return RunResult(output=body, confidence_bps=0, cost_cents=0)


class AnthropicRunner:
    """生产实现：平台买的 API。"""

    name = "anthropic"
    production_ready = True

    def __init__(self, default_model: str = DEFAULT_MODEL):
        self.default_model = default_model

    def run(self, *, model, system_prompt, title, description, category) -> RunResult:
        try:
            from anthropic import Anthropic
        except Exception as exc:  # 未安装 SDK
            raise AgentUnavailable(f"AI 执行后端不可用：{exc}") from exc
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise AgentUnavailable("AI 执行后端未配置密钥")
        schema = {
            "type": "object",
            "properties": {
                "output": {"type": "string"},
                # 让模型自报置信度。**这是自报的**，所以 AGT-030 的客观判据
                # 必须压在它上面——否则等于让执行者给自己判卷。
                "confidence_bps": {"type": "integer", "minimum": 0, "maximum": 10000},
            },
            "required": ["output", "confidence_bps"],
            "additionalProperties": False,
        }
        try:
            client = Anthropic()
            message = client.messages.create(
                model=model or self.default_model,
                max_tokens=8192,
                system=system_prompt or "你是任务执行助理，按要求完成交付物。",
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{
                    "role": "user",
                    "content": f"任务标题：{title}\n类目：{category}\n"
                               f"描述：{description or '（无）'}\n请完成并给出交付内容。",
                }],
            )
            text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
            data = json.loads(text)
            output = str(data["output"])
            if not output.strip():
                raise ValueError("模型返回空交付")
            usage = getattr(message, "usage", None)
            cost = _estimate_cost_cents(usage)
            return RunResult(output=output,
                             confidence_bps=int(data.get("confidence_bps", 0)),
                             cost_cents=cost)
        except AgentUnavailable:
            raise
        except Exception as exc:
            raise AgentUnavailable(f"AI 执行失败：{type(exc).__name__}") from exc


def _estimate_cost_cents(usage) -> int:
    """AGT-052 按配置单价估算，不是 provider 返回的真实计费。

    真实计费要等接到具体 API 的账单口径；在那之前这个数字是**估算**，
    毛利报表上必须这么说，不能把估算当成实账。
    """
    if not usage:
        return 0
    in_per_m = int(os.environ.get("PLATFORM_AGENT_COST_IN_PER_MTOK_CENTS", "0"))
    out_per_m = int(os.environ.get("PLATFORM_AGENT_COST_OUT_PER_MTOK_CENTS", "0"))
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    return (tin * in_per_m + tout * out_per_m) // 1_000_000


_runner: AgentRunner | None = None


def get_runner() -> AgentRunner:
    global _runner
    if _runner is None:
        _runner = (
            AnthropicRunner() if os.environ.get("PLATFORM_AGENT_RUNNER", "") == "anthropic"
            else LocalRunner()
        )
    return _runner


def set_runner(runner: AgentRunner | None) -> None:
    """测试用注入点。"""
    global _runner
    _runner = runner
