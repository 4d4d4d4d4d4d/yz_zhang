"""AGT 平台自有 Agent 执行层（48 号 spec）。

这一批的断言围绕三条判断：

1. **agent 复用 User 体系**——所以托管/纠纷/信用/账本一行不改就对它生效。
   测试要真的走完整合约链路，而不是只测 agent 模块自己。
2. **不让 agent 给自己判卷**——置信度是自报的，所以客观判据必须由平台执行，
   且 agent 自报「很有信心」不能覆盖判据不通过。
3. **agent 会去接它接不了的活**——如果不拦。所以到场任务、越界类目、
   超额预算三条闸门各有一条测试。
"""
import pytest

from app.modules.agent import service as agent_service
from app.modules.agent.runner import AgentUnavailable, RunResult, set_runner
from app.modules.wallet import service as wallet
from tests.conftest import auth, make_admin, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task


class FakeRunner:
    """可控的执行后端。测试要能分别造出「高置信度好输出」「低置信度」
    「后端挂了」三种结局。"""

    def __init__(self, output="交付内容：已完成。", confidence_bps=9000,
                 cost_cents=12, raises=False):
        self.output, self.confidence_bps = output, confidence_bps
        self.cost_cents, self.raises = cost_cents, raises
        self.calls = 0

    def run(self, **kwargs):
        self.calls += 1
        if self.raises:
            raise AgentUnavailable("测试注入：后端不可用")
        return RunResult(self.output, self.confidence_bps, self.cost_cents)


@pytest.fixture()
def runner():
    r = FakeRunner()
    set_runner(r)
    yield r
    set_runner(None)


def make_agent(client, admin, **over):
    body = {
        "name": over.pop("name", "开发助理"),
        "domains": over.pop("domains", ["软件开发"]),
        "model": "test-model",
        "cost_per_run_cents": 10,
        "max_task_budget_cents": 50000,
        "confidence_threshold_bps": 7000,
        **over,
    }
    r = client.post("/api/v1/admin/agents", json=body, headers=auth(admin))
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def remote_task(client, requester, **over):
    """agent 能接的任务：远程 + 类目命中 + 预算不超限。"""
    defaults = {"category": "软件开发", "is_remote": True, "budget_cents": 20000}
    return publish_task(client, requester, **{**defaults, **over})


# ---------------------------------------------------------- AGT-010/011/012 准入
def test_agt010_agent_cannot_take_onsite_tasks(client, requester, runner):
    """**排第一位的闸门**：平台上大量保洁/跑腿同样有类目、有预算、在招募中。
    不拦的话 agent 会报名一个上门保洁单，然后交付一段文字。"""
    admin = make_admin(client, "13900000010")
    agent_id = make_agent(client, admin, domains=["保洁"])
    task = publish_task(client, requester, category="保洁", is_remote=False, budget_cents=20000)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    assert r.status_code == 400
    assert "到场" in r.json()["detail"]["message"]


def test_agt011_category_must_be_in_domains(client, requester, runner):
    admin = make_admin(client, "13900000011")
    agent_id = make_agent(client, admin, domains=["软件开发"])
    task = publish_task(client, requester, category="设计", is_remote=True, budget_cents=20000)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent_not_eligible"


def test_agt012_budget_ceiling_is_enforced(client, requester, runner):
    """赔付能力上限：搞砸 200 元的文案认栽，搞砸 5 万的项目不行。"""
    admin = make_admin(client, "13900000012")
    agent_id = make_agent(client, admin, max_task_budget_cents=10000)
    task = remote_task(client, requester, budget_cents=30000)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    assert r.status_code == 400
    assert "上限" in r.json()["detail"]["message"]


def test_eligible_agents_explains_why_not(client, requester, runner):
    """只说「没有可用助理」没有意义——发布方不知道该改什么。"""
    admin = make_admin(client, "13900000013")
    make_agent(client, admin, domains=["保洁"])
    task = remote_task(client, requester)
    rows = client.get(f"/api/v1/tasks/{task['id']}/eligible-agents",
                      headers=auth(requester)).json()
    assert rows and rows[0]["eligible"] is False
    assert rows[0]["reason"]          # 必须给出理由，不能是空字符串


# ------------------------------------------------------------------ AGT-020 全链路
def test_agt020_agent_goes_through_the_whole_contract_flow(client, requester, runner):
    """agent 走完整合约链路，不开后门。这条同时验证了架构判断：
    因为 agent 是 User，托管/放款/评价一行都不用改。"""
    admin = make_admin(client, "13900000020")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester)

    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    assert r.status_code == 201
    app_id = r.json()["id"]
    r = client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester))
    assert r.status_code == 200, r.text
    cid = r.json()["contract_id"]

    # AGT-017 责任主体写进合同条款
    terms = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()["terms"]
    assert "AI 执行声明" in terms and "平台为本任务履约的责任主体" in terms

    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))

    r = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "succeeded"
    assert runner.calls == 1


