"""AI-DEC-001（366 号 spec）对话式需求澄清：发单人只会说一句话时，追问几句把需求问清，再给一份能发布的草稿。

规则版，**不调模型**：可预测、零成本、离线也能用，问题都来自平台已经沉淀的「一单活最常缺的几样」（126 号任务画像的完整度、
213 号 K12 规则、发单拦截）。每次请求把已经答过的带上，服务端给出下一批（最多 3 个）还没答的问题和随答随长的草稿；
必答的都答完就 `ready`。发不发、怎么改由人在发布页定——这里不落库、不发布。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.modules.account.models import User

router = APIRouter(tags=["task"])

MAX_QUESTIONS = 3
# 说法 → 类目：只收最常见、几乎不会认错的几个；认不出就问，不猜
SYNONYMS = {
    "打扫": "保洁", "清洁": "保洁", "擦玻璃": "保洁", "搬家": "搬家", "搬东西": "搬家", "遛狗": "宠物照护",
    "喂猫": "宠物照护", "取快递": "跑腿", "送文件": "跑腿", "代买": "跑腿", "陪爸妈": "助老陪伴", "陪老人": "助老陪伴",
    "修空调": "家电维修", "修洗衣机": "家电维修", "水龙头": "水电维修", "跳闸": "水电维修", "logo": "设计", "海报": "设计", "剪视频": "短视频剪辑",
}
DATE_HINT = re.compile(r"今天|明天|后天|周[一二三四五六日天]|星期|\d+\s*[号日]|\d+\s*点|\d+\s*月|上午|下午|晚上|月底|月初|尽快")
ACCEPT_HINT = re.compile(r"验收|标准|交付物|交付|完成后|做到|算完成")
REMOTE_HINT = re.compile(r"线上|远程|网上|在线")
FAMILY_HINT = re.compile(r"爸|妈|父母|老人|爷爷|奶奶|外公|外婆|家里人")
MONEY = re.compile(r"(\d+(?:\.\d+)?)\s*(元|块|万)?")

QUESTIONS = {
    "category": "这是哪一类的活？选一个最接近的",
    "where": "在哪里做？线上就能做，还是要上门（哪个城市、哪个区或小区）？",
    "when": "什么时候要？哪天几点，或者最晚哪天前做完",
    "scope": "具体要做到什么程度？比如几个房间、几件东西、多大面积、多长",
    "acceptance": "怎么算做完？说一个你验收时会看的标准",
    "budget": "预算大概多少钱？不确定可以先跳过，发布页会给同类单的参考价",
    "for_whom": "是替家里人发的吗？到场找谁、怎么称呼（发布页可以勾「替别人发」，联系方式成交后才给对方）",
}
REQUIRED = ("category", "where", "when", "scope", "acceptance")
LABEL = {"where": "地点", "when": "时间", "scope": "要做到", "acceptance": "验收", "budget": "预算", "for_whom": "服务对象"}


class ClarifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=2, max_length=500)
    answers: dict[str, str] = Field(default_factory=dict, max_length=10)
    category: str = Field(default="", max_length=50)


def _categories(db: Session) -> list[str]:
    from .models import Category

    return [c.name for c in db.query(Category).filter(Category.active.is_(True)).order_by(Category.id)]


def guess_category(text: str, names: list[str]) -> str:
    """说明里直接出现类目名（取最长的那个），或者出现最常见的说法；都没有就返回空，交给追问。"""
    hits = [n for n in names if n and n in text]
    if hits:
        return max(hits, key=len)
    for word, cat in SYNONYMS.items():
        if word in text.lower() and cat in names:
            return cat
    return ""


def _blocked(text: str) -> dict | None:
    """发单拦截与 K12 规则先过一遍：问了半天发不出去，不如一开始就说清。"""
    from .errand import _raise_for, restricted_errand
    from .k12 import assert_no_k12_tutoring

    try:
        kind = restricted_errand(text)
        if kind:
            _raise_for(kind)
        assert_no_k12_tutoring(text)
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"code": "blocked", "message": str(e.detail)}
        return {"code": detail.get("code", "blocked"), "message": detail.get("message", "")}
    return None


def _budget_cents(answer: str) -> int | None:
    m = MONEY.search(answer or "")
    if not m:
        return None
    n = float(m.group(1)) * (10000 if m.group(2) == "万" else 1)
    return int(round(n * 100)) if n > 0 else None


def _title(text: str) -> str:
    first = re.split(r"[。！？!?\n；;，,]", text.strip(), maxsplit=1)[0].strip()
    return (first or text.strip())[:30]


def clarify(db: Session, body: ClarifyIn) -> dict:
    text = body.text.strip()
    answers = {k: v.strip()[:200] for k, v in body.answers.items() if k in QUESTIONS and v and v.strip()}
    everything = " ".join([text, *answers.values()])
    blocked = _blocked(everything)
    names = _categories(db)
    category = next((c for c in (body.category, answers.get("category", "")) if c and c in names), "")
    category = category or guess_category(everything, names)
    known = {
        "category": bool(category),
        "where": "where" in answers or bool(REMOTE_HINT.search(text)),
        "when": "when" in answers or bool(DATE_HINT.search(text)),
        "scope": "scope" in answers or len(text) >= 20,
        "acceptance": "acceptance" in answers or bool(ACCEPT_HINT.search(text)),
        "budget": "budget" in answers,
        "for_whom": "for_whom" in answers or not FAMILY_HINT.search(everything),
    }
    order = [*REQUIRED, "budget", "for_whom"]
    pending = [k for k in order if not known[k]]
    common = names[:12]
    questions = [{"key": k, "ask": QUESTIONS[k], "required": k in REQUIRED,
                  "options": common if k == "category" else []} for k in pending[:MAX_QUESTIONS]]
    lines = [text]
    for k in ("where", "when", "scope", "acceptance", "budget", "for_whom"):
        if answers.get(k):
            lines.append(f"{LABEL[k]}：{answers[k]}")
    draft = {
        "title": _title(text),
        "description": "\n".join(lines),
        "category": category,
        "is_remote": bool(REMOTE_HINT.search(answers.get("where", "") or text)),
        "budget_cents": _budget_cents(answers.get("budget", "")),
        "on_behalf_hint": bool(FAMILY_HINT.search(everything)),
    }
    ready = not blocked and not any(not known[k] for k in REQUIRED)
    return {"questions": [] if blocked else questions, "draft": draft, "ready": ready, "blocked": blocked,
            "remaining_required": sum(1 for k in REQUIRED if not known[k])}


@router.post("/tasks/clarify")
def clarify_endpoint(body: ClarifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """发单前的追问：不落库、不发布，只回下一批问题和草稿。"""
    return clarify(db, body)
