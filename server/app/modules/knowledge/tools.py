"""AGT-080~083 平台内置的经验工具（109 号 spec）。

**这个文件里的东西只产出草稿**：不写资金、不签约、不转移权益、不对外发消息
（AGT-081，由 `test_experience_units` 的 AST 闸门扫描，不靠人自觉）。
产出一律标「由经验单元 X 生成，未经人工确认」，并且可以一键丢弃（AGT-083）。

为什么草稿是硬要求：经验来自历史闭环，而历史闭环里有纠纷与返工。一个把历史做法
直接当成当前动作的工具，会把上一次的错误复制到下一次——而且因为它「有经验撑着」，
看起来比随便猜更可信。
"""
from __future__ import annotations


def draft_label(unit) -> str:
    return f"由经验单元「{unit.title}」（第 {unit.version} 版）生成，未经人工确认"


def acceptance_report_draft(unit, task) -> dict:
    """按单元里的验收清单，给这一单生成一份验收报告草稿（逐项待勾选）。"""
    items = list((unit.content or {}).get("checklist") or [])
    exclusions = list((unit.applicability or {}).get("exclusions") or [])
    lines = [f"验收报告草稿：《{task.title}》", "", draft_label(unit), "", "逐项核对："]
    lines += [f"☐ {it}" for it in items]
    if exclusions:
        lines += ["", "这份清单不适用的情形（遇到请人工判断）："] + [f"· {x}" for x in exclusions]
    lines += ["", "结论：（由发布方填写）"]
    return {"text": "\n".join(lines), "label": draft_label(unit), "items": items}


RUNNERS = {"acceptance_report_draft": acceptance_report_draft}