# ------------------------------------------------------------- AGT-013 置信度闸门
def test_agt013_low_confidence_escalates_and_blocks_delivery(client, requester, runner):
    admin = make_admin(client, "13900000030")
    agent_id = make_agent(client, admin, confidence_threshold_bps=8000)
    topup(client, requester, 100000)
    task = remote_task(client, requester)
    _accept_and_fund(client, requester, task, agent_id)

    runner.confidence_bps = 5000
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester)).json()
    assert run["status"] == "escalated"

    runs = client.get(f"/api/v1/tasks/{task['id']}/agent-runs", headers=auth(requester)).json()
    assert "人工核验" in runs["delivery_block"]


def test_agt013_escalation_is_not_a_dead_end(client, requester, runner):
    """升级后不能把钱卡住：发布方仍可取消合约走既有退款链路。
    建一道没有出口的闸门，比不建更坏。"""
    admin = make_admin(client, "13900000031")
    agent_id = make_agent(client, admin, confidence_threshold_bps=9500)
    topup(client, requester, 100000)
    task = remote_task(client, requester)
    _accept_and_fund(client, requester, task, agent_id)
    runner.confidence_bps = 1000
    client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))

    before = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    r = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(requester))
    assert r.status_code == 200, r.text
    after = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    assert after > before, "升级后取消必须能把托管的钱退回来"


def test_agt013_missing_confidence_is_treated_as_lowest(client, requester, runner):
    """拿不到置信度按**最低**处理（必然升级），不按最高——
    代价落在别人身上时往保守一侧倒。"""
    admin = make_admin(client, "13900000032")
    agent_id = make_agent(client, admin, confidence_threshold_bps=1)
    topup(client, requester, 100000)
    task = remote_task(client, requester)
    _accept_and_fund(client, requester, task, agent_id)
    runner.confidence_bps = None
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester)).json()
    assert run["confidence_bps"] == 0
    assert run["status"] == "escalated"


# --------------------------------------------------------- AGT-030/031 客观判据
def test_agt030_platform_judges_not_the_agent(client, requester, runner):
    """**这条是整个验收机制成立的前提**：agent 自报 99% 置信度，
    但平台判据不通过 → 仍然失败。让执行者自己判卷等于没有验收。"""
    admin = make_admin(client, "13900000040")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester, acceptance_criteria=[
        {"text": "必须包含免责声明", "kind": "auto",
         "check": {"op": "contains", "value": "免责声明"}},
    ])
    _accept_and_fund(client, requester, task, agent_id)

    runner.confidence_bps = 9900          # agent 说它很有信心
    runner.output = "写好了，很棒。"       # 但判据要的词不在里面
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester)).json()
    assert run["status"] == "failed"
    assert "验收判据未通过" in run["error"]
    auto = [c for c in run["criteria_results"] if c["kind"] == "auto"]
    assert auto and auto[0]["passed"] is False


def test_agt031_failed_criteria_block_delivery(client, requester, runner):
    admin = make_admin(client, "13900000041")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester, acceptance_criteria=[
        {"text": "输出必须是 JSON", "kind": "auto", "check": {"op": "is_json", "value": None}},
    ])
    _accept_and_fund(client, requester, task, agent_id)
    runner.output = "这不是 JSON"
    client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))
    runs = client.get(f"/api/v1/tasks/{task['id']}/agent-runs", headers=auth(requester)).json()
    assert "执行失败" in runs["delivery_block"]


def test_agt031_manual_criteria_do_not_block_but_are_recorded(client, requester, runner):
    """manual 项不阻断交付，但要原样带进验收界面，且**不能猜**：
    「还没人判」与「判过没通过」必须分得开，否则不知道该找谁。"""
    admin = make_admin(client, "13900000042")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester, acceptance_criteria=[
        {"text": "文风符合品牌调性", "kind": "manual"},
    ])
    _accept_and_fund(client, requester, task, agent_id)
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester)).json()
    assert run["status"] == "succeeded"
    assert run["criteria_results"][0]["passed"] is None


def test_agt030_bad_criteria_are_rejected_at_publish_time(client, requester):
    """判据在**发布环节**校验：写错的判据要在开工前发现，
    而不是等 agent 跑完才报错。"""
    r = client.post("/api/v1/tasks", json={
        "title": "写一篇稿子", "category": "软件开发", "budget_cents": 10000, "is_remote": True,
        "acceptance_criteria": [{"text": "随便", "kind": "auto",
                                 "check": {"op": "eval", "value": "1"}}],
    }, headers=auth(requester))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "unsupported_check"


