"""场景包定义的格式与校验（123 号 spec 第 2 节）。

定义可以来自管理后台，也可以来自仓库里的 `seeds/*.json`（skill `scenario-discovery` 产出的就是这种文件）。
两条路走同一个校验：格式（pydantic）+ 规则（`rule_problems`）。规则是平台的红线写成代码：
- 每个助手专家都要声明**禁止动作**与**人工关口**；高风险人群（财税、法务、政策）的助手必须把钱、签署、申报都设为人工关口；
- 工具只能从白名单里选（`TOOLS`）；
- 知识条目必须有出处；政策类必须有有效期（政策会变，过期的条目要被看见）；
- 资产 key 在包内唯一，助手引用的方法与知识必须在包里。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

KEY = r"^[a-z0-9][a-z0-9-]{1,58}$"
SEGMENTS = ("opc", "gig", "creator", "studio", "buyer", "general")
# 这些人群的事碰钱、碰合同、碰政府：助手只出草稿，三道关口一道不能少
HIGH_RISK_SEGMENTS = ("opc",)
GATES = {
    "money": "付款、收款、转账、托管",
    "sign": "签署合同或协议",
    "file": "向税务、市场监管等机关申报或提交材料",
    "publish": "对外发布内容或任务",
    "share_personal": "把个人信息交给第三方",
}
REQUIRED_HIGH_RISK_GATES = {"money", "sign", "file"}
# 137 号 spec（SCN-103）：按人群补的关口。发单方（buyer）的助手碰的是钱与对外发布任务；
# 创作者（creator）的助手碰的是钱与版权授权（签署）。缺一道就不能上线
SEGMENT_REQUIRED_GATES = {"buyer": {"money", "publish"}, "creator": {"money", "sign"}}
# 助手专家能调用的工具（白名单）。每个工具都是**只读或只出草稿**的平台能力，碰钱的一个没有
TOOLS = {
    "pack.knowledge": "本包的知识条目（带出处与有效期）",
    "notebook.search": "用户自己的知识库（只读本人的）",
    "legal.faq": "平台法律常识问答（高风险问题拒答并指向紧急渠道）",
    "workbench.method": "把本包的方法套到用户的工作台任务上（用户点了才套）",
    "opc.books": "一人公司记账底稿：本季度收支汇总与免税标准提示（只读本人的）",
    "opc.calendar": "一人公司申报日历：按本人设置推算的近期申报与年报节点",
    "opc.contract_review": "合同体检：按条款清单与风险句式指出要看的地方（不构成法律意见）",
    "gig.nearby": "接单者：「现在有空」时半径内招募中的单（直线距离）",
    "gig.quote": "接单者：同类目近 180 天成交价分布与到手估算（不是承诺价）",
    "experience.search": "平台经验单元（只读引用：历史闭环沉淀的做法与清单，写明版本与验证状态）",
    "creator.brief": "创作者：需求单体检——按九项清单指出甲方需求里没写的项和该追问的话（只读你贴进来的文字）",
    "live.script_check": "小店直播：话术自查——按词表标出绝对化用语、功效承诺、价格与限时的词和出处（只读你贴进来的文字，不断定违规）",
}


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Step(_M):
    title: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=500)


class MethodDef(_M):
    key: str = Field(pattern=KEY)
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=500)
    steps: list[Step] = Field(min_length=1, max_length=30)


class KnowledgeDef(_M):
    key: str = Field(pattern=KEY)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    kind: Literal["rule", "policy", "howto"] = "howto"
    source: str = Field(min_length=2, max_length=300)        # 出处：法规名、官网、平台规则……
    valid_until: date | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)


class RoutineDef(_M):
    key: str = Field(pattern=KEY)
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["digest", "review", "reminder"]
    freq: Literal["daily", "weekly", "monthly"]
    time_of_day: str = "09:00"
    weekday: int = Field(default=0, ge=0, le=6)
    monthday: int = Field(default=1, ge=1, le=31)
    note: str = Field(default="", max_length=500)

    @field_validator("time_of_day")
    @classmethod
    def _hhmm(cls, v):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("时间格式为 HH:MM（北京时间）")
        return v


class TaskTemplateDef(_M):
    key: str = Field(pattern=KEY)
    title: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=2000)
    acceptance: list[str] = Field(default_factory=list, max_length=10)


class AssistantDef(_M):
    """助手专家的**角色契约**（蓝皮书第 6、24 章）：人设、输入、输出、禁止动作、工具白名单、人工关口。"""
    key: str = Field(pattern=KEY)
    name: str = Field(min_length=1, max_length=40)
    persona: str = Field(min_length=1, max_length=500)
    inputs: list[str] = Field(min_length=1, max_length=10)
    outputs: list[str] = Field(min_length=1, max_length=10)
    forbidden: list[str] = Field(min_length=1, max_length=10)
    tools: list[str] = Field(min_length=1, max_length=10)
    human_gates: list[str] = Field(min_length=1, max_length=5)
    methods: list[str] = Field(default_factory=list, max_length=20)
    knowledge: list[str] = Field(default_factory=list, max_length=50)
    # 答不了时把人送去发一单（找专业的人）：类目名
    fallback_category: str = Field(default="", max_length=40)


class Score(_M):
    """覆盖 × 频率 × 痛感 × AI 可完成度 × 商业价值 ÷ 交付成本（VISION 1.8）。"""
    coverage: int = Field(ge=1, le=5)
    frequency: int = Field(ge=1, le=5)
    pain: int = Field(ge=1, le=5)
    ai: float = Field(ge=0, le=1)
    value: int = Field(ge=1, le=5)
    cost: int = Field(ge=1, le=5)

    def total(self) -> float:
        return round(self.coverage * self.frequency * self.pain * self.ai * self.value / self.cost, 2)


class PackDef(_M):
    key: str = Field(pattern=KEY)
    title: str = Field(min_length=1, max_length=80)
    segment: Literal["opc", "gig", "creator", "studio", "buyer", "general"]
    summary: str = Field(default="", max_length=500)
    pains: list[str] = Field(min_length=1, max_length=10)
    score: Score
    evidence: list[str] = Field(default_factory=list, max_length=10)   # 为什么做它：信号、访谈、业界做法
    assistants: list[AssistantDef] = Field(default_factory=list, max_length=5)
    methods: list[MethodDef] = Field(default_factory=list, max_length=20)
    knowledge: list[KnowledgeDef] = Field(default_factory=list, max_length=100)
    routines: list[RoutineDef] = Field(default_factory=list, max_length=10)
    task_templates: list[TaskTemplateDef] = Field(default_factory=list, max_length=10)


def rule_problems(p: PackDef) -> list[str]:
    out: list[str] = []
    if not (p.assistants or p.methods or p.knowledge or p.routines or p.task_templates):
        out.append("场景包里一样资产都没有")
    for group in ("assistants", "methods", "knowledge", "routines", "task_templates"):
        keys = [a.key for a in getattr(p, group)]
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            out.append(f"{group} 的 key 重复：{dup}")
    methods = {m.key for m in p.methods}
    knowledge = {k.key for k in p.knowledge}
    for a in p.assistants:
        bad_tools = sorted(set(a.tools) - set(TOOLS))
        if bad_tools:
            out.append(f"助手「{a.name}」用了白名单外的工具：{bad_tools}")
        bad_gates = sorted(set(a.human_gates) - set(GATES))
        if bad_gates:
            out.append(f"助手「{a.name}」的人工关口不认识：{bad_gates}")
        if p.segment in HIGH_RISK_SEGMENTS and not REQUIRED_HIGH_RISK_GATES <= set(a.human_gates):
            out.append(f"助手「{a.name}」服务高风险人群（{p.segment}），钱、签署、申报都必须是人工关口")
        need = SEGMENT_REQUIRED_GATES.get(p.segment, set()) - set(a.human_gates)
        if need:
            out.append(f"助手「{a.name}」服务{p.segment}人群，缺人工关口：{sorted(need)}")
        if sorted(set(a.methods) - methods):
            out.append(f"助手「{a.name}」引用了包里没有的方法：{sorted(set(a.methods) - methods)}")
        if sorted(set(a.knowledge) - knowledge):
            out.append(f"助手「{a.name}」引用了包里没有的知识：{sorted(set(a.knowledge) - knowledge)}")
        if a.knowledge and "pack.knowledge" not in a.tools:
            out.append(f"助手「{a.name}」引用了知识却没有 pack.knowledge 工具")
    for k in p.knowledge:
        if k.kind == "policy" and k.valid_until is None:
            out.append(f"政策类知识「{k.title}」必须写有效期（政策会变）")
    return out


# SCN-112：雷达一键起草的知识条目里留给人填的地方。草稿可以存，**留着它就不能提交审核、不能上线**
PLACEHOLDER = "【待填写】"


def placeholder_problems(p: PackDef) -> list[str]:
    """提交审核与上线前查：起草出来的空位还有没填的，就不让往下走（AI / 模板只出草稿，内容要人写）。"""
    out = []
    for k in p.knowledge:
        left = [name for name, v in (("正文", k.body), ("出处", k.source), ("标题", k.title)) if PLACEHOLDER in v]
        if left:
            out.append(f"知识「{k.title.replace(PLACEHOLDER, '').strip() or k.key}」的{'、'.join(left)}还有「{PLACEHOLDER}」没填")
    return out


def validate(data: dict) -> tuple[PackDef | None, list[str]]:
    """格式与规则一起校验。返回（定义, 问题）：有问题时定义可能为 None。"""
    from pydantic import ValidationError

    try:
        p = PackDef.model_validate(data)
    except ValidationError as e:
        return None, [f"{'.'.join(str(x) for x in err['loc'])}：{err['msg']}" for err in e.errors()]
    return p, rule_problems(p)
