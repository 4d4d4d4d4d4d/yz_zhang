"""ORC-060~063 / VER-051 让 AI 真的参与，并且越做越好（61 号 spec）。

两条欠账各挂了三个批次：

- **AGT-053** 编排器的工具只有 `publish_task`——一个标榜「AI 驱动」的平台，
  它的 agent loop 里没有 agent。
- **VER-051** `verification_lessons` 表在写，**全仓没有任何地方读它**。
  需求原话「能够持续帮助迭代任务完成」的载体，此前只落了一半。

两条合起来才是那个闭环：AI 参与执行 → 人核验 → 结论回流 → 下次做得更好。
"""
import pytest

from app.modules.agent.runner import RunResult, set_runner
from tests.conftest import auth, make_admin, register, topup, verify_user
from tests.test_agent_execution import make_agent


class RecordingRunner:
    """记下每次收到的 system_prompt——**经验有没有真的喂进去，只能这样验**。"""

    def __init__(self, output="交付内容：已完成。", confidence_bps=9000):
        self.output, self.confidence_bps = output, confidence_bps
        self.prompts: list[str] = []
        self.raises = False

    def run(self, **kwargs):
        self.prompts.append(kwargs.get("system_prompt", ""))
        if self.raises:
            from app.modules.agent.runner import AgentUnavailable

            raise AgentUnavailable("测试注入：后端不可用")
        return RunResult(self.output, self.confidence_bps, 12)


@pytest.fixture()
def runner():
    r = RecordingRunner()
    set_runner(r)
    yield r
    set_runner(None)


def make_mission(client, owner, *, allow_agents=False, cap=60000, category="软件开发"):
    r = client.post("/api/v1/missions", json={
        "goal": "做一版接口文档", "detail": "分成大纲与正文两步",
        "category": category, "budget_cap_cents": cap, "max_iterations": 3,
        "acceptance_criteria": ["包含鉴权说明"],
        "allow_agents": allow_agents,
    }, headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()


def tick(client, owner, mission_id):
    r = client.post(f"/api/v1/missions/{mission_id}/tick", headers=auth(owner))
    assert r.status_code == 200, r.text
    return r.json()


def steps_of(client, owner, mission_id):
    return client.get(f"/api/v1/missions/{mission_id}",
                      headers=auth(owner)).json()["steps"]


# ------------------------------------------------- ORC-061 默认不派给 AI
def test_orc061_agents_are_not_used_without_explicit_permission(client, requester, runner):
    """发起人授权了「自动花钱」，不等于授权「活由 AI 做」——这是两件事。

    一个人可能很愿意让系统自动去市场上找人，同时完全不接受交付物是机器写的。
    """
    admin = make_admin(client, "13800061001")
    make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    topup(client, requester, 300000)
    m = make_mission(client, requester)          # 默认 allow_agents=False
    assert m["allow_agents"] is False

    tick(client, requester, m["id"])
    steps = steps_of(client, requester, m["id"])
    assert steps, "没有分发任何步骤"
    assert all(s["agent_user_id"] is None for s in steps), "没授权却把活派给了 AI"
    assert runner.prompts == [], "没授权却执行了 agent"
    # 任务照常挂在广场上等人接
    for s in steps:
        task = client.get(f"/api/v1/tasks/{s['task_id']}", headers=auth(requester)).json()
        assert task["status"] == "published"


# ------------------------------------------------- ORC-060 授权后走完整链路
def test_orc060_agent_step_goes_through_the_whole_contract_chain(client, requester, runner):
    """照常建任务、照常签约托管，只是执行方是 agent。

    与 AGT-020 同一条：**不开后门**。托管/评审/纠纷/毛利全都以 task_id、
    user_id 为键，另开一条「直接调模型」的路等于把它们各写第二遍。
    """
    admin = make_admin(client, "13800061002")
    agent_id = make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    topup(client, requester, 300000)
    m = make_mission(client, requester, allow_agents=True)

    tick(client, requester, m["id"])
    steps = steps_of(client, requester, m["id"])
    agent_steps = [s for s in steps if s["agent_user_id"] == agent_id]
    assert agent_steps, "开了授权却没有任何一步派给 AI"

    for s in agent_steps:
        task = client.get(f"/api/v1/tasks/{s['task_id']}", headers=auth(requester)).json()
        # 成功执行 → V81 的平台代交付把它推到待验收
        assert task["status"] == "pending_acceptance", task["status"]
        contract = client.get(f"/api/v1/contracts/by-task/{s['task_id']}",
                              headers=auth(requester)).json()
        assert contract["status"] == "funded", "托管没走"
        assert "AI 执行声明" in contract["terms"], "合同里没有责任主体声明"
    assert runner.prompts, "agent 没有真的被执行"


def test_orc060_eligibility_gates_still_apply(client, requester, runner):
    """类目不命中的 agent 不会被派单：AGT-010/011/012 三道闸门不因编排而放松。"""
    admin = make_admin(client, "13800061003")
    make_agent(client, admin, name="保洁助理", domains=["保洁"])
    topup(client, requester, 300000)
    m = make_mission(client, requester, allow_agents=True, category="软件开发")

    tick(client, requester, m["id"])
    steps = steps_of(client, requester, m["id"])
    assert all(s["agent_user_id"] is None for s in steps), "把软件开发的活派给了保洁助理"


# --------------------------------------- ORC-062 AI 做不成 → 全额退款转人工
def test_orc062_failed_agent_run_cancels_and_refunds(client, requester, runner):
    """AI 没做成，钱全额退回，步骤转失败等修复步重发给人。

    取消以**执行方**名义发起：以发布方名义会按规则补偿执行者 20%——
    AI 搞砸了还收补偿金，那是把规则套错了对象。
    """
    admin = make_admin(client, "13800061004")
    agent_id = make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    topup(client, requester, 300000)
    before = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]

    runner.raises = True                      # 后端挂了 → run=failed
    m = make_mission(client, requester, allow_agents=True)
    tick(client, requester, m["id"])

    steps = steps_of(client, requester, m["id"])
    agent_steps = [s for s in steps if s["agent_user_id"] == agent_id]
    assert agent_steps, "没有派给 AI，这条测试什么也没验"
    for s in agent_steps:
        assert s["status"] == "failed"
        assert "改由人工承接" in s["observation"]
        task = client.get(f"/api/v1/tasks/{s['task_id']}", headers=auth(requester)).json()
        assert task["status"] == "cancelled"

    after = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    assert after == before, f"钱没有全额退回：{before} → {after}"
    # 五条资金不变量仍然成立
    assert client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()["ok"] is True


