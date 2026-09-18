"""ORC 编排引擎：plan → dispatch → observe → evaluate 的一次 tick。

与 agent harness 的对应关系：
- tool 调用 = 发布任务给平台上的其他人（真实合约托管 + 验收 + 纠纷兜底）；
- observation = 任务验收结果（completed 成果 / cancelled 失败 / 驳回问题）；
- 迭代 = 观测到问题后自动生成「修复步」再次分发，直到达标或触及护栏。

护栏（ORC-004）是本模块的第一性要求：agent 会自动花钱，必须有预算上限、
迭代上限与显式停机条件，且所有资金动作仍复用既有托管/守恒/审计链路。
"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.modules.account.models import utcnow

from .models import Mission, MISSION_TRANSITIONS, MissionStep


def transition(db: Session, mission: Mission, new_status: str) -> Mission:
    """ORC-003 编排状态机：白名单流转，非法流转 409（与任务状态机同治理）。"""
    allowed = MISSION_TRANSITIONS.get(mission.status, set())
    if new_status not in allowed:
        raise conflict(
            f"编排状态不允许从 {mission.status} 变更为 {new_status}", "invalid_mission_transition"
        )
    mission.status = new_status
    mission.updated_at = utcnow()
    db.add(mission)
    return mission


def plan(db: Session, mission: Mission) -> list[MissionStep]:
    """规划：复用 AI 分解网关把目标拆成可分发的工具调用（无 Key 时走模板引擎）。"""
    from app.modules.decompose.llm import get_gateway

    existing = db.query(MissionStep).filter(MissionStep.mission_id == mission.id).count()
    if existing:
        return []
    from app.core.config import settings

    # ORC-004 规划只用上限的一部分，其余留作重试预留金
    plan_budget = mission.budget_cap_cents * (10000 - settings.ORC_PLAN_RESERVE_BPS) // 10000
    items = get_gateway().decompose(
        db, mission.goal, mission.detail, mission.category, plan_budget
    )
    steps = []
    for item in items:
        # AIO-001/003 验收要点：优先用分解结果自带的，否则由 Mission 级要求
        # 与类目通用要点兜底——离线（模板引擎）路径同样有要点，不依赖 Key
        acceptance = list(item.get("acceptance") or []) or default_acceptance(mission)
        step = MissionStep(
            mission_id=mission.id, iteration=0, tool="publish_task",
            title=item["title"][:120],
            acceptance=acceptance,
            args={
                "title": item["title"][:120],
                "description": _with_acceptance(item.get("description", ""), acceptance),
                "category": mission.category,
                "budget_cents": item["budget_cents"],
                "required_skills": item.get("required_skills", []),
            },
        )
        db.add(step)
        steps.append(step)
    db.flush()
    return steps


def default_acceptance(mission: Mission) -> list[str]:
    """AIO-001 通用验收要点：执行者从一开始就知道「怎样算做完」，
    这比事后争议便宜得多。"""
    base = [str(x) for x in (mission.acceptance_criteria or [])]
    return base + ["提交交付说明", "附现场/成果图片凭证"]


def _with_acceptance(description: str, acceptance: list) -> str:
    """AIO-002 验收要点写进任务描述，随合约条款一并留痕。"""
    if not acceptance:
        return description
    lines = "\n".join(f"- {a}" for a in acceptance)
    return f"{description}\n\n【验收要点】\n{lines}".strip()


def _dispatch_step(db: Session, mission: Mission, step: MissionStep) -> None:
    """分发一步 = 调用「发布任务」这个工具（真实建单并进广场招募）。"""
    from app.modules.task.models import Task
    from app.modules.task.service import transition as task_transition, validate_publishable

    budget = int(step.args.get("budget_cents", 0))
    if budget <= 0:
        step.status = "failed"
        step.observation = "预算为 0，无法分发"
        db.add(step)
        return
    # AIO-025 预算护栏 = 已实付 + 当前占用 + 本步。三项缺一不可：
    #   spent     已经付出去的钱不可逆，必须占额度，否则「完成→评审不达标→重发」
    #             会让实际支出翻倍，正是护栏要防的 runaway；
    #   committed 在途任务的占用；
    # 取消的任务只从 committed 释放（钱没花出去），因此重试不会被虚耗的额度饿死。
    if mission.spent_cents + mission.committed_cents + budget > mission.budget_cap_cents:
        raise bad_request(
            f"超出编排预算上限（{mission.budget_cap_cents} 分），本步需 {budget} 分",
            "budget_cap_exceeded",
        )
    task = Task(
        creator_id=mission.owner_id,
        title=step.args["title"],
        description=step.args.get("description", ""),
        category=step.args.get("category", mission.category),
        required_skills=step.args.get("required_skills", []),
        budget_cents=budget,
        is_remote=True,
    )
    db.add(task)
    db.flush()
    validate_publishable(task, db)
    task_transition(db, task, "published")
    step.task_id = task.id
    step.status = "dispatched"
    mission.committed_cents += budget
    db.add_all([step, mission])


def observe(db: Session, mission: Mission) -> list[dict]:
    """观测：读取已分发步骤对应任务的真实状态，转成 observation。"""
    from app.modules.task.models import Task

    out = []
    steps = (
        db.query(MissionStep)
        .filter(MissionStep.mission_id == mission.id, MissionStep.status == "dispatched")
        .all()
    )
    from .review import run_review

    for step in steps:
        task = db.get(Task, step.task_id) if step.task_id else None
        if not task:
            continue
        budget = int(step.args.get("budget_cents", 0))
        if task.status == "completed":
            # AIO-010 不再只看状态：对交付做一次评审，质量进入循环判定
            result = run_review(db, mission, step)
            # AIO-024 完成放款 → 占用转为真实花费
            mission.committed_cents = max(0, mission.committed_cents - budget)
            mission.spent_cents += budget
            db.add(mission)
            if result.verdict == "pass":
                step.status = "done"
                step.observation = (
                    f"任务 #{task.id} 已验收通过，评审 {result.score} 分"
                    f"（{result.reviewer}）"
                )
            else:
                # AIO-012 模型/规则判定不达标**不动钱**：任务该放的款已经放了，
                # 这里只把这一步标记为需要整改，由修复步补齐缺失项
                step.status = "failed"
                step.observation = (
                    f"任务 #{task.id} 已完成但评审未达标（{result.score} 分）："
                    f"缺 {'、'.join(result.missing) or '未说明'}"
                )
        elif task.status == "cancelled":
            step.status = "failed"
            # AIO-024 取消 = 钱没花出去，释放占用额度，否则 agent 会被
            # 一堆「已经不存在的占用」饿死，循环永远收敛不了
            mission.committed_cents = max(0, mission.committed_cents - budget)
            db.add(mission)
            step.observation = f"任务 #{task.id} 已取消/流单，需要修复步重试"
        elif task.status == "disputed":
            step.observation = f"任务 #{task.id} 进入纠纷仲裁，暂停推进"
        else:
            step.observation = f"任务 #{task.id} 进行中（{task.status}）"
        db.add(step)
        out.append({"step_id": step.id, "task_id": task.id,
                    "task_status": task.status, "observation": step.observation})
    return out


def evaluate(db: Session, mission: Mission) -> dict:
    """评估：完成度 = 已验收步数 / 总步数；并汇总待修复问题。"""
    rows = db.query(MissionStep).filter(MissionStep.mission_id == mission.id).all()
    # superseded：已被修复步取代的旧步，不再计入分母，否则任何一次失败都会
    # 让编排永远无法达到 100%（修复成功也没用）——这是循环能收敛的关键
    steps = [s for s in rows if s.status != "superseded"]
    total = len(steps)
    done_steps = [s for s in steps if s.status == "done"]
    done = len(done_steps)
    failed = [s for s in steps if s.status == "failed"]
    mission.completion_pct = int(done * 100 / total) if total else 0
    # AIO-020 质量维度：已完成步的平均评审分。只看完成率会把
    # 「交一句做完了」和「交合格产出」当成同一件事
    scores = [s.review_score for s in done_steps if s.review_score]
    mission.quality_pct = int(sum(scores) / len(scores)) if scores else 0
    db.add(mission)
    return {"total_steps": total, "done": done, "failed": len(failed),
            "superseded": sum(1 for s in rows if s.status == "superseded"),
            "completion_pct": mission.completion_pct,
            "quality_pct": mission.quality_pct,
            "issues": [{"step_id": s.id, "title": s.title, "observation": s.observation,
                        "missing": s.review_missing or []}
                       for s in failed]}


# AIO-021 连续多少轮不达标后重新拆解（而不是继续重试同一形态）
REPLAN_AFTER_ATTEMPTS = 2
# 重新拆解时的预算上浮（万分比）：原价没人接/做不好，多半是价格不匹配
REPLAN_BUDGET_BOOST_BPS = 3000


def _make_remedy_steps(db: Session, mission: Mission) -> list[MissionStep]:
    """AIO-021/022 迭代：为失败步生成**带整改要点**的修复步。

    原实现是同规格重发（`args=dict(s.args)`）——上次没人接或没做好，
    同样的标题、预算、技能要求再发一次，凭什么这次会成功？
    这里做三件事让循环真的收敛：
      1. 把上一轮缺什么写进任务描述，执行者知道要补齐哪些；
      2. 连续两轮不达标 → 上浮预算重新招募，而不是无限重试同一形态；
      3. 幂等改用 `parent_step_id` 外键（原来靠标题字符串匹配，多轮后
         标题会变成「[修复] [修复] [修复] X」，且匹配本身很脆）。
    """
    db.flush()  # 会话 autoflush=False：先落盘 observe 的状态改动，否则 SQL 过滤读到旧值
    failed = (
        db.query(MissionStep)
        .filter(MissionStep.mission_id == mission.id, MissionStep.status == "failed")
        .all()
    )
    remedies = []
    for step in failed:
        # AIO-022 幂等：已经为该步生成过修复步就不再重复
        dup = (
            db.query(MissionStep)
            .filter(MissionStep.mission_id == mission.id,
                    MissionStep.parent_step_id == step.id)
            .first()
        )
        if dup:
            continue

        attempt = step.attempt + 1
        args = dict(step.args)
        missing = list(step.review_missing or [])
        notes = []
        if missing:
            notes.append("上一轮未达标，请务必补齐：" + "、".join(missing))
        else:
            notes.append("上一轮未能完成，请按验收要点重新执行。")

        # AIO-021 连续多轮不达标 → 重新拆解：上浮预算重新招募
        if attempt > REPLAN_AFTER_ATTEMPTS:
            boosted = args.get("budget_cents", 0) * (10000 + REPLAN_BUDGET_BOOST_BPS) // 10000
            args["budget_cents"] = boosted
            notes.append(f"已第 {attempt} 次尝试，上浮预算重新招募。")

        args["description"] = _with_acceptance(
            f"{args.get('description', '')}\n\n【本轮整改要求】\n" + "\n".join(notes),
            step.acceptance or [],
        )
        # 标题保持稳定，轮次由 attempt 表达（不再层层加 [修复] 前缀）
        args["title"] = f"{step.title}（第 {attempt} 次）"[:120]

        remedy = MissionStep(
            mission_id=mission.id, iteration=mission.iteration + 1, tool="publish_task",
            title=step.title, args=args, is_remedy=1,
            parent_step_id=step.id, attempt=attempt,
            acceptance=list(step.acceptance or []),
        )
        db.add(remedy)
        step.status = "superseded"  # 原步交由修复步接续，不再算作未决失败
        step.observation = f"{step.observation}（已生成第 {attempt} 次尝试接续）"
        db.add(step)
        remedies.append(remedy)
    db.flush()
    return remedies


def _log_event(db: Session, mission: Mission, action: str, summary: str) -> None:
    """AIO-023 迭代时间线：agent 必须可解释，否则没人敢授权它自动花钱。"""
    from .models import MissionEvent

    db.add(MissionEvent(mission_id=mission.id, iteration=mission.iteration,
                        action=action, summary=summary[:2000]))


def tick(db: Session, mission: Mission) -> dict:
    """推进一轮循环：规划（首轮）→ 观测 → 评估 → 分发/迭代 → 停机判定。"""
    if mission.status in ("succeeded", "failed", "cancelled"):
        raise conflict("编排已结束，不可继续推进", "mission_closed")

    planned = plan(db, mission) if mission.status == "planning" else []
    if mission.status == "planning":
        transition(db, mission, "running")

    observations = observe(db, mission)
    report = evaluate(db, mission)

    # AIO-020 达标：全部步骤完成**且**平均评审分过线。
    # 只看完成率会把「交一句做完了」当成达标——质量闸门是这个循环的意义所在。
    from .review import QUALITY_BAR

    if report["total_steps"] and report["done"] == report["total_steps"]:
        if report["quality_pct"] >= QUALITY_BAR:
            transition(db, mission, "succeeded")
            _log_event(db, mission, "completed",
                       f"全部 {report['total_steps']} 步完成，平均评审 "
                       f"{report['quality_pct']} 分，编排达标。")
            return {"action": "completed", "planned": len(planned),
                    "observations": observations, **report, "status": mission.status}
        # 全完成但均分不过线：不算成功，转为整改（下面的失败步处理会接手）
        _log_event(db, mission, "quality_gate",
                   f"全部步骤完成但平均分 {report['quality_pct']} 低于门槛 "
                   f"{QUALITY_BAR}，转入整改。")

    # 有失败步 → 生成修复步（快速迭代），受迭代上限约束
    remedies = []
    if report["failed"]:
        if mission.iteration >= mission.max_iterations:
            mission.last_error = "达到迭代上限仍有未完成步骤"
            transition(db, mission, "failed")
            db.add(mission)
            _log_event(db, mission, "give_up",
                       f"已迭代 {mission.iteration} 轮（上限 {mission.max_iterations}），"
                       f"仍有 {report['failed']} 步未达标，停机等待人工。")
            return {"action": "give_up", "observations": observations, **report,
                    "status": mission.status}
        remedies = _make_remedy_steps(db, mission)
        mission.iteration += 1
        db.add(mission)

    # 分发所有待分发步（含本轮新生成的修复步），预算不足则挂起等待人工决策
    db.flush()
    pending = (
        db.query(MissionStep)
        .filter(MissionStep.mission_id == mission.id, MissionStep.status == "pending")
        .order_by(MissionStep.id).all()
    )
    dispatched = 0
    for step in pending:
        try:
            _dispatch_step(db, mission, step)
            dispatched += 1 if step.status == "dispatched" else 0
        except Exception as exc:  # 预算护栏等 → 挂起而非失败，保留人工介入余地
            detail = getattr(exc, "detail", None)
            mission.last_error = (detail or {}).get("message", str(exc))[:300] \
                if isinstance(detail, dict) else str(exc)[:300]
            transition(db, mission, "blocked")
            db.add(mission)
            _log_event(db, mission, "blocked",
                       f"分发受阻并挂起：{mission.last_error}。"
                       f"已占用 {mission.committed_cents} 分 / 上限 "
                       f"{mission.budget_cap_cents} 分，需人工加预算或改规格。")
            return {"action": "blocked", "dispatched": dispatched,
                    "observations": observations, **report,
                    "status": mission.status, "error": mission.last_error}

    if mission.status == "blocked" and dispatched:
        transition(db, mission, "running")
    report = evaluate(db, mission)
    action = "dispatched" if dispatched else "waiting"
    _log_event(db, mission, action, _summarize(
        mission, planned, observations, remedies, dispatched, report))
    return {"action": action,
            "planned": len(planned), "dispatched": dispatched,
            "remedies": len(remedies), "observations": observations,
            **report, "status": mission.status}


def _summarize(mission: Mission, planned, observations, remedies, dispatched, report) -> str:
    """AIO-023 人类可读摘要：做了什么 / 现在怎样 / 下一步。"""
    did = []
    if planned:
        did.append(f"规划出 {len(planned)} 步")
    if observations:
        did.append(f"观测 {len(observations)} 个在途任务")
    if remedies:
        did.append(f"生成 {len(remedies)} 个整改步")
    if dispatched:
        did.append(f"发布 {dispatched} 个任务")
    doing = "；".join(did) or "本轮无可推进的动作"

    state = (f"完成 {report['done']}/{report['total_steps']} 步"
             f"（{report['completion_pct']}%），平均评审 {report['quality_pct']} 分")
    if report["issues"]:
        first = report["issues"][0]
        gaps = "、".join(first.get("missing") or []) or "见观测说明"
        nxt = f"待整改 {len(report['issues'])} 步，首个「{first['title']}」缺：{gaps}"
    elif report["done"] < report["total_steps"]:
        nxt = "等待在途任务被接单与验收"
    else:
        nxt = "无待办"
    budget = (f"预算占用 {mission.committed_cents} / 上限 {mission.budget_cap_cents} 分，"
              f"已实付 {mission.spent_cents} 分")
    return f"{doing}。当前：{state}；{budget}。下一步：{nxt}。"
