"""VER 人类核验闭环 + ESCA 争议升级阶梯（49 号 spec）。

这一批补 V73 留下的 AGT-050：`escalated` 当时只做到「拦住 + 可退款」，
没有接到人类专家。需求那句「agent 无法完成或者需要人类专家核验」，
核心是后半句——不是换个人重做，是**让人来判 AI 做得对不对**。
"""
import pytest

from app.modules.agent.runner import RunResult, set_runner
from app.modules.verify import service as verify_service
from app.modules.wallet import service as wallet
from tests.conftest import JOB_HEADERS, auth, make_admin, register, topup, verify_user
from tests.test_agent_execution import FakeRunner, make_agent, remote_task
from tests.test_task_flow import match_and_fund, publish_task


@pytest.fixture()
def runner():
    r = FakeRunner()
    set_runner(r)
    yield r
    set_runner(None)


def escalated_task(client, requester, admin, runner, agent_max_budget=50000,
                   expect="escalated", **task_over):
    """造一个「agent 跑了但没通过」的任务。

    `expect` 默认是 `escalated`（置信度不足）。带 auto 判据且判据不过时，
    run 会是 `failed`——**判据失败优先于置信度**，这是对的：
    客观判据不过就是不过，agent 自报多少信心都不改变这一点。
    两种都该能转人工核验。
    """
    agent_id = make_agent(client, admin, confidence_threshold_bps=9000,
                          max_task_budget_cents=agent_max_budget)
    topup(client, requester, 200000)
    task = remote_task(client, requester, **task_over)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    app_id = r.json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    runner.confidence_bps = 4000          # 低于阈值 → escalated
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run",
                      headers=auth(requester)).json()
    assert run["status"] == expect, run
    return task, agent_id


def make_verifier(client, phone, category="软件开发", nickname="核验人"):
    """造一个有资格的核验人：实名 + 该类目有完成记录。"""
    u = register(client, phone, nickname)
    verify_user(client, u, name="核验")
    other = register(client, phone[:-1] + "9", "临时发布方")
    verify_user(client, other, name="临时")
    topup(client, other, 100000)
    task = publish_task(client, other, category=category, is_remote=True, budget_cents=10000)
    match_and_fund(client, other, u, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(u))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(other))
    return u


# ------------------------------------------------------------- VER-002 谁付这笔钱
def test_ver002_escalation_is_paid_by_the_platform(client, requester, runner):
    """**平台自有 agent 没把握，是平台的问题。**

    让发布方为 AI 的不确定性买单，等于把技术不成熟的成本转嫁给用户。
    这条有直接的经济后果：置信度阈值调得越松，平台自己掏的核验费越多——
    这正是它该有的激励。
    """
    admin = make_admin(client, "13800001000")
    task, _ = escalated_task(client, requester, admin, runner)
    before = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    after = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]

    assert order["trigger"] == "escalation"
    assert order["payer_id"] == wallet.PLATFORM_USER_ID
    assert after == before, "升级触发的核验不该从发布方扣钱"


def test_ver002_voluntary_verification_is_paid_by_the_requester(client, requester, runner):
    """发布方主动核验一个**已成功**的 run：这是他额外买的一份确定性，他付。"""
    admin = make_admin(client, "13800001001")
    agent_id = make_agent(client, admin)
    topup(client, requester, 200000)
    task = remote_task(client, requester)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    cid = client.post(f"/api/v1/applications/{r.json()['id']}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run",
                      headers=auth(requester)).json()
    assert run["status"] == "succeeded"

    before = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    after = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    assert order["trigger"] == "requested"
    assert order["payer_id"] == requester["id"]
    assert before - after == order["fee_cents"]


def test_ver000_verification_is_priced_as_review_not_redo(client, requester, runner):
    """核验是「看一遍」不是「重做」。按重做收费，发布方就为 AI 的不确定性
    付了两次全价，这个产品立刻不成立。"""
    admin = make_admin(client, "13800001002")
    task, _ = escalated_task(client, requester, admin, runner, budget_cents=100000,
                             agent_max_budget=200000)
    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    assert order["fee_cents"] < 100000 // 3, "核验费接近原价，说明按重做在收费"
    assert order["fee_cents"] >= verify_service.FEE_MIN_CENTS


# ------------------------------------------------------------ VER-020/021 核验人资格
def test_ver020_an_agent_cannot_be_a_verifier(client, requester, runner):
    """**让 AI 核验 AI 的产出，是把同一个不确定性叠两遍，不是降低它。**

    整条升级链路的价值就建立在「最后有一个人负责」上，
    一旦允许 agent 核验，升级就变成原地打转。
    """
    from app.core.db import SessionLocal
    from app.modules.account.models import User
    from app.modules.task.models import Task
    from app.modules.verify.models import VerificationOrder

    admin = make_admin(client, "13800001010")
    task, agent_id = escalated_task(client, requester, admin, runner)
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    # agent 没有登录态，所以直接问准入函数——这正是它该被拦住的地方
    with SessionLocal() as db:
        agent_user = db.get(User, agent_id)
        block = verify_service.verifier_block(
            db, db.get(Task, task["id"]), db.get(VerificationOrder, order_id), agent_user,
        )
    assert "AI 助理不能担任核验人" in block


