"""LLM 网关抽象（04.E）。

生产实现接入真实模型（如 claude-sonnet-5）并强制 JSON Schema 校验输出；
默认实现 TemplateLLM 基于知识库模板 + 规则，保证离线可测与降级可用
（04.E：'不合规自动重试/降级为人工模板'的降级路径本身）。
"""
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


_gateway: LLMGateway = TemplateLLM()


def get_gateway() -> LLMGateway:
    return _gateway


def set_gateway(gateway: LLMGateway) -> None:
    """测试/生产替换实现。"""
    global _gateway
    _gateway = gateway
