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

    同样是单一判断来源：`deliver` 端点、平台代交付（AGT-060）与客户端按钮
    读同一个函数。非 agent 任务恒返回空——这条闸门只管 agent。
    """
    executor = db.get(User, task.executor_id) if task.executor_id else None
    if not executor or not executor.is_agent:
        return ""
    run = latest_run(db, task.id)
    if not run:
        return "尚未执行，无法提交交付"
    if run.status == "running":
        return "执行中，请稍候"
    # VER-022 人工核验通过（或已修正）即解除闸门——这就是 AGT-050 说的那个出口
    from app.modules.verify import service as verify_service

    outcome = verify_service.unblocking_outcome(db, task.id)
    if run.status == "failed":
        # AGT-067 判据/审核没过的 run，**只有「已修正」能解锁**。
        # 修正稿在 VER-030 里被强制重跑了一遍平台判据，不过就报错——
        # 客观闸门一次也没被绕过，变的是那份被判的文本。
        # 而 `approved` 只是一个人说了句「行」，那是**覆盖**判据而不是满足判据，
        # 与 AGT-030「不让执行方自己判卷」同一条理由（换成核验人判也一样）。
        if outcome == "revised":
            return ""
        return f"执行失败，无法提交交付：{run.error or '未知错误'}"
    if run.status == "escalated":
        # 置信度不足只是「没把握」，不是「判据没过」，所以 approved 也能解锁
        if outcome:
            return ""
        return "AI 置信度不足，需人工核验后方可提交交付"
    return ""


# 交付正文入 `ProgressLog.content`（Text 列）。截断只为防一次巨量粘贴撑爆
# 纠纷证据导出，不是业务上限。
DELIVERY_CONTENT_MAX = 20000


def submit_agent_delivery(db: Session, task, note: str = "") -> bool:
    """AGT-060 **平台代 agent 提交交付**；返回是否真的交付了。

    这一条补的是 48/49 两批合起来漏掉的最后一步：agent 没有登录态
    （AGT-017，也不该有），而 `POST /tasks/{id}/deliver` 要求
    `user.id == task.executor_id`——于是**生产里没有任何人能替它交付**，
    任务永远停在 `in_progress`，发布方的钱永远躺在托管里。
    测试没红，只因为它自己绕开 HTTP 直接调服务层（见 56 号 spec 第 0 节）。

    为什么由平台发起，而不是放宽 `deliver` 的身份校验：那条校验同时管着
    所有人类任务，为一个 AI 的特例去放宽一条通用身份闸门，代价不对等。
    而平台本来就是 AI 履约的**责任主体**（AGT-017 已写进合同条款），
    由责任主体发起交付，身份是自洽的。
    """
    from app.modules.task import service as task_service
    from app.modules.task.models import ProgressLog

    executor = db.get(User, task.executor_id) if task.executor_id else None
    if not executor or not executor.is_agent:
        return False
    # V76 那个坑：`delivery_block` 会**再查一次库**，而会话是 autoflush=False。
    # 调用方（run_agent / submit_outcome）刚在内存里改完状态，不 flush 的话
    # 那次查询看不见，代交付会被自己刚解除的闸门挡住。
    db.flush()
    # AGT-062 幂等：已交付（pending_acceptance）或已完成的任务再调一次，
    # 不产生第二条交付记录、不重置 delivered_at
    if task.status != "in_progress":
        return False
    # AGT-061 **新开的路必须比原来的路更窄**：代交付调闸门，不重写闸门
    if delivery_block(db, task):
        return False
    run = latest_run(db, task.id)
    content = (note or (run.output if run else "")).strip()
    if not content:
        return False

    task.delivered_at = utcnow()
    # AGT-064 user_id 写 **agent 的 user 行**，不写发布方：
    # 纠纷证据链里必须能看出这份交付物是谁交的，写成发布方就是在证据里撒谎
    db.add(ProgressLog(task_id=task.id, user_id=executor.id, kind="delivery",
                       content=content[:DELIVERY_CONTENT_MAX]))
    task_service.transition(db, task, "pending_acceptance")
    return True


def moderate_output(db: Session, text: str) -> tuple[str, list[str]]:
    """AGT-051 产出送内容审核，返回 (status, labels)，status ∈ pass/review/reject。

    48 号 spec 把这条记成「本批没做」，理由是当时未经审核的产出只有当事人
    看得见。**本批把产出接到了交付上**——它会成为交付物、进纠纷证据链、
    被验收——所以接交付的同一批必须把审核接上，否则是在给一个已知的洞加流量。

    供应商故障时**不放行、也不销毁**，升级人审。与 UMOD-010 的 fail-open
    方向一致（不因第三方抖动而销毁内容），但不 open 到直接交付：上传物的
    用途是自证，挡住它伤的是被侵害方；agent 产出的用途是换钱，放过它伤的是
    发布方和平台自己。**分界线是代价落在谁身上。**
    """
    from app.vendors import base as vendor_base
    from app.vendors.base import VendorError
    from app.vendors.registry import get_provider

    if not text.strip():
        return "pass", []
    provider = get_provider("moderation")
    try:
        verdict = vendor_base.call(
            db, "moderation", provider.name, "check_agent_output",
            # 送审文本**不进调用日志**，只记字符数：把待审文本抄一份到日志里，
            # 等于给违规内容多开一个落点
            {"chars": len(text)},
            lambda: provider.check("text", text),
        )
    except VendorError as exc:
        return "review", [f"provider_error:{exc.code}"]
    labels = [str(x) for x in (verdict.data.get("labels") or [])]
    if verdict.status == "reject":
        return "reject", labels or ["违规内容"]
    if verdict.status == "review":
        reason = verdict.data.get("reason")
        return "review", labels + ([str(reason)] if reason else [])
    return "pass", labels


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

    # VER-051 **经验回流**：同类目最近的非通过核验结论拼进系统提示词。
    # 这张表从 V74 起一直在写，而全仓没有任何地方读它——需求里那句
    # 「能够持续帮助迭代任务完成」的载体，此前只落了一半。
    from app.modules.verify import service as verify_service

    lessons = verify_service.lessons_for(db, task.category)
    run.lessons_used = [row.id for row in lessons]
    system_prompt = profile.system_prompt + verify_service.lessons_prompt(lessons)

    try:
        result = get_runner().run(
            model=profile.model,
            system_prompt=system_prompt,
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

    # AGT-051/065 **审核先于判据**：一份违规的产出，判据过没过不重要。
    mod_status, mod_labels = moderate_output(db, result.output)
    run.moderation_status = mod_status
    run.moderation_labels = mod_labels
    if mod_status == "reject":
        # 被拒的产出**不入库**（与 UMOD-011 对称），但 labels 留下来
        run.output = ""
        run.status = "failed"
        run.error = ("产出未通过内容安全审核：" + "、".join(mod_labels))[:300]
        profile.runs_failed += 1
        run.finished_at = utcnow()
        return run

    # AGT-030 客观判据由平台执行。agent 自报的置信度再高，判据不过就是不过。
    results, all_auto_passed = crit.evaluate(task.acceptance_criteria or [], result.output)
    run.criteria_results = results

    if not all_auto_passed:
        run.status = "failed"
        failed = [r["text"] for r in results if r["kind"] == "auto" and not r["passed"]]
        run.error = "验收判据未通过：" + "；".join(failed)[:260]
        profile.runs_failed += 1
    elif mod_status == "review":
        # AGT-066 审核拿不准（或供应商挂了）→ 升级人审，不自动交付。
        # 这不是「审核失败」：本地/沙箱实现看不了图，扔掉会让非生产部署不可用。
        run.status = "escalated"
        run.error = ("产出需人工核验：" + "、".join(mod_labels))[:300]
        profile.runs_escalated += 1
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