def test_ver021_parties_to_the_task_cannot_verify_it(client, requester, runner):
    """利益冲突不靠自觉。"""
    admin = make_admin(client, "13800001011")
    task, _ = escalated_task(client, requester, admin, runner)
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    r = client.post(f"/api/v1/verification-orders/{order_id}/claim", headers=auth(requester))
    assert r.status_code == 403
    assert "当事人" in r.json()["detail"]["message"]


def test_ver021_needs_a_completion_record_in_that_category(client, requester, runner):
    admin = make_admin(client, "13800001012")
    task, _ = escalated_task(client, requester, admin, runner)
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    outsider = register(client, "13800001013", "没干过这类活")
    verify_user(client, outsider, name="外人")
    r = client.post(f"/api/v1/verification-orders/{order_id}/claim", headers=auth(outsider))
    assert r.status_code == 403
    assert "完成记录" in r.json()["detail"]["message"]


def test_open_orders_explain_why_not_claimable(client, requester, runner):
    """只显示空列表的话，核验人不知道是资格不够还是真没单。"""
    admin = make_admin(client, "13800001014")
    task, _ = escalated_task(client, requester, admin, runner)
    client.post(f"/api/v1/tasks/{task['id']}/verification", headers=auth(requester))
    outsider = register(client, "13800001015", "路人")
    verify_user(client, outsider, name="路人")
    rows = client.get("/api/v1/verification-orders", headers=auth(outsider)).json()
    assert rows and rows[0]["claimable"] is False and rows[0]["reason"]


# --------------------------------------------------------- VER-022/030 结论与出口
def test_ver022_approved_unblocks_delivery(client, requester, runner):
    """这就是 AGT-050 说的那个出口：升级不再是死路。"""
    admin = make_admin(client, "13800001020")
    task, _ = escalated_task(client, requester, admin, runner)
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    runs = client.get(f"/api/v1/tasks/{task['id']}/agent-runs", headers=auth(requester)).json()
    assert runs["delivery_block"], "核验前应当是被挡住的"

    v = make_verifier(client, "13800001021")
    client.post(f"/api/v1/verification-orders/{order_id}/claim", headers=auth(v))
    r = client.post(f"/api/v1/verification-orders/{order_id}/outcome",
                    json={"outcome": "approved", "comment": "产出可用"}, headers=auth(v))
    assert r.status_code == 200 and r.json()["unblocked"] is True

    runs = client.get(f"/api/v1/tasks/{task['id']}/agent-runs", headers=auth(requester)).json()
    assert runs["delivery_block"] == "", "核验通过后闸门应当解除"


def test_ver022_rejected_does_not_unblock(client, requester, runner):
    admin = make_admin(client, "13800001022")
    task, _ = escalated_task(client, requester, admin, runner)
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    v = make_verifier(client, "13800001023")
    client.post(f"/api/v1/verification-orders/{order_id}/claim", headers=auth(v))
    r = client.post(f"/api/v1/verification-orders/{order_id}/outcome",
                    json={"outcome": "rejected", "comment": "完全不可用"}, headers=auth(v))
    assert r.json()["unblocked"] is False
    runs = client.get(f"/api/v1/tasks/{task['id']}/agent-runs", headers=auth(requester)).json()
    assert runs["delivery_block"], "被推翻却解除了闸门"


def test_ver030_revision_must_still_pass_the_platform_criteria(client, requester, runner):
    """**人工核验是加上去的一道，不是用来豁免原有那道的。**

    不重跑判据就有个洞：判据拦住了 agent 的输出，核验人（可能只想早点结单）
    提交一份同样不过判据的修正稿，却因为「人工核验通过了」而放行。
    """
    admin = make_admin(client, "13800001030")
    task, _ = escalated_task(client, requester, admin, runner, expect="failed",
                             acceptance_criteria=[
                                 {"text": "必须包含免责声明", "kind": "auto",
                                  "check": {"op": "contains", "value": "免责声明"}},
                             ])
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    v = make_verifier(client, "13800001031")
    client.post(f"/api/v1/verification-orders/{order_id}/claim", headers=auth(v))

    bad = client.post(f"/api/v1/verification-orders/{order_id}/outcome",
                      json={"outcome": "revised", "comment": "我改好了",
                            "revised_output": "改完了，很棒。"}, headers=auth(v))
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "criteria_failed"

    good = client.post(f"/api/v1/verification-orders/{order_id}/outcome",
                       json={"outcome": "revised", "comment": "补上了",
                             "revised_output": "内容……\n免责声明：仅供参考。"},
                       headers=auth(v))
    assert good.status_code == 200 and good.json()["unblocked"] is True


