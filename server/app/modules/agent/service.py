"""AGT agent 的准入判定与执行（48 号 spec）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.modules.account.models import User, utcnow

from . import criteria as crit
from .models import AgentProfile, AgentRun
from .runner import AgentUnavailable, get_runner


def get_profile(db: Session, agent_user_id: int) -> AgentProfile | None:
    return db.get(AgentProfile, agent_user_id)


def eligibility_block(db: Session, profile: AgentProfile, task) -> str:
    """返回拒绝理由；空字符串表示可以接。

    **单一判断来源**：报名端点、推荐召回、执行前复检都调这一个函数。
    三处各写一遍 if，迟早有一处漏掉——这是 V61 `_appeal_block` 立下的规矩。
    """
    if not profile.is_active:
        return "该助理已停用"
    agent_user = db.get(User, profile.user_id)
    if not agent_user or agent_user.is_banned or agent_user.is_deleted:
        return "该助理不可用"
    # AGT-010 **排第一位**：平台上大量保洁/跑腿/到场维修同样有类目、有预算、
    # 在招募中。没有这条闸门，agent 会报名一个上门保洁单然后交付一段文字。
    if not task.is_remote:
        return "需到场完成的任务不能由 AI 助理执行"
    # AGT-011 领域不命中时明确拒绝，好过输出一堆看着像那么回事的东西
    if task.category not in (profile.domains or []):
        return f"「{task.category}」不在该助理的能力范围内"
    # AGT-012 赔付能力上限
    if task.budget_cents > profile.max_task_budget_cents:
        return "任务金额超出 AI 助理的承接上限，请交由人工执行"
    return ""


def assert_eligible(db: Session, profile: AgentProfile, task) -> None:
    block = eligibility_block(db, profile, task)
    if block:
        raise bad_request(block, "agent_not_eligible")


def eligible_agents(db: Session, task) -> list[AgentProfile]:
    """该任务可用的 agent。AGT-018 召回处用它，普通推荐池不含 agent。"""
    return [
        p for p in db.query(AgentProfile).filter(AgentProfile.is_active.is_(True)).all()
        if not eligibility_block(db, p, task)
    ]


def running_run(db: Session, task_id: int) -> AgentRun | None:
    return (
        db.query(AgentRun)
        .filter(AgentRun.task_id == task_id, AgentRun.status == "running")
        .first()
    )


def latest_run(db: Session, task_id: int) -> AgentRun | None:
    return (
        db.query(AgentRun)
        .filter(AgentRun.task_id == task_id)
        .order_by(AgentRun.id.desc())
        .first()
    )


def delivery_block(db: Session, task) -> str:
    """AGT-013/031 agent 执行的任务能不能提交交付。

    同样是单一判断来源：`deliver` 端点与客户端按钮读同一个函数。
    非 agent 任务恒返回空——这条闸门只管 agent。
    """
    executor = db.get(User, task.executor_id) if task.executor_id else None
    if not executor or not executor.is_agent:
        return ""
    run = latest_run(db, task.id)
    if not run:
        return "尚未执行，无法提交交付"
    if run.status == "running":
        return "执行中，请稍候"
    if run.status == "failed":
        return f"执行失败，无法提交交付：{run.error or '未知错误'}"
    if run.status == "escalated":
        return "AI 置信度不足，已转人工核验，暂不能提交交付"
    return ""


def run_agent(db: Session, task, contract_id: int | None = None) -> AgentRun:
    """执行一次。成功、升级、失败三种结局都落库。"""
    profile = get_profile(db, task.executor_id)
    if not profile:
        raise conflict("该任务的执行方不是 AI 助理", "not_an_agent")
    # AGT-014 并发闸：重复触发不重复扣费、不产生两份交付
    if running_run(db, task.id):
        raise conflict("该任务已有执行在进行中", "agent_run_in_progress")
    assert_eligible(db, profile, task)  # 成交后配置可能已改，执行前复检

    run = AgentRun(
        agent_user_id=profile.user_id, task_id=task.id, contract_id=contract_id,
        status="running",
    )
    db.add(run)
    db.flush()
    profile.runs_total += 1

    try:
        result = get_runner().run(
            model=profile.model,
            system_prompt=profile.system_prompt,
            title=task.title,
            description=task.description,
            category=task.category,
        )
    except AgentUnavailable as exc:
        # AGT-015 失败不假装成功，**也不降级成模板**。
        # 与任务分解故意不同：分解降级成模板仍然有用、发布方会自己看一眼；
        # 交付物降级成模板就是拿废品换钱。同一个「降级」，两个场景答案相反。
        run.status = "failed"
        run.error = str(exc)[:300]
        run.cost_cents = 0
        run.finished_at = utcnow()
        profile.runs_failed += 1
        return run

    run.output = result.output
    # AGT-016 成本必须落库：没有它，agent 接单是赚是赔谁也说不清
    run.cost_cents = result.cost_cents or profile.cost_per_run_cents
    # AGT-013 拿不到置信度时按**最低**处理（必然升级），不按最高——
    # 代价落在别人身上时往保守一侧倒
    run.confidence_bps = max(0, min(10000, int(result.confidence_bps or 0)))

    # AGT-030 客观判据由平台执行。agent 自报的置信度再高，判据不过就是不过。
    results, all_auto_passed = crit.evaluate(task.acceptance_criteria or [], result.output)
    run.criteria_results = results

    if not all_auto_passed:
        run.status = "failed"
        failed = [r["text"] for r in results if r["kind"] == "auto" and not r["passed"]]
        run.error = "验收判据未通过：" + "；".join(failed)[:260]
        profile.runs_failed += 1
    elif run.confidence_bps < profile.confidence_threshold_bps:
        run.status = "escalated"
        run.error = (
            f"置信度 {run.confidence_bps / 100:.1f}% 低于阈值 "
            f"{profile.confidence_threshold_bps / 100:.1f}%"
        )
        profile.runs_escalated += 1
    else:
        run.status = "succeeded"
        profile.runs_succeeded += 1

    run.finished_at = utcnow()
    return run


def gross_margin_cents(db: Session, agent_user_id: int) -> dict:
    """AGT-016 累计毛利 = 完成任务的收入 − API 成本。

    只计**已完成**任务的收入：跑了但没验收的不算收入，而成本已经付了——
    把未完成的算成收入，就是把亏损记成盈利。
    """
    from app.modules.task.models import Task

    runs = db.query(AgentRun).filter(AgentRun.agent_user_id == agent_user_id).all()
    cost = sum(r.cost_cents for r in runs)
    task_ids = {r.task_id for r in runs}
    revenue = 0
    if task_ids:
        revenue = sum(
            t.budget_cents
            for t in db.query(Task).filter(Task.id.in_(task_ids), Task.status == "completed").all()
        )
    return {"revenue_cents": revenue, "cost_cents": cost, "margin_cents": revenue - cost}