def test_agt030_bad_regex_is_rejected(client, requester):
    r = client.post("/api/v1/tasks", json={
        "title": "写一篇稿子", "category": "软件开发", "budget_cents": 10000, "is_remote": True,
        "acceptance_criteria": [{"text": "匹配", "kind": "auto",
                                 "check": {"op": "regex", "value": "([unclosed"}}],
    }, headers=auth(requester))
    assert r.status_code == 400


# ------------------------------------------------------------ AGT-014/015 并发与失败
def test_agt014_only_one_run_at_a_time(client, requester, runner):
    """重复触发不重复扣费、不产生两份交付。"""
    admin = make_admin(client, "13900000050")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester)
    _accept_and_fund(client, requester, task, agent_id)

    from app.core.db import SessionLocal
    from app.modules.agent.models import AgentRun

    # 直接造一条 running 的 run，模拟「上一次还在跑」
    with SessionLocal() as db:
        db.add(AgentRun(agent_user_id=agent_id, task_id=task["id"], status="running"))
        db.commit()
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "agent_run_in_progress"
    assert runner.calls == 0, "并发闸没拦住，模型被又调了一次（这是要花钱的）"


def test_agt015_backend_failure_does_not_fake_success(client, requester, runner):
    """与任务分解故意不同：分解失败降级到模板是对的，交付物降级成模板
    就是拿废品换钱。所以这里**不降级**。"""
    admin = make_admin(client, "13900000051")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester)
    _accept_and_fund(client, requester, task, agent_id)

    runner.raises = True
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester)).json()
    assert run["status"] == "failed"
    assert run["output"] == "", "失败时不许产出任何交付内容"
    runs = client.get(f"/api/v1/tasks/{task['id']}/agent-runs", headers=auth(requester)).json()
    assert "执行失败" in runs["delivery_block"]


def test_local_runner_cannot_look_like_it_works():
    """缺省实现不假装能干活：置信度恒为 0，必然被阈值拦成 escalated。"""
    from app.modules.agent.runner import LocalRunner

    result = LocalRunner().run(model="", system_prompt="", title="t",
                               description="", category="c")
    assert result.confidence_bps == 0
    assert LocalRunner.production_ready is False


# ------------------------------------------------------------------ AGT-016 成本
def test_agt016_every_successful_run_records_its_cost(client, requester, runner):
    """没有这个数字，「让 agent 接单」是赚是赔谁也说不清。"""
    admin = make_admin(client, "13900000060")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester)
    _accept_and_fund(client, requester, task, agent_id)
    client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))

    rows = client.get("/api/v1/admin/agents", headers=auth(admin)).json()
    row = next(r for r in rows if r["user_id"] == agent_id)
    assert row["cost_cents"] > 0
    assert row["margin_is_estimated"] is True, "估算的毛利必须标明是估算"


def test_agt016_unfinished_tasks_do_not_count_as_revenue(client, requester, runner):
    """跑了但没验收的不算收入，而成本已经付了——把未完成算成收入，
    就是把亏损记成盈利。"""
    admin = make_admin(client, "13900000061")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester)
    _accept_and_fund(client, requester, task, agent_id)
    client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))

    rows = client.get("/api/v1/admin/agents", headers=auth(admin)).json()
    row = next(r for r in rows if r["user_id"] == agent_id)
    assert row["revenue_cents"] == 0
    assert row["margin_cents"] < 0


# ------------------------------------------------------------- AGT-018 推荐池
def test_agt018_agents_do_not_pollute_the_normal_recommendation_pool(client, requester, runner):
    """不排除的话，每一个保洁单的推荐列表里都会出现 AI 助理。"""
    admin = make_admin(client, "13900000070")
    agent_id = make_agent(client, admin, domains=["保洁"])
    worker = register(client, "13900000071", "真人保洁")
    verify_user(client, worker, name="李四")
    task = publish_task(client, requester, category="保洁", is_remote=False)
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations",
                      headers=auth(requester)).json()
    ids = {r["user_id"] for r in recs}
    assert agent_id not in ids
    assert worker["id"] in ids, "把真人也排掉了，说明排除条件写过头了"


# -------------------------------------------------------- AGT-019 收入归集与不变量
def test_agt019_earnings_are_swept_to_the_platform_account(client, requester, runner):
    admin = make_admin(client, "13900000080")
    agent_id = make_agent(client, admin)
    topup(client, requester, 100000)
    task = remote_task(client, requester)
    _accept_and_fund(client, requester, task, agent_id)
    client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))

    from app.core.db import SessionLocal

    # agent 是平台自有的，没有登录态（也不该有），所以交付与验收走服务层
    with SessionLocal() as db:
        from app.modules.task.models import Task
        from app.modules.task.router import _complete_task

        from app.modules.task import service as task_service

        t = db.get(Task, task["id"])
        t.delivered_at = t.created_at
        task_service.transition(db, t, "pending_acceptance")
        _complete_task(db, t)
        db.commit()

    with SessionLocal() as db:
        agent_acct = wallet.get_or_create(db, agent_id)
        platform = wallet.get_or_create(db, wallet.PLATFORM_USER_ID)
        assert agent_acct.available_cents == 0, "agent 钱包应被归集清空"
        assert platform.available_cents > 0

    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert r["ok"] is True, f"归集打破了资金不变量：{r['mismatches']}"