def test_ver_revised_requires_an_actual_revision(client, requester, runner):
    admin = make_admin(client, "13800001032")
    task, _ = escalated_task(client, requester, admin, runner)
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    v = make_verifier(client, "13800001033")
    client.post(f"/api/v1/verification-orders/{order_id}/claim", headers=auth(v))
    r = client.post(f"/api/v1/verification-orders/{order_id}/outcome",
                    json={"outcome": "revised", "comment": "改了", "revised_output": "  "},
                    headers=auth(v))
    assert r.status_code == 400


# ---------------------------------------------------------------- VER-010 资金
def test_ver010_verifier_gets_paid_and_invariants_hold(client, requester, runner):
    admin = make_admin(client, "13800001040")
    task, _ = escalated_task(client, requester, admin, runner)
    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    v = make_verifier(client, "13800001041")
    before = client.get("/api/v1/wallet", headers=auth(v)).json()["available_cents"]
    client.post(f"/api/v1/verification-orders/{order['id']}/claim", headers=auth(v))
    client.post(f"/api/v1/verification-orders/{order['id']}/outcome",
                json={"outcome": "approved", "comment": "可用"}, headers=auth(v))
    after = client.get("/api/v1/wallet", headers=auth(v)).json()["available_cents"]
    assert after - before == order["fee_cents"], "核验人做完了必须拿到钱"

    rec = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert rec["ok"] is True, rec["mismatches"]


