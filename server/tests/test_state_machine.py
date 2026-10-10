"""03.A 任务状态机 P0 不变量：白名单穷举 + 非法流转必拒 + 终态无出边。

直接针对 TRANSITIONS 表与 transition() 做穷举，把「必须严格约束流转」钉成契约。
"""
import pytest

from app.core.db import SessionLocal
from app.modules.task.models import TASK_STATUSES, TRANSITIONS, Task
from app.modules.task.service import transition


# ---------- 结构不变量（纯数据，无副作用） ----------
def test_transition_table_references_only_valid_states():
    valid = set(TASK_STATUSES)
    for src, targets in TRANSITIONS.items():
        assert src in valid, f"源状态非法：{src}"
        for t in targets:
            assert t in valid, f"目标状态非法：{src}->{t}"


def test_every_status_has_a_transition_entry():
    # 每个状态都必须在表中显式声明（哪怕是空集终态），避免遗漏导致的隐式行为
    for s in TASK_STATUSES:
        assert s in TRANSITIONS, f"状态 {s} 未在流转表声明"


def test_terminal_states_have_no_outgoing():
    assert TRANSITIONS["completed"] == set()
    assert TRANSITIONS["cancelled"] == set()


def test_no_self_loops():
    for src, targets in TRANSITIONS.items():
        assert src not in targets, f"存在自环：{src}->{src}"


# ---------- 行为不变量：穷举每个 (from,to) 组合 ----------
# 会触发事件副作用的目标状态（放款/结项/退款等），穷举时跳过其副作用只验流转判定
_SIDE_EFFECT_TARGETS = {"completed", "cancelled", "disputed", "matched",
                        "pending_acceptance", "in_progress"}


@pytest.mark.parametrize("src", list(TRANSITIONS.keys()))
def test_illegal_transitions_all_rejected(client, src):
    """从每个源状态，穷举所有非白名单目标，全部必须被 transition() 拒绝。"""
    allowed = TRANSITIONS[src]
    illegal = [s for s in TASK_STATUSES if s != src and s not in allowed]
    with SessionLocal() as db:
        for target in illegal:
            task = Task(creator_id=1, title="状态机探针", category="保洁",
                        budget_cents=1000, status=src)
            db.add(task)
            db.flush()
            with pytest.raises(Exception) as exc:
                transition(db, task, target)
            # 必须是 invalid_transition，而非其它错误
            detail = getattr(exc.value, "detail", {})
            assert isinstance(detail, dict) and detail.get("code") == "invalid_transition", \
                f"{src}->{target} 未被正确拒绝：{detail}"
            db.rollback()


def test_legal_transition_from_draft_allowed(client):
    """合法流转应放行并写入新状态（draft->published 无资金副作用）。"""
    with SessionLocal() as db:
        task = Task(creator_id=1, title="合法流转", category="保洁",
                    budget_cents=1000, status="draft")
        db.add(task)
        db.flush()
        transition(db, task, "published")
        assert task.status == "published"
