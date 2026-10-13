"""AI-DEC-040~048 拆到能干活为止的树（106 号 spec，设计见 96 号）。

用户 2026-10-10 的设计意见：「任务拆解借鉴 todolist 生成过程，生成树类脉络够细够具体
的任务，这样有些 AI 可以闭环，有些需要求助其他专家」。V132 之前一次提案只产出**一层**，
且没有任何字段说这一步谁能干。

这里的三条硬规则：

1. **叶子靠判据，不靠深度**（AI-DEC-040）：交付物、验收标准、单一责任主体、可托管的预算，
   四条齐了才是叶子。深度与节点数是防失控的保险，不是停止条件。
2. **谁能闭环要有可查的依据**（AI-DEC-042）：「AI 可闭环」要平台 Agent 在该类目真的
   成功闭环过；判不出来就是 `unknown`，不猜。
3. **要资质的类目永不标 AI 可闭环**（AI-DEC-043）：按类目资质表直接否决，不走判定——
   接单侧已经用资质拦住的活儿，拆解侧放行等于从另一个门绕进去。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request, conflict, not_found

# 叶子四条判据缺了哪条（AI-DEC-040）。值是给用户看的名字
CRITERIA = {
    "deliverable": "交付物",
    "acceptance": "验收标准",
    "single_owner": "单一责任主体",
    "budget": "可托管的预算",
}

EXECUTOR_KINDS = ("ai_closable", "needs_human", "needs_expert", "needs_machine", "unknown")

# 停在这里的原因 -> 给用户的话（AI-DEC-045：停止原因对用户可见，不是静默截断）
STOP_NOTES = {
    "criteria_met": "四条判据齐全，可以直接开工",
    "max_depth": "已到深度上限，没有继续拆。补齐交付物与验收标准，它就能作为一步发布",
    "max_nodes": "整棵树已到节点上限，没有继续拆",
    "budget_fragment": "预算太少，再拆出来的步骤托管不了",
    "no_progress": "拆不出比它更细的步骤了",
    "invalid_output": "拆出来的步骤之间的依赖关系不成立（依赖自己或成环），这一步没有展开",
    "cost_cap": "这棵树调用模型的次数已到上限",
    "moderation": "拆出的步骤里有内容未通过审核，这一步没有展开",
    "template_limit": "模板只能拆一层。要更细，请补充交付物与验收标准，或在接入模型后再拆",
}

# AI-DEC-045 每条保险的触发次数，暴露到 /metrics。一个经常在深度上限截断的类目，
# 说明那一类的判据或模板不对，而不是用户的需求太复杂——**看不见就没人会去查**。
# 取值只来自 STOP_NOTES 的键（有界），不会撑爆指标基数。
_stops: dict[str, int] = {}


def record_stop(reason: str) -> None:
    if reason in STOP_NOTES:
        _stops[reason] = _stops.get(reason, 0) + 1


def stop_counts() -> dict[str, int]:
    return {r: _stops.get(r, 0) for r in STOP_NOTES if r != "criteria_met"}


EDITABLE = {"title", "description", "budget_cents", "deliverable", "acceptance",
            "single_owner", "category", "executor_hint", "depends_on"}
USER_HINTS = ("", "human", "expert", "ai")


# ------------------------------------------------------------------ 节点
def new_node(nid: int, parent: int | None, depth: int, spec: dict, budget: int,
             source: str, fallback: bool) -> dict:
    return {
        "id": nid, "parent": parent, "depth": depth,
        "title": spec["title"], "description": spec.get("description", ""),
        "required_skills": list(spec.get("required_skills", [])),
        "budget_cents": budget, "depends_on": [],
        "deliverable": spec.get("deliverable", ""), "acceptance": spec.get("acceptance", ""),
        "single_owner": bool(spec.get("single_owner", True)),
        "category": spec.get("category", ""), "executor_hint": spec.get("executor_hint", ""),
        "source": source, "fallback": fallback,
        "leaf": False, "missing": [], "stop_reason": "", "expanded": False,
        "executor_kind": "", "executor_basis": "", "required_cert": "",
        "task_id": None,
    }


def children_of(nodes: list[dict], nid: int | None) -> list[dict]:
    return [n for n in nodes if n["parent"] == nid]


def _by_id(nodes: list[dict], nid: int) -> dict:
    for n in nodes:
        if n["id"] == nid:
            return n
    raise not_found("拆解里没有这一步")


def _subtree_ids(nodes: list[dict], nid: int) -> set[int]:
    out, stack = set(), [nid]
    while stack:
        cur = stack.pop()
        out.add(cur)
        stack.extend(n["id"] for n in nodes if n["parent"] == cur)
    return out


# ------------------------------------------------------------------ 判定
class _Facts:
    """一次请求里的查表缓存：类目资质、Agent 闭环次数。"""

    def __init__(self, db: Session):
        self.db = db
        self._cert: dict[str, str | None] = {}
        self._runs: dict[str, int] = {}

    def cert(self, category: str) -> str | None:
        """类目的准入资质；类目不存在返回 None。"""
        if category not in self._cert:
            from app.modules.task.models import Category

            row = self.db.query(Category).filter(Category.name == category).first()
            self._cert[category] = (row.required_cert or "") if row else None
        return self._cert[category]

    def agent_closed_runs(self, category: str) -> int:
        """该类目下平台 Agent **成功且任务已被验收**的次数——自报成功不算。"""
        if category not in self._runs:
            from app.modules.agent.models import AgentRun
            from app.modules.task.models import Task

            self._runs[category] = (
                self.db.query(AgentRun.id).join(Task, Task.id == AgentRun.task_id)
                .filter(AgentRun.status == "succeeded", Task.status == "completed",
                        Task.category == category).count())
        return self._runs[category]


def judge_executor(facts: _Facts, category: str, hint: str) -> tuple[str, str, str]:
    """-> (executor_kind, 依据, required_cert)。依据必须是可查的事实，不是模型的话。"""
    cert = facts.cert(category) or ""
    if cert:
        # AI-DEC-043 硬否决：不看 hint，不走判定
        return ("needs_expert", f"类目「{category}」要求「{cert}」资质（平台类目资质表）", cert)
    if hint == "ai":
        runs = facts.agent_closed_runs(category)
        need = settings.DECOMPOSE_AI_CLOSABLE_MIN_RUNS
        if runs >= need:
            return ("ai_closable", f"平台 Agent 在「{category}」类目已成功闭环 {runs} 次（已验收）", "")
        return ("unknown",
                f"被认为 AI 可以做，但平台 Agent 在「{category}」类目只有 {runs} 次已验收的闭环"
                f"（至少 {need} 次才算有依据）——请选择交给人做，或换一个有资质要求的类目", "")
    if hint == "expert":
        return ("unknown",
                f"被认为需要专业资质，但类目「{category}」在平台类目资质表里没有资质要求——"
                "请选择它属于哪个要资质的类目，或交给人做", "")
    if hint == "machine":
        return ("unknown", "被认为需要设备或产能，平台还没有可核对的产能登记——请选择交给人做", "")
    if hint == "unknown":
        return ("unknown", "判断不了这一步谁能做——请选择交给人做，或选一个要资质的类目", "")
    return ("needs_human", "无资质门槛的人工步骤（默认）", "")


def evaluate(facts: _Facts, node: dict, root_category: str, has_children: bool) -> None:
    """AI-DEC-040 判叶子，AI-DEC-042/043 判谁能闭环。有子步骤的节点是组织结构，不判。"""
    if has_children:
        node.update(leaf=False, missing=[], executor_kind="", executor_basis="", required_cert="")
        if node["stop_reason"] == "criteria_met":
            node["stop_reason"] = ""
        return
    missing = []
    if len(node["deliverable"].strip()) < 2:
        missing.append("deliverable")
    if len(node["acceptance"].strip()) < 4:
        missing.append("acceptance")
    if not node["single_owner"]:
        missing.append("single_owner")
    if node["budget_cents"] < settings.DECOMPOSE_MIN_NODE_BUDGET_CENTS:
        missing.append("budget")
    node["missing"] = missing
    node["leaf"] = not missing
    if node["leaf"]:
        node["stop_reason"] = "criteria_met"
    elif node["stop_reason"] == "criteria_met":
        node["stop_reason"] = ""
    kind, basis, cert = judge_executor(facts, node["category"] or root_category,
                                       node["executor_hint"])
    node.update(executor_kind=kind, executor_basis=basis, required_cert=cert)


def _reevaluate_all(facts: _Facts, nodes: list[dict], root_category: str) -> None:
    parents = {n["parent"] for n in nodes}
    for n in nodes:
        evaluate(facts, n, root_category, n["id"] in parents)


# ------------------------------------------------------------------ 校验
def _dag_ok(n: int, deps: list[list[int]]) -> bool:
    for i, ds in enumerate(deps):
        if any(d < 0 or d >= n or d == i for d in ds):
            return False
    state = [0] * n

    def dfs(u):
        state[u] = 1
        for v in deps[u]:
            if state[v] == 1 or (state[v] == 0 and dfs(v)):
                return True
        state[u] = 2
        return False

    return not any(state[i] == 0 and dfs(i) for i in range(n))


def validate_tree(nodes: list[dict], root_budget: int) -> None:
    """AI-DEC-046 **每一层**：子步骤预算之和 ≤ 它的上一级；同级依赖不成环。

    改造前 `validate_items` 只在单层上做过——多层时，第三层的预算可以悄悄超过
    第二层，而那一层的钱是从第二层分出来的。
    """
    groups: dict[int | None, list[dict]] = {}
    for n in nodes:
        groups.setdefault(n["parent"], []).append(n)
    for pid, kids in groups.items():
        cap = root_budget if pid is None else _by_id(nodes, pid)["budget_cents"]
        total = sum(k["budget_cents"] for k in kids)
        if total > cap:
            where = "总任务" if pid is None else f"「{_by_id(nodes, pid)['title']}」"
            raise bad_request(f"{where}下面各步预算合计 {total / 100:.2f} 元，超过了它的 {cap / 100:.2f} 元",
                              "budget_exceeded")
        if any(k["budget_cents"] <= 0 for k in kids):
            raise bad_request("每一步的预算都必须大于 0", "budget_required")
        ids = [k["id"] for k in kids]
        pos = {nid: i for i, nid in enumerate(ids)}
        if any(d not in pos for k in kids for d in k["depends_on"]):
            raise bad_request("一步只能依赖同一级的其他步骤", "invalid_dependency")
        if not _dag_ok(len(kids), [[pos[d] for d in k["depends_on"]] for k in kids]):
            raise bad_request("步骤之间的依赖存在环或依赖了自己", "cyclic_dependency")


def unresolved(nodes: list[dict]) -> list[dict]:
    """确认前必须说清的步骤：没有子步骤却不是叶子，或是叶子但判不了谁来做。"""
    parents = {n["parent"] for n in nodes}
    out = []
    for n in nodes:
        if n["id"] in parents:
            continue
        if not n["leaf"]:
            out.append({"id": n["id"], "title": n["title"],
                        "why": "还差：" + "、".join(CRITERIA[m] for m in n["missing"])})
        elif n["executor_kind"] == "unknown":
            out.append({"id": n["id"], "title": n["title"], "why": "还没说清谁来做"})
    return out


# ------------------------------------------------------------------ 审核
def _moderation_hit(spec: dict, db=None) -> str | None:
    """AI-DEC-047 每一层都过内容安全与金融合规，不只根节点。"""
    from app.modules.finance.compliance import scan_finance_terms
    from app.modules.task.service import machine_review

    text = " ".join(str(spec.get(k, "")) for k in ("title", "description", "deliverable", "acceptance"))
    return machine_review(text, db) or scan_finance_terms(text) or None


# ------------------------------------------------------------------ 展开
def _allocate(budget: int, specs: list[dict]) -> list[int]:
    ratios = [max(int(s.get("budget_ratio_bps", 0)), 0) for s in specs]
    total = sum(ratios)
    if total <= 0:
        ratios, total = [1] * len(specs), len(specs)
    out, allocated = [], 0
    for i, r in enumerate(ratios):
        amount = budget - allocated if i == len(ratios) - 1 else budget * r // total
        if i < len(ratios) - 1:
            allocated += amount
        out.append(amount)
    return out


def _norm(t: str) -> str:
    return "".join(t.split()).lower()


def frontier(nodes: list[dict]) -> list[dict]:
    parents = {n["parent"] for n in nodes}
    return [n for n in nodes if not n["leaf"] and not n["expanded"]
            and not n["stop_reason"] and n["id"] not in parents]


def expand(db: Session, task, nodes: list[dict], targets: list[int] | None,
           gateway, model_calls: int) -> tuple[list[dict], int, dict]:
    """展开一层（或指定的几步）。返回 (新的节点表, 新的模型调用数, 这一步的报告)。

    每一层都落盘（调用方写回）：用户可以在第二层就打断、改写，再让它接着往下拆。
    """
    nodes = [dict(n) for n in nodes]
    facts = _Facts(db)
    root = {"title": task.title, "description": task.description,
            "category": task.category, "budget_cents": task.budget_cents,
            "city": task.city or "", "task_id": task.id, "creator_id": task.creator_id}
    report = {"expanded": [], "stopped": [], "blocked": [], "unit_uses": []}
    uses_model = bool(getattr(gateway, "uses_model", False))

    if not nodes:
        target_nodes: list[dict | None] = [None]
    elif targets is None:
        target_nodes = frontier(nodes)
    else:
        target_nodes = []
        for tid in targets:
            n = _by_id(nodes, tid)
            if children_of(nodes, tid):
                raise conflict(f"「{n['title']}」已经拆过了", "already_expanded")
            target_nodes.append(n)

    for target in target_nodes:
        depth = (target["depth"] + 1) if target else 1
        budget = target["budget_cents"] if target else task.budget_cents

        def stop(reason: str):
            record_stop(reason)
            if target is None:
                raise conflict(STOP_NOTES[reason], "decompose_stopped")
            target["stop_reason"] = reason
            report["stopped"].append({"id": target["id"], "reason": reason})

        if depth > settings.DECOMPOSE_MAX_DEPTH:
            stop("max_depth")
            continue
        if len(nodes) >= settings.DECOMPOSE_MAX_NODES:
            stop("max_nodes")
            continue
        if target is not None and budget < 2 * settings.DECOMPOSE_MIN_NODE_BUDGET_CENTS:
            stop("budget_fragment")
            continue
        if uses_model and model_calls >= settings.DECOMPOSE_MAX_MODEL_CALLS:
            stop("cost_cap")
            continue

        path = []
        cur = target
        while cur is not None:
            path.insert(0, cur["title"])
            cur = _by_id(nodes, cur["parent"]) if cur["parent"] is not None else None
        res = gateway.expand(db, {
            "root": root, "path": path, "depth": depth,
            "node": None if target is None else {
                "title": target["title"], "description": target["description"],
                "category": target["category"] or task.category, "budget_cents": budget},
        })
        if res.get("model_call"):
            model_calls += 1
        specs = res["children"]

        if not specs:
            stop("template_limit" if not uses_model or res.get("fallback") else "no_progress")
            continue
        if target is not None and (len(specs) < 2 or any(
                _norm(s["title"]) == _norm(target["title"]) for s in specs)):
            stop("no_progress")
            continue
        if not _dag_ok(len(specs), [list(s.get("depends_on_idx", [])) for s in specs]):
            stop("invalid_output")
            continue
        hits = [(s["title"], _moderation_hit(s, db)) for s in specs]
        if any(h for _, h in hits):
            report["blocked"].extend(t for t, h in hits if h)
            stop("moderation")
            continue
        amounts = _allocate(budget, specs)
        floor = settings.DECOMPOSE_MIN_NODE_BUDGET_CENTS
        if target is not None and any(a < floor and a * 50 < budget for a in amounts):
            stop("budget_fragment")
            continue
        if len(nodes) + len(specs) > settings.DECOMPOSE_MAX_NODES:
            stop("max_nodes")
            continue

        base = max((n["id"] for n in nodes), default=0) + 1
        made = []
        for i, (spec, amount) in enumerate(zip(specs, amounts)):
            cat = spec.get("category", "")
            if cat and facts.cert(cat) is None:
                cat = ""  # 不在平台类目表里的类目名不采信，沿用上一级
            made.append(new_node(base + i, target["id"] if target else None, depth,
                                 {**spec, "category": cat}, amount,
                                 res["source"], bool(res.get("fallback"))))
        for i, spec in enumerate(specs):
            made[i]["depends_on"] = [base + d for d in spec.get("depends_on_idx", [])]
        nodes.extend(made)
        if target is not None:
            target.update(expanded=True, stop_reason="")
        report["expanded"].append(target["id"] if target else None)
        if res.get("unit_use"):
            # 这一层真的被采用了：调用方落盘之后再记一次单元使用（KB-083）
            report.setdefault("unit_uses", []).append(res["unit_use"])

    _reevaluate_all(facts, nodes, task.category)
    return nodes, model_calls, report


# ------------------------------------------------------------------ 编辑
def record_unit_uses(db: Session, task, report: dict) -> None:
    """KB-083 采用了经验单元的那几层，落盘之后记使用（结果会回流到单元的验证状态）。"""
    from app.modules.knowledge import units as kb_units
    from app.modules.knowledge.models import ReusableUnit

    for uid in report.get("unit_uses") or []:
        unit = db.get(ReusableUnit, uid)
        if unit is not None:
            kb_units.record_use(db, unit, "decompose", task.creator_id, task.id,
                                summary=f"分解《{task.title}》的第一层")


def edit_node(db: Session, task, nodes: list[dict], nid: int, patch: dict) -> list[dict]:
    nodes = [dict(n) for n in nodes]
    node = _by_id(nodes, nid)
    unknown = set(patch) - EDITABLE
    if unknown:
        raise bad_request(f"这些字段不能改：{'、'.join(sorted(unknown))}", "field_not_editable")
    if "executor_hint" in patch and patch["executor_hint"] not in USER_HINTS:
        raise bad_request("谁来做只能选：交给人做 / 需要资质 / 交给 AI", "invalid_executor_hint")
    if patch.get("category"):
        if _Facts(db).cert(patch["category"]) is None:
            raise bad_request(f"平台没有「{patch['category']}」这个类目", "category_not_found")
    if "title" in patch and not str(patch["title"]).strip():
        raise bad_request("步骤名称不能为空", "step_title_required")
    for k, v in patch.items():
        node[k] = v
    validate_tree(nodes, task.budget_cents)
    _reevaluate_all(_Facts(db), nodes, task.category)
    return nodes


def delete_node(nodes: list[dict], nid: int, db: Session, task) -> list[dict]:
    _by_id(nodes, nid)
    gone = _subtree_ids(nodes, nid)
    out = []
    for n in nodes:
        if n["id"] in gone:
            continue
        n = dict(n)
        n["depends_on"] = [d for d in n["depends_on"] if d not in gone]
        out.append(n)
    if not out:
        raise bad_request("至少要保留一步", "empty_items")
    # 删掉最后一个子步骤的上一级重新变回「待拆」
    parents = {n["parent"] for n in out}
    for n in out:
        if n["expanded"] and n["id"] not in parents:
            n["expanded"] = False
    _reevaluate_all(_Facts(db), out, task.category)
    return out


def nodes_from_items(db: Session, task, old: list[dict], items: list[dict]) -> list[dict]:
    """V132 之前的一层编辑接口（`PATCH /decompositions/{id}` 带 items）在树上的含义：
    只在树还只有一层时可用，按下标保留每一步的交付物、验收标准与谁来做。"""
    if any(n["depth"] > 1 for n in old):
        raise conflict("这份拆解已经展开到第二层以下，请逐步编辑", "tree_has_depth")
    old_top = children_of(old, None)
    made = []
    for i, it in enumerate(items):
        base = dict(old_top[i]) if i < len(old_top) else new_node(
            i + 1, None, 1, {"title": it.get("title", "")}, 0, "user", False)
        base.update(id=i + 1, parent=None, depth=1,
                    title=it.get("title", base["title"]),
                    description=it.get("description", base["description"]),
                    required_skills=list(it.get("required_skills", base["required_skills"])),
                    budget_cents=int(it.get("budget_cents", 0)),
                    depends_on=[d + 1 for d in (it.get("depends_on_idx") or [])],
                    expanded=False)
        for k in ("deliverable", "acceptance", "single_owner", "category", "executor_hint"):
            if k in it:
                base[k] = it[k]
        made.append(base)
    validate_tree(made, task.budget_cents)
    _reevaluate_all(_Facts(db), made, task.category)
    return made


def items_view(nodes: list[dict]) -> list[dict]:
    """给 V132 之前的客户端看的一层视图（只读派生，不是第二份数据）。"""
    top = children_of(nodes, None)
    pos = {n["id"]: i for i, n in enumerate(top)}
    return [{
        "title": n["title"], "description": n["description"],
        "required_skills": n["required_skills"], "budget_cents": n["budget_cents"],
        "depends_on_idx": [pos[d] for d in n["depends_on"] if d in pos],
        "source": n["source"],
    } for n in top]


# ------------------------------------------------------------------ 确认
def confirm(db: Session, nodes: list[dict], parent) -> tuple[list[dict], list]:
    """AI-DEC-046 只有叶子成为可发布任务；中间步骤是组织结构（草稿态容器，不独立托管）。"""
    from app.modules.task import service as task_service
    from app.modules.task.models import Task

    todo = unresolved(nodes)
    if todo:
        names = "、".join(f"「{t['title']}」（{t['why']}）" for t in todo[:3])
        more = f"等 {len(todo)} 步" if len(todo) > 3 else ""
        raise conflict(f"还有步骤没说清：{names}{more}", "tree_incomplete")
    validate_tree(nodes, parent.budget_cents)

    nodes = [dict(n) for n in nodes]
    tasks: dict[int, Task] = {}
    for n in sorted(nodes, key=lambda x: (x["depth"], x["id"])):
        up = tasks[n["parent"]] if n["parent"] is not None else parent
        t = Task(
            creator_id=parent.creator_id, parent_id=up.id,
            # 广场上看到的是单独一条任务：带上总任务的名字，别人才知道这一步属于什么
            title=f"{parent.title} - {n['title']}"[:100], description=n["description"] + (
                f"\n\n交付物：{n['deliverable']}\n验收标准：{n['acceptance']}" if n["leaf"] else ""),
            category=n["category"] or parent.category, task_type=parent.task_type,
            required_skills=n["required_skills"], budget_cents=n["budget_cents"],
            is_remote=parent.is_remote, city=parent.city, lat=parent.lat, lng=parent.lng,
            address_hint=parent.address_hint, address_exact=parent.address_exact,
        )
        db.add(t)
        db.flush()
        tasks[n["id"]] = t
        n["task_id"] = t.id
    for n in nodes:
        tasks[n["id"]].depends_on = [tasks[d].id for d in n["depends_on"]]
        db.add(tasks[n["id"]])

    def unblocked(n: dict) -> bool:
        cur = n
        while cur is not None:
            if cur["depends_on"]:
                return False
            cur = _by_id(nodes, cur["parent"]) if cur["parent"] is not None else None
        return True

    for n in nodes:
        if n["leaf"] and unblocked(n):
            task_service.transition(db, tasks[n["id"]], "published")
    return nodes, [tasks[n["id"]] for n in nodes]


def publish_unblocked_leaves(db: Session, container) -> None:
    """一个容器步骤的前置都完成了：把它下面没有前置的叶子发布出去（逐层向下）。"""
    from app.modules.task import service as task_service
    from app.modules.task.models import Task

    kids = db.query(Task).filter(Task.parent_id == container.id).all()
    status = {k.id: k.status for k in kids}
    for k in kids:
        if k.status != "draft" or not all(status.get(d) == "completed" for d in (k.depends_on or [])):
            continue
        if db.query(Task.id).filter(Task.parent_id == k.id).first():
            publish_unblocked_leaves(db, k)
        else:
            task_service.transition(db, k, "published")