def test_ver041_unclaimed_orders_expire_and_refund(client, requester, runner):
    """超时未接单自动退款。已接单的不自动退——钱退了人还在干是更糟的状态。"""
    from datetime import timedelta

    from app.core.db import SessionLocal
    from app.modules.account.models import utcnow
    from app.modules.verify.models import VerificationOrder

    admin = make_admin(client, "13800001050")
    task, _ = escalated_task(client, requester, admin, runner)
    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    with SessionLocal() as db:
        row = db.get(VerificationOrder, order["id"])
        row.deadline = utcnow() - timedelta(hours=1)
        db.commit()

    r = client.post("/api/v1/verify/jobs/expire-orders", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["expired"] >= 1
    rec = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert rec["ok"] is True, rec["mismatches"]


def test_ver_one_open_order_at_a_time(client, requester, runner):
    admin = make_admin(client, "13800001051")
    task, _ = escalated_task(client, requester, admin, runner)
    client.post(f"/api/v1/tasks/{task['id']}/verification", headers=auth(requester))
    r = client.post(f"/api/v1/tasks/{task['id']}/verification", headers=auth(requester))
    assert r.status_code == 409


# ---------------------------------------------------------------- VER-040 经验回流
def test_ver040_verification_writes_a_lesson_without_personal_data(client, requester, runner):
    """需求里的「持续帮助迭代」靠的就是这条。

    `KnowledgeCard` 记的是类目/价格/工期——记不下「怎么做才对」。
    核验结论恰好是这个信息，而且是带标注的。
    """
    from app.core.db import SessionLocal
    from app.modules.verify.models import VerificationLesson

    admin = make_admin(client, "13800001060")
    task, _ = escalated_task(client, requester, admin, runner)
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    v = make_verifier(client, "13800001061")
    client.post(f"/api/v1/verification-orders/{order_id}/claim", headers=auth(v))
    client.post(f"/api/v1/verification-orders/{order_id}/outcome",
                json={"outcome": "approved", "comment": "结构完整，可直接使用"},
                headers=auth(v))

    with SessionLocal() as db:
        lesson = (
            db.query(VerificationLesson)
            .order_by(VerificationLesson.id.desc()).first()
        )
    assert lesson is not None
    assert lesson.category == "软件开发" and lesson.outcome == "approved"
    assert "结构完整" in lesson.reason
    # 脱敏与 KB-002 同规矩：经验卡不带人
    cols = {c.key for c in VerificationLesson.__table__.columns}
    assert not (cols & {"user_id", "verifier_id", "creator_id", "executor_id"}), \
        "经验表不该存任何人的 id"


# ---------------------------------------------------------------- ESCA 升级阶梯
def test_esca001_ticket_escalates_to_dispute_with_context(client, requester, worker):
    """不带上下文的话用户要把话重说一遍——而**两次陈述不一致会被当成翻供**。"""
    topup(client, requester, 100000)
    topup(client, worker, 50000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    t = client.post("/api/v1/support/tickets",
                    json={"subject": "交付物有问题", "body": "对方交的东西和约定不符"},
                    headers=auth(requester)).json()
    r = client.post(f"/api/v1/support/tickets/{t['id']}/escalate-to-dispute",
                    json={"task_id": task["id"], "reason": "客服未能解决，申请平台处理"},
                    headers=auth(requester))
    assert r.status_code == 201, r.text
    dispute_id = r.json()["dispute_id"]

    # 两边互相能找到
    tickets = client.get("/api/v1/support/tickets", headers=auth(requester)).json()
    assert any(x["id"] == t["id"] and x["status"] == "escalated" for x in tickets)

    from app.core.db import SessionLocal
    from app.modules.dispute.models import Dispute

    with SessionLocal() as db:
        d = db.get(Dispute, dispute_id)
        ctx = (d.evidence or {}).get("from_ticket")
    assert ctx and ctx["ticket_id"] == t["id"]
    assert "和约定不符" in ctx["body"], "工单正文没带进纠纷，用户得重说一遍"


def test_esca001_cannot_escalate_the_same_ticket_twice(client, requester, worker):
    topup(client, requester, 100000)
    topup(client, worker, 50000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    t = client.post("/api/v1/support/tickets", json={"subject": "问题", "body": "描述"},
                    headers=auth(requester)).json()
    body = {"task_id": task["id"], "reason": "客服未能解决，申请平台处理"}
    assert client.post(f"/api/v1/support/tickets/{t['id']}/escalate-to-dispute",
                       json=body, headers=auth(requester)).status_code == 201
    r = client.post(f"/api/v1/support/tickets/{t['id']}/escalate-to-dispute",
                    json=body, headers=auth(requester))
    assert r.status_code == 409


def test_esca002_evidence_package_includes_ai_execution(client, requester, runner):
    """ESCA-003 平台是责任主体，所以 agent 的履约记录必须在证据包里——
    否则「谁做的、做成什么样、谁核过」在材料里是空白。

    注意这条扩展的是**既有的** `/legal/disputes/{id}/evidence-export`，
    没有另建一个导出端点：同一个动作两条路正是 V58 修过的那个缺陷。
    """
    admin = make_admin(client, "13800001070")
    task, _ = escalated_task(client, requester, admin, runner)
    order_id = client.post(f"/api/v1/tasks/{task['id']}/verification",
                           headers=auth(requester)).json()["id"]
    v = make_verifier(client, "13800001071")
    client.post(f"/api/v1/verification-orders/{order_id}/claim", headers=auth(v))
    client.post(f"/api/v1/verification-orders/{order_id}/outcome",
                json={"outcome": "approved", "comment": "可用"}, headers=auth(v))

    # ESCA-003 agent 执行的任务同样能开纠纷——被诉的是平台自己
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "对 AI 交付物的质量有异议"}, headers=auth(requester))
    assert d.status_code == 201, d.text
    pkg = client.get(f"/api/v1/legal/disputes/{d.json()['id']}/evidence-export",
                     headers=auth(requester)).json()

    ai = pkg["package"]["ai_execution"]
    assert ai is not None, "证据包里没有 AI 执行记录"
    assert ai["agent_runs"] and ai["agent_runs"][0]["status"] == "escalated"
    assert ai["verifications"] and ai["verifications"][0]["outcome"] == "approved"
    # 诚实标注：置信度是自报的，不是平台度量的
    assert "自报置信度" in ai["notice"]
    # 合同里的 AI 责任声明也必须在材料里
    assert "平台为本任务履约的责任主体" in pkg["package"]["contract"]["terms"]


def test_esca002_absent_ai_trail_says_absent_rather_than_empty(client, requester, worker):
    """**没有就返回 None，不返回一堆空数组。**

    全是空数组的 `ai_execution` 会让读材料的人以为「查过了，没有 AI 参与」，
    而实际上可能是这段根本没接上。
    """
    topup(client, requester, 100000)
    topup(client, worker, 50000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付不符约定，要求重做"}, headers=auth(requester)).json()
    pkg = client.get(f"/api/v1/legal/disputes/{d['id']}/evidence-export",
                     headers=auth(requester)).json()
    assert pkg["package"]["ai_execution"] is None


def test_no_duplicate_evidence_export_endpoint():
    """V58 的教训：同一个动作两条路，最常走的那条会抄近道。

    写这一批时我先自己写了一个 `/disputes/{id}/evidence-package`，
    然后发现 `legal` 里**已经有**一个更完整的导出（带哈希链验证、
    存证回执、证明力声明）。删掉自己那个、去扩展既有的，才是对的。
    这条钉住「只有一个导出端点」。
    """
    from app.main import app

    paths = [p for p in app.openapi()["paths"] if "evidence" in p]
    assert paths == ["/api/v1/legal/disputes/{dispute_id}/evidence-export"], \
        f"出现了不止一个证据导出端点：{paths}"
