"""XAPP 跨 App 助手的平台侧规则（161 号 spec）。

执行器（Android 无障碍、桌面、iOS 快捷指令、测试用的模拟执行器）都走同一个协议：
拿下一步 → 执行 → 回报结果。平台负责：授权白名单、通道顺序、红线步交还给人、逐步确认、叫停、失败两次交还、记录脱敏。
"""
from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.timefmt import iso
from app.modules.account.models import utcnow

from .models import XappGrant, XappRun, XappStep

# XAPP-001 可以授权的动作（不含红线类）
ACTIONS = {"open": "打开", "read": "读取页面", "fill": "填写", "tap": "点击", "navigate": "跳转页面"}
# XAPP-003 红线类：只能由本人在屏幕上亲手做；智能体只把人带到那个页面
RED_LINE = {"pay": "付款", "transfer": "转账", "sign": "签署", "publish": "发布", "send_message": "对外发消息",
            "change_security": "改密码或安全设置", "delete": "删除数据"}
# XAPP-002 通道：越往后越容易因为对方改版失效
CHANNELS = ("api", "deeplink", "a11y", "vision")
EXECUTORS = ("android", "desktop", "ios_shortcut", "mock")
MAX_FAILS = 2
GRANT_MAX_DAYS = 90
APP_ID = re.compile(r"^[A-Za-z0-9_.\-]{2,120}$")


def _now():
    return utcnow()


def active_grant(db: Session, grant_id: int, user_id: int) -> XappGrant:
    g = db.get(XappGrant, grant_id)
    if not g or g.user_id != user_id:
        raise not_found("没有这个授权")
    if g.revoked_at is not None or g.expires_at <= _now():
        raise conflict("这个授权已经撤销或过期，请重新授权", "xapp_grant_inactive")
    return g


def create_grant(db: Session, user_id: int, apps: list[str], actions: list[str], days: int,
                 device_label: str, allow_cloud_vision: bool) -> XappGrant:
    bad = [a for a in apps if not APP_ID.match(a)]
    if bad or not apps:
        raise bad_request("目标 App 要写包名或应用标识（例如 com.autonavi.minimap），至少一个", "xapp_bad_app")
    unknown = sorted(set(actions) - set(ACTIONS))
    if unknown or not actions:
        if set(unknown) & set(RED_LINE):
            raise bad_request(f"{'、'.join(RED_LINE[k] for k in unknown if k in RED_LINE)}这类动作不能授权给智能体，"
                              "执行时会把你带到那个页面，由你亲手完成", "xapp_red_line_not_grantable")
        raise bad_request(f"能授权的动作只有：{'、'.join(f'{k}（{v}）' for k, v in ACTIONS.items())}", "xapp_bad_action")
    if not 1 <= days <= GRANT_MAX_DAYS:
        raise bad_request(f"授权期限是 1 到 {GRANT_MAX_DAYS} 天", "xapp_bad_days")
    g = XappGrant(user_id=user_id, apps=sorted(set(apps)), actions=sorted(set(actions)), device_label=device_label,
                  allow_cloud_vision=allow_cloud_vision, expires_at=_now() + timedelta(days=days))
    db.add(g)
    db.flush()
    return g


def revoke_grant(db: Session, g: XappGrant) -> int:
    """XAPP-001 撤销即停：用这个授权还在跑的执行全部叫停。"""
    g.revoked_at = _now()
    n = 0
    for r in db.query(XappRun).filter(XappRun.grant_id == g.id, XappRun.status.in_(("running", "needs_human"))):
        r.status, r.stop_reason, r.finished_at = "stopped", "授权已撤销", _now()
        n += 1
    return n


