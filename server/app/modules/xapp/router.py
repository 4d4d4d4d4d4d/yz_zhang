"""XAPP 跨 App 助手接口（161 号 spec）。

两类调用方，同一个用户身份：
- 本人（App / Web）：授权、发起、看计划、确认、叫停、看记录；
- 执行器（本人设备上的 Android 无障碍执行器、桌面执行器、iOS 快捷指令、测试用模拟执行器）：拿下一步、回报结果。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.modules.account.models import User

from . import planner
from . import service as svc
from .models import XappGrant, XappRun, XappStep

router = APIRouter(tags=["xapp"])


class GrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    apps: list[str] = Field(min_length=1, max_length=20)
    actions: list[str] = Field(min_length=1, max_length=10)
    days: int = 7
    device_label: str = Field(default="", max_length=60)
    allow_cloud_vision: bool = False


class StepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app: str = Field(min_length=2, max_length=120)
    action: str = Field(min_length=2, max_length=20)
    intent: str = Field(min_length=1, max_length=200)
    channel: str = Field(min_length=2, max_length=10)
    vision_where: str = Field(default="device", max_length=8)


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant_id: int
    goal: str = Field(min_length=2, max_length=200)
    executor: str = "mock"
    confirm_mode: str = "red_only"
    steps: list[StepIn] = Field(min_length=1, max_length=100)


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant_id: int
    goal: str = Field(min_length=2, max_length=200)


class ResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    summary: str = Field(default="", max_length=2000)


class StopIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=200)


def _own_run(db: Session, run_id: int, user: User) -> XappRun:
    r = db.get(XappRun, run_id)
    if not r or r.user_id != user.id:
        raise not_found("没有这次执行")
    return r


def _own_step(db: Session, run: XappRun, step_id: int) -> XappStep:
    s = db.get(XappStep, step_id)
    if not s or s.run_id != run.id:
        raise not_found("这次执行里没有这一步")
    return s


@router.get("/xapp/catalog")
def catalog():
    """能授权的动作、只能本人亲手做的红线动作、通道顺序。客户端照这个画界面，不自己抄一份。"""
    return {"actions": [{"key": k, "label": v} for k, v in svc.ACTIONS.items()],
            "red_line": [{"key": k, "label": v} for k, v in svc.RED_LINE.items()],
            "channels": list(svc.CHANNELS), "executors": list(svc.EXECUTORS),
            # XAPP-015：出计划的规则表。开着隐私沙箱的手机按这张表在本机出计划（目标原文不上云）
            "plan_rules": planner.rules(),
            "notice": "付款、转账、签署、发布、对外发消息、改密码、删除数据只能由你亲手完成；智能体只把你带到那个页面。"
                      "屏幕内容默认只在本机处理。"}


@router.post("/xapp/grants", status_code=201)
def create_grant(body: GrantIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    g = svc.create_grant(db, user.id, body.apps, body.actions, body.days, body.device_label.strip(),
                         body.allow_cloud_vision)
    return svc.dump_grant(g)


@router.get("/xapp/grants")
def list_grants(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.query(XappGrant).filter(XappGrant.user_id == user.id).order_by(XappGrant.id.desc()).all()
    return [svc.dump_grant(g) for g in rows]


@router.delete("/xapp/grants/{grant_id}")
def revoke_grant(grant_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    g = db.get(XappGrant, grant_id)
    if not g or g.user_id != user.id:
        raise not_found("没有这个授权")
    stopped = svc.revoke_grant(db, g)
    return {**svc.dump_grant(g), "runs_stopped": stopped}


@router.post("/xapp/plan")
def plan(body: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """XAPP-015 一句目标 → 计划草稿：只出草稿、不发起；本人看过再用它发起执行。
    配了模型就由模型出并按授权重新校验，否则按规则出；开着隐私沙箱的人这个接口被拦下，在本机按同一张规则表出。"""
    g = svc.active_grant(db, body.grant_id, user.id)
    return planner.make_plan(db, user.id, g, body.goal.strip())


@router.post("/xapp/runs", status_code=201)
def create_run(body: RunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    r = svc.create_run(db, user.id, body.grant_id, body.goal.strip(), body.executor, body.confirm_mode,
                       [s.model_dump() for s in body.steps])
    return svc.dump_run(db, r, with_steps=True)


@router.get("/xapp/runs")
def list_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.query(XappRun).filter(XappRun.user_id == user.id).order_by(XappRun.id.desc()).limit(50).all()
    return [svc.dump_run(db, r) for r in rows]


@router.get("/xapp/runs/{run_id}")
def get_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return svc.dump_run(db, _own_run(db, run_id, user), with_steps=True)


@router.post("/xapp/runs/{run_id}/next")
def next_step(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """XAPP-007 执行器拿下一步：execute（去做）/ handoff（红线步，带人到页面）/ awaiting_confirm（等本人确认）/
    done / stopped / needs_human。"""
    return svc.next_step(db, _own_run(db, run_id, user))


@router.post("/xapp/runs/{run_id}/steps/{step_id}/result")
def report(run_id: int, step_id: int, body: ResultIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db, scope="function")):
    run = _own_run(db, run_id, user)
    return svc.report(db, run, _own_step(db, run, step_id), body.ok, body.summary)


@router.post("/xapp/runs/{run_id}/steps/{step_id}/confirm")
def confirm(run_id: int, step_id: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db, scope="function")):
    """XAPP-003/004 本人确认：普通步确认后才会派发；红线步确认表示「我自己做完了」。"""
    run = _own_run(db, run_id, user)
    return svc.confirm(db, run, _own_step(db, run, step_id))


@router.post("/xapp/runs/{run_id}/stop")
def stop(run_id: int, body: StopIn, user: User = Depends(get_current_user),
         db: Session = Depends(get_db, scope="function")):
    """XAPP-004 一键叫停：执行器下次拿步骤时就停。"""
    run = _own_run(db, run_id, user)
    svc.stop(run, body.reason.strip())
    return svc.dump_run(db, run)