def test_orc062_remedy_steps_are_never_handed_to_agents_again(client, requester, runner):
    """同一形态失败过一次就换人做——修复步不再派给 AI。"""
    admin = make_admin(client, "13800061005")
    agent_id = make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    topup(client, requester, 300000)
    runner.raises = True
    m = make_mission(client, requester, allow_agents=True)
    tick(client, requester, m["id"])          # 首轮：派 AI → 失败
    tick(client, requester, m["id"])          # 次轮：生成修复步并分发

    steps = steps_of(client, requester, m["id"])
    remedies = [s for s in steps if s["is_remedy"]]
    assert remedies, "没有生成修复步"
    assert all(s["agent_user_id"] is None for s in remedies), "修复步又派给了同一个 AI"
    assert all(s["agent_user_id"] != agent_id for s in remedies)


# ------------------------------------------------------ VER-051 经验回流
def _record_lesson(category, outcome, title, reason, revision=""):
    from app.core.db import SessionLocal
    from app.modules.verify.models import VerificationLesson

    with SessionLocal() as db:
        row = VerificationLesson(category=category, outcome=outcome, task_title=title,
                                 criteria=["包含鉴权说明"], reason=reason,
                                 revision_summary=revision)
        db.add(row)
        db.commit()
        return row.id


def test_ver051_lessons_reach_the_agent_prompt(client, requester, runner):
    """这张表从 V74 起一直在写，而全仓没有任何地方读它。"""
    admin = make_admin(client, "13800061010")
    agent_id = make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    lesson_id = _record_lesson("软件开发", "revised", "写一版接口文档",
                               "缺少鉴权失败时的错误码说明", "补上 401/403 的语义区别")
    topup(client, requester, 300000)
    m = make_mission(client, requester, allow_agents=True)
    tick(client, requester, m["id"])

    assert runner.prompts, "agent 没被执行"
    prompt = runner.prompts[-1]
    assert "人工核验指出过的问题" in prompt
    assert "缺少鉴权失败时的错误码说明" in prompt
    assert "补上 401/403 的语义区别" in prompt

    # ORC-063 喂了什么必须落库，否则「经验回流」是一句无法验证的话
    from app.core.db import SessionLocal
    from app.modules.agent.models import AgentRun

    with SessionLocal() as db:
        run = db.query(AgentRun).filter(AgentRun.agent_user_id == agent_id).first()
        assert run and lesson_id in (run.lessons_used or [])


def test_ver051_approved_lessons_and_other_categories_stay_out(client, requester, runner):
    """`approved` 没有信息量（「这次做对了」不指导下一次），
    跨类目的只会稀释真正相关的内容——而提示词长度是有成本的。"""
    admin = make_admin(client, "13800061011")
    make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    _record_lesson("软件开发", "approved", "上一单", "写得很好，没有问题")
    _record_lesson("保洁", "rejected", "保洁单", "厨房地面未清理")
    topup(client, requester, 300000)
    m = make_mission(client, requester, allow_agents=True)
    tick(client, requester, m["id"])

    prompt = runner.prompts[-1]
    assert "写得很好" not in prompt, "approved 的结论进了提示词"
    assert "厨房地面未清理" not in prompt, "别的类目的结论进了提示词"


def test_ver051_prompt_does_not_grow_without_bound(client, requester, runner):
    """一个会随数据增长而变坏的机制是定时炸弹，不是功能。"""
    from app.modules.verify import service as verify_service

    admin = make_admin(client, "13800061012")
    make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    for i in range(20):
        _record_lesson("软件开发", "rejected", f"历史任务 {i}", "理由" * 500)
    topup(client, requester, 300000)
    m = make_mission(client, requester, allow_agents=True)
    tick(client, requester, m["id"])

    prompt = runner.prompts[-1]
    assert prompt.count("被判定不通过") <= verify_service.LESSON_LIMIT
    assert len(prompt) < 6000, f"提示词已经 {len(prompt)} 字，会随经验条数一直涨"


def test_ver051_no_lessons_means_no_empty_heading(client, requester, runner):
    """没有经验时不产生一段空的「经验」抬头——那会让模型以为自己漏看了什么。"""
    admin = make_admin(client, "13800061013")
    make_agent(client, admin, domains=["软件开发"], max_task_budget_cents=100000)
    topup(client, requester, 300000)
    m = make_mission(client, requester, allow_agents=True)
    tick(client, requester, m["id"])
    assert "人工核验指出过的问题" not in runner.prompts[-1]