def _validate_step(g: XappGrant, s: dict, i: int) -> dict:
    app, action, channel = s.get("app", ""), s.get("action", ""), s.get("channel", "")
    where = s.get("vision_where", "device") or "device"
    if app not in g.apps:
        raise forbidden(f"第 {i} 步要操作的「{app}」不在授权的 App 里", "xapp_app_not_granted")
    if channel not in CHANNELS:
        raise bad_request(f"第 {i} 步的通道只能是 {'、'.join(CHANNELS)}", "xapp_bad_channel")
    red = action in RED_LINE
    if not red and action not in g.actions:
        raise forbidden(f"第 {i} 步的动作「{ACTIONS.get(action, action)}」没有授权", "xapp_action_not_granted")
    if channel == "vision" and where == "cloud" and not g.allow_cloud_vision:
        raise forbidden("这个授权没有允许云端模型看屏幕：屏幕内容默认只在本机处理", "xapp_cloud_vision_off")
    if where not in ("device", "cloud"):
        raise bad_request("屏幕识别只能在本机（device）或云端（cloud）", "xapp_bad_channel")
    return {"app": app, "action": action, "intent": (s.get("intent") or "")[:200], "channel": channel,
            "vision_where": where if channel == "vision" else "device", "red_line": red}


def create_run(db: Session, user_id: int, grant_id: int, goal: str, executor: str, confirm_mode: str,
               steps: list[dict]) -> XappRun:
    g = active_grant(db, grant_id, user_id)
    if executor not in EXECUTORS:
        raise bad_request(f"执行器只能是 {'、'.join(EXECUTORS)}", "xapp_bad_executor")
    if confirm_mode not in ("each", "red_only"):
        raise bad_request("确认方式只能是每步确认（each）或只确认红线步（red_only）", "xapp_bad_confirm_mode")
    if not 1 <= len(steps) <= settings.XAPP_MAX_STEPS:
        raise bad_request(f"一次执行 1 到 {settings.XAPP_MAX_STEPS} 步", "xapp_too_many_steps")
    since = _now() - timedelta(days=1)
    if db.query(XappRun).filter(XappRun.user_id == user_id, XappRun.created_at >= since).count() >= settings.XAPP_DAILY_RUNS:
        raise conflict(f"一天最多发起 {settings.XAPP_DAILY_RUNS} 次跨 App 执行", "xapp_daily_limit")
    checked = [_validate_step(g, s, i + 1) for i, s in enumerate(steps)]
    run = XappRun(user_id=user_id, grant_id=g.id, goal=goal[:200], executor=executor, confirm_mode=confirm_mode)
    db.add(run)
    db.flush()
    for i, c in enumerate(checked):
        db.add(XappStep(run_id=run.id, seq=i + 1, needs_confirm=c["red_line"] or confirm_mode == "each", **c))
    db.flush()
    return run


def _steps(db: Session, run: XappRun) -> list[XappStep]:
    return db.query(XappStep).filter(XappStep.run_id == run.id).order_by(XappStep.seq).all()


def _finish_if_done(run: XappRun, steps: list[XappStep]) -> None:
    if run.status == "running" and all(s.status in ("done", "done_by_user", "skipped") for s in steps):
        run.status, run.finished_at = "done", _now()


def next_step(db: Session, run: XappRun) -> dict:
    """XAPP-007 执行器拿下一步。叫停、交还给人、授权失效都不再派发；要确认的没确认就等；红线步只「带人到那个页面」。"""
    if run.status != "running":
        return {"state": run.status, "reason": run.stop_reason}
    g = db.get(XappGrant, run.grant_id)
    if g is None or g.revoked_at is not None or g.expires_at <= _now():
        run.status, run.stop_reason, run.finished_at = "stopped", "授权已撤销或过期", _now()
        return {"state": "stopped", "reason": run.stop_reason}
    steps = _steps(db, run)
    for s in steps:
        if s.status in ("done", "done_by_user", "skipped"):
            continue
        if s.needs_confirm and s.confirmed_at is None:
            return {"state": "awaiting_confirm", "step": dump_step(s)}
        if s.red_line:
            # 红线步：执行器只负责把人带到那个页面，等本人亲手做完再在平台上确认
            return {"state": "handoff", "step": dump_step(s)}
        s.status, s.updated_at = "dispatched", _now()
        s.attempts += 1
        return {"state": "execute", "step": dump_step(s)}
    _finish_if_done(run, steps)
    return {"state": run.status, "reason": run.stop_reason}


