"""XAPP-015 一句目标 → 计划草稿（161 号 spec，V191）。

两条路，结果都只是**草稿**：本人看过、改过，再用它发起执行。
- 规则：认 App 名、按关键词认动作、按 API → 深链 → 控件树 → 屏幕识别的顺序挑通道、自动标红线步。
  规则表也放进 `/xapp/catalog`，开着隐私沙箱的手机用共享 SDK 的 `planXappLocally` 在本机按同一张表出计划；
  两边对同一组例子出同样的计划（`packages/core/src/xapp-plan-cases.json`，两边测试都读）。
- 模型：平台配了模型网关就让模型出，**再按授权重新校验一遍**：不在授权里的 App 一律丢掉、动作是不是红线由服务端判，
  模型说了不算；模型出错或什么都没给，退回规则并写明。
"""
from __future__ import annotations

import logging
import re

from app.core.config import settings

from .models import XappGrant
from .service import ACTIONS, CHANNELS, RED_LINE

logger = logging.getLogger(__name__)

# 常见 App 的名字与它们支持的通道（按偏好排）。没列的 App 只能走控件树与屏幕识别。
APP_HINTS: list[dict] = [
    {"app": "com.autonavi.minimap", "names": ["高德", "地图", "导航", "路线"], "channels": ["deeplink", "a11y", "vision"]},
    {"app": "com.baidu.BaiduMap", "names": ["百度地图"], "channels": ["deeplink", "a11y", "vision"]},
    {"app": "com.tencent.mm", "names": ["微信"], "channels": ["a11y", "vision"]},
    {"app": "com.eg.android.AlipayGphone", "names": ["支付宝"], "channels": ["deeplink", "a11y", "vision"]},
    {"app": "com.sankuai.meituan", "names": ["美团"], "channels": ["deeplink", "a11y", "vision"]},
    {"app": "com.ss.android.lark", "names": ["飞书"], "channels": ["api", "deeplink", "a11y", "vision"]},
    {"app": "com.alibaba.android.rimet", "names": ["钉钉"], "channels": ["api", "deeplink", "a11y", "vision"]},
    {"app": "com.taobao.taobao", "names": ["淘宝"], "channels": ["deeplink", "a11y", "vision"]},
]
DEFAULT_CHANNELS = ["a11y", "vision"]

# 关键词 → 动作。红线动作排在前面：一句话里同时有「回复」与「看」，两步都要，红线那步不能被吞掉。
ACTION_WORDS: list[dict] = [
    {"action": "pay", "words": ["付款", "支付", "付钱", "买单", "下单"], "intent": "付款（你亲手完成）"},
    {"action": "transfer", "words": ["转账", "转钱", "打钱"], "intent": "转账（你亲手完成）"},
    {"action": "sign", "words": ["签署", "签字", "签合同", "签约"], "intent": "签署（你亲手完成）"},
    {"action": "publish", "words": ["发布", "发帖", "发朋友圈"], "intent": "发布（你亲手完成）"},
    {"action": "send_message", "words": ["回复", "发消息", "发给", "告诉", "通知"], "intent": "发出消息（你亲手点发送）"},
    {"action": "change_security", "words": ["改密码", "修改密码", "安全设置"], "intent": "改安全设置（你亲手完成）"},
    {"action": "delete", "words": ["删除", "删掉", "清空"], "intent": "删除（你亲手完成）"},
    {"action": "fill", "words": ["搜索", "搜", "填写", "输入", "查一下", "查"], "intent": "填写或搜索"},
    {"action": "read", "words": ["看看", "查看", "读取", "看一下", "多久", "多少"], "intent": "读取页面上的结果"},
    {"action": "tap", "words": ["点击", "选择", "点一下"], "intent": "点选"},
    {"action": "navigate", "words": ["跳到", "切换到", "进入"], "intent": "跳转页面"},
]


XAPP_PLAN_PROMPT = (
    "你在帮用户规划如何在他自己的手机上操作其他 App 完成一个目标。只能用给出的授权 App。"
    "每一步写 app（包名）、action（open/read/fill/tap/navigate，或红线动作 pay/transfer/sign/publish/send_message/"
    "change_security/delete）、intent（这一步要做什么，一句中文）、channel（api/deeplink/a11y/vision，能用前面的就不用后面的）、"
    "why（为什么要这一步）。付款、转账、签署、发布、对外发消息、改安全设置、删除数据一律写成红线动作，由用户亲手完成。"
    "步骤越少越好，不要编造用户没说的事。"
)
XAPP_PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["steps"],
    "properties": {"steps": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["app", "action", "intent", "channel", "why"],
        "properties": {"app": {"type": "string"}, "action": {"type": "string"}, "intent": {"type": "string"},
                       "channel": {"type": "string"}, "why": {"type": "string"}}}}},
}


def rules() -> dict:
    """规则表本身（进 `/xapp/catalog`，本机出计划用同一张表）。"""
    return {"apps": APP_HINTS, "default_channels": DEFAULT_CHANNELS, "actions": ACTION_WORDS,
            "channel_order": list(CHANNELS), "max_steps": settings.XAPP_MAX_STEPS}


def _hint(app: str) -> dict | None:
    return next((h for h in APP_HINTS if h["app"] == app), None)


def _channels(app: str) -> list[str]:
    h = _hint(app)
    return list(h["channels"]) if h else list(DEFAULT_CHANNELS)