def _accept_and_fund(client, requester, task, agent_id):
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    return cid


# ------------------------------------------- 检视中改掉的一处：对账不变量的手抄清单
def test_platform_invariant_is_self_maintaining(client, requester):
    """平台账户不变量原本是**五组科目手抄相加**，加一种新科目就误报。

    本批加 `agent_payout_*` 时它立刻报了「平台佣金不符」——而问题不在
    agent，在那份手抄的清单。改成按账户求和后，新科目自动纳入。
    这条测试造一笔平台账户上的转账（补贴），断言对账仍然平。
    """
    admin = make_admin(client, "13900000090")
    topup(client, requester, 50000)
    # 给平台账户注资后再补贴出去：两种都动平台余额，且科目不同
    client.post("/api/v1/admin/subsidy-pool/fund", json={"amount_cents": 30000},
                headers=auth(admin))
    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert r["ok"] is True, r["mismatches"]


def test_platform_invariant_still_catches_tampering(client, requester):
    """不能因为「自维护」就变弱：直接改余额而不落流水，必须仍然被抓到。"""
    import sqlalchemy as sa

    from app.core.db import SessionLocal, engine
    from app.modules.wallet.service import PLATFORM_USER_ID

    admin = make_admin(client, "13900000091")
    topup(client, requester, 10000)
    # 建账户走 ORM：裸 INSERT 要手写全部非空列，漏一列就被 OR IGNORE 静默吞掉
    # （而且 OR IGNORE 是 SQLite 方言，Postgres 上跑不了——V72 的教训）
    with SessionLocal() as db:
        wallet.get_or_create(db, PLATFORM_USER_ID)
        db.commit()
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE wallet_accounts SET available_cents = available_cents + 777 "
                    "WHERE user_id = :id"),
            {"id": PLATFORM_USER_ID},
        )
    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert r["ok"] is False
    assert any(m["invariant"] == "platform_fee_backing" for m in r["mismatches"])


# ------------------------- CONC-020 连接池跨请求的过期读快照（本批查出的真实缺陷）
def test_conc020_sqlite_must_not_pool_connections():
    """SQLite 必须用 NullPool，否则连接池会跨请求留下**过期的 WAL 读快照**。

    怎么查出来的：全链路验收里「注销后登录态失效」间歇性变红。注销确实提交了
    （库里 users.is_deleted=1、login_sessions.revoked=1），但紧接着的
    `GET /users/me` 仍然 200——在鉴权处打点，看到它读到的是
    is_deleted=False / revoked=False，即**提交之前的快照**。
    换 NullPool 后同一条链路稳定 47/47，打点也变成 True/True。

    后果不是「一条验收项偶尔红」：它意味着在 SQLite 下写完立刻读不保证读到
    自己刚写的东西，**一个已吊销的会话能在一段时间里继续通过鉴权**。

    为什么这条测试断言的是**配置**而不是行为：TestClient 是单线程、连接不复用，
    这个缺陷在 pytest 里**根本复现不出来**（改坏之前 703 个测试全绿）。
    写一条复现不了的行为测试，就是造一个永远不会红的闸门——
    那比没有闸门更坏。真正的复现在 `scripts/acceptance.py` 打真实服务那条路上。
    所以这里钉配置：谁把 NullPool 去掉，这条立刻红。
    """
    from sqlalchemy.pool import NullPool

    from app.core.db import engine

    if engine.dialect.name != "sqlite":
        pytest.skip("只约束 SQLite；Postgres 有真正的 MVCC，连接池没有这个问题")
    assert isinstance(engine.pool, NullPool), (
        "SQLite 引擎又用回了连接池：跨请求的过期读快照会让已吊销的会话继续有效"
    )


def test_conc020_read_your_own_write_across_requests(client, requester):
    """上一个请求写的，下一个请求必须读得到。

    如上所述，这条在 TestClient 下抓不到那个缺陷（连接不复用）。
    留着它是因为它便宜、且描述的是真正要守的不变量本身。
    """
    for i in range(12):
        nickname = f"改名{i}"
        client.patch("/api/v1/users/me", json={"nickname": nickname}, headers=auth(requester))
        got = client.get("/api/v1/users/me", headers=auth(requester)).json()["nickname"]
        assert got == nickname, f"第 {i} 轮读到过期数据：期望 {nickname}，实际 {got}"