_DIGITS = re.compile(r"\d{6,}")
_PHONE = re.compile(r"1[3-9]\d{9}")


def scrub(text: str) -> str:
    """XAPP-005 结果摘要脱敏：长串数字（卡号、验证码、证件号）与手机号打码。"""
    text = _PHONE.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], text or "")
    return _DIGITS.sub(lambda m: m.group(0)[:2] + "*" * (len(m.group(0)) - 4) + m.group(0)[-2:], text)[:500]


def report(db: Session, run: XappRun, step: XappStep, ok: bool, summary: str) -> dict:
    """XAPP-009 回报结果：成功就往下走；同一步连续失败两次，整次执行交还给人，不盲点。"""
    if run.status != "running":
        raise conflict("这次执行已经停了，结果不再接收", "xapp_run_not_running")
    if step.status != "dispatched":
        raise conflict("这一步没有派发给执行器", "xapp_step_not_dispatched")
    step.result, step.updated_at = scrub(summary), _now()
    if ok:
        step.status = "done"
    else:
        step.status = "pending"
        if step.attempts >= MAX_FAILS:
            step.status = "failed"
            run.status, run.stop_reason = "needs_human", f"第 {step.seq} 步连续失败 {MAX_FAILS} 次：{step.result[:80]}"
    _finish_if_done(run, _steps(db, run))
    return {"run_status": run.status, "step": dump_step(step)}


def confirm(db: Session, run: XappRun, step: XappStep) -> dict:
    """XAPP-003/004 本人确认：普通步确认后才派发；红线步确认表示「我自己做完了」。"""
    if run.status != "running":
        raise conflict("这次执行已经停了", "xapp_run_not_running")
    if step.status in ("done", "done_by_user", "skipped"):
        raise conflict("这一步已经处理过了", "xapp_step_done")
    step.confirmed_at, step.updated_at = _now(), _now()
    if step.red_line:
        step.status = "done_by_user"
    _finish_if_done(run, _steps(db, run))
    return {"run_status": run.status, "step": dump_step(step)}


def stop(run: XappRun, reason: str) -> None:
    if run.status in ("running", "needs_human"):
        run.status, run.stop_reason, run.finished_at = "stopped", (reason or "本人叫停")[:200], _now()


def dump_grant(g: XappGrant) -> dict:
    now = _now()
    return {"id": g.id, "device_label": g.device_label, "apps": g.apps, "actions": g.actions,
            "allow_cloud_vision": g.allow_cloud_vision, "expires_at": iso(g.expires_at), "revoked_at": iso(g.revoked_at),
            "active": g.revoked_at is None and g.expires_at > now, "created_at": iso(g.created_at)}


def dump_step(s: XappStep) -> dict:
    return {"id": s.id, "seq": s.seq, "app": s.app, "action": s.action,
            "action_label": RED_LINE.get(s.action) or ACTIONS.get(s.action, s.action),
            "intent": s.intent, "channel": s.channel, "vision_where": s.vision_where, "red_line": s.red_line,
            "needs_confirm": s.needs_confirm, "confirmed": s.confirmed_at is not None, "status": s.status,
            "attempts": s.attempts, "result": s.result}


def dump_run(db: Session, r: XappRun, with_steps: bool = False) -> dict:
    out = {"id": r.id, "grant_id": r.grant_id, "goal": r.goal, "executor": r.executor, "confirm_mode": r.confirm_mode,
           "status": r.status, "stop_reason": r.stop_reason, "created_at": iso(r.created_at), "finished_at": iso(r.finished_at)}
    if with_steps:
        out["steps"] = [dump_step(s) for s in _steps(db, r)]
    return out