def _pick_channel(app: str, action: str) -> str:
    """XAPP-002：能用前面的就不用后面的。打开优先深链；其余优先接口，再控件树，最后屏幕识别。"""
    ch = _channels(app)
    if action == "open":
        return ch[0]
    return next((c for c in ch if c != "deeplink"), ch[-1])


def _mentions(goal: str, apps: list[str]) -> list[tuple[int, str]]:
    """授权里的 App 在这句话里第一次出现的位置（认名字，也认包名）。"""
    found = []
    for app in apps:
        h = _hint(app)
        names = [app] + (h["names"] if h else [])
        pos = [goal.find(n) for n in names if n and goal.find(n) >= 0]
        if pos:
            found.append((min(pos), app))
    return sorted(found)


def _step(app: str, action: str, intent: str, why: str) -> dict:
    return {"app": app, "action": action, "action_label": RED_LINE.get(action) or ACTIONS.get(action, action),
            "intent": intent[:200], "channel": _pick_channel(app, action), "vision_where": "device",
            "red_line": action in RED_LINE, "why": why}


def plan_by_rules(goal: str, apps: list[str]) -> list[dict]:
    goal = goal.strip()
    mentions = _mentions(goal, apps) or [(0, apps[0])]
    hits: list[tuple[int, str, str, str]] = []   # (位置, 动作, 意图, 命中的词)
    # App 的名字先占位：「支付宝」里的「支付」不是付款
    taken: list[tuple[int, int]] = [(m.start(), m.end()) for n in sorted({n for h in APP_HINTS for n in h["names"]} | set(apps),
                                                                          key=len, reverse=True)
                                    for m in re.finditer(re.escape(n), goal)]
    # 长词先认（同样长时红线在前）：「查看」整个算读取，里面的「查」不再算一次搜索
    pairs = sorted(((w, r) for r in ACTION_WORDS for w in r["words"]), key=lambda x: -len(x[0]))
    for w, rule in pairs:
        for m in re.finditer(re.escape(w), goal):
            span = (m.start(), m.end())
            if any(a < span[1] and span[0] < b for a, b in taken):
                continue
            taken.append(span)
            hits.append((m.start(), rule["action"], rule["intent"], w))
    hits.sort()
    steps: list[dict] = []
    opened: set[str] = set()
    for pos, action, intent, word in hits:
        app = next((a for p, a in reversed(mentions) if p <= pos), mentions[0][1])
        if app not in opened:
            opened.add(app)
            steps.append(_step(app, "open", "打开" + ((_hint(app) or {}).get("names") or [app])[0], "先打开要操作的 App"))
        if steps and steps[-1]["app"] == app and steps[-1]["action"] == action:
            continue
        steps.append(_step(app, action, intent, f"目标里有「{word}」"))
    for _, app in mentions:
        if app not in opened:
            opened.add(app)
            steps.append(_step(app, "open", "打开" + ((_hint(app) or {}).get("names") or [app])[0], "目标里提到了它"))
    return steps[: settings.XAPP_MAX_STEPS]


def _sanitize(raw: list, apps: list[str]) -> tuple[list[dict], list[str]]:
    """模型给的步骤按授权重新校验：不在授权里的 App 丢掉；红线由服务端判；通道不认识就按规则挑。"""
    out, dropped = [], []
    for s in raw[: settings.XAPP_MAX_STEPS]:
        if not isinstance(s, dict):
            continue
        app, action = str(s.get("app", "")), str(s.get("action", ""))
        if app not in apps:
            dropped.append(f"「{app}」不在授权里，那一步去掉了")
            continue
        if action not in ACTIONS and action not in RED_LINE:
            dropped.append(f"「{action}」不是认得的动作，那一步去掉了")
            continue
        st = _step(app, action, str(s.get("intent", "")) or (RED_LINE.get(action) or ACTIONS[action]),
                   str(s.get("why", ""))[:200] or "模型给出")
        ch = str(s.get("channel", ""))
        if ch in CHANNELS and ch in _channels(app):
            st["channel"] = ch
        out.append(st)
    return out, dropped


def make_plan(db, user_id: int, g: XappGrant, goal: str) -> dict:
    from app.core.sandbox import gateway_for

    gw = gateway_for(db, user_id)
    source, notes, steps = "rules", [], []
    planner = getattr(gw, "plan_xapp", None)
    if planner is not None:
        try:
            steps, dropped = _sanitize(planner(db, goal, list(g.apps)), list(g.apps))
            notes += dropped
            if steps:
                source = "model"
            else:
                notes.append("模型给的步骤都不能用，下面是按规则出的")
        except Exception as exc:  # noqa: BLE001 —— 模型出错要看得见，并退回规则
            logger.warning("xapp_plan_fallback", extra={"error_type": type(exc).__name__})
            notes.append("模型这次没给出可用的计划，下面是按规则出的")
            steps = []
    if not steps:
        steps = plan_by_rules(goal, list(g.apps))
    missing = sorted({s["action"] for s in steps if not s["red_line"] and s["action"] not in g.actions})
    if missing:
        notes.append("这些动作还没授权：" + "、".join(ACTIONS[a] for a in missing) + "。先在授权里加上，或去掉那几步")
    if any(s["red_line"] for s in steps):
        notes.append("标了红线的步骤，智能体只把你带到那个页面，由你亲手完成")
    return {"goal": goal, "grant_id": g.id, "source": source, "steps": steps, "missing_actions": missing,
            "ready": bool(steps) and not missing, "notes": notes}
