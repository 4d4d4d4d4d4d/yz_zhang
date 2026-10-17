"""AGT-051/060~067 Agent 交付闭环与产出审核（56 号 spec）。

这一批的起点是一次探针：把 48/49 号 spec 建起来的链路**从 HTTP 口上**
完整走一遍。前五步（邀请→选人→签约→托管→执行）都通，第六步通不了：

    DELIVER as requester: 403 {'code': 'forbidden', 'message': '仅执行者可提交验收'}
    TASK STATUS after run: in_progress

agent 没有登录态（AGT-017，也不该有），`deliver` 只认执行者本人——
**生产里没有任何人能替它交付**。此前测试全绿，只因为它自己绕开 HTTP
直接调服务层，注释还写着「所以交付与验收走服务层」。

所以这个文件里的断言有一条硬规矩：**能走 HTTP 就走 HTTP**。
唯一读库的地方是检查交付记录落在谁名下（那是 HTTP 看不到的东西）。
"""
import pytest

from app.core.db import SessionLocal
from app.modules.agent import service as agent_service
from app.modules.agent.runner import set_runner
from app.modules.task.models import ProgressLog, Task
from app.vendors import registry
from app.vendors.base import VendorError, VendorResult
from tests.conftest import auth, make_admin, register, topup, verify_user
from tests.test_agent_execution import FakeRunner, make_agent, remote_task
from tests.test_task_flow import match_and_fund, publish_task
from tests.test_verification_escalation import make_verifier


@pytest.fixture()
def runner():
    r = FakeRunner()
    set_runner(r)
    yield r
    set_runner(None)


class _Moderation:
    """可控的内容审核桩。`name` 必须留着——vendor 留痕要用。"""

    name = "local"

    def __init__(self):
        self.status, self.labels, self.raises = "pass", [], False
        self.calls = []

    def check(self, kind, text, media_urls=None):
        self.calls.append((kind, text, media_urls))
        if self.raises:
            raise VendorError("upstream_down", "内容安全服务不可用", retryable=True)
        return VendorResult(ok=True, external_ref="stub", status=self.status,
                            data={"labels": self.labels})


@pytest.fixture()
def moderation(monkeypatch):
    stub = _Moderation()
    real = registry.get_provider
    monkeypatch.setattr(registry, "get_provider",
                        lambda kind: stub if kind == "moderation" else real(kind))
    return stub


def agent_task(client, requester, admin, agent_id=None, **task_over):
    """把任务推到「agent 已成交、已托管、可执行」。"""
    if agent_id is None:
        agent_id = make_agent(client, admin)
    topup(client, requester, 200000)
    task = remote_task(client, requester, **task_over)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    assert r.status_code == 201, r.text
    cid = client.post(f"/api/v1/applications/{r.json()['id']}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    return task, agent_id, cid


def run_agent(client, requester, task):
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))
    assert r.status_code == 201, r.text
    return r.json()


def task_status(client, user, task):
    return client.get(f"/api/v1/tasks/{task['id']}", headers=auth(user)).json()["status"]


def delivery_logs(task_id):
    with SessionLocal() as db:
        return (db.query(ProgressLog)
                .filter(ProgressLog.task_id == task_id, ProgressLog.kind == "delivery")
                .order_by(ProgressLog.id).all())


# ------------------------------------------------- AGT-060 这一批的主命题
def test_agt060_agent_task_can_actually_be_delivered_over_http(client, requester, runner,
                                                               moderation):
    """**探针复现的那条**：改造前这个任务永远停在 in_progress。

    整条链路一次 SessionLocal 都不用——这正是改造前做不到的事。
    """
    admin = make_admin(client, "13800056001")
    task, agent_id, _ = agent_task(client, requester, admin)

    run = run_agent(client, requester, task)
    assert run["status"] == "succeeded"
    assert run["delivered"] is True, "执行成功了却没有交付——这就是改造前的那个洞"
    assert run["task_status"] == "pending_acceptance"
    assert task_status(client, requester, task) == "pending_acceptance"

    # 发布方能正常验收放款，钱不再卡在托管里
    r = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"


def test_agt060_requester_still_cannot_press_deliver_himself(client, requester, runner,
                                                             moderation):
    """修法是**平台代交付**，不是放宽 `deliver` 的身份校验。

    那条校验同时管着所有人类任务；为一个 AI 的特例放宽它，代价不对等。
    """
    admin = make_admin(client, "13800056002")
    task, _, _ = agent_task(client, requester, admin)
    run_agent(client, requester, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(requester))
    assert r.status_code in (403, 409)
    assert r.json()["detail"]["code"] != "ok"


def test_agt064_delivery_log_is_attributed_to_the_agent(client, requester, runner, moderation):
    """交付记录记在 **agent 的 user 行**名下。

    纠纷证据链里必须能看出这份交付物是谁交的；记成发布方就是在证据里撒谎。
    """
    admin = make_admin(client, "13800056003")
    runner.output = "交付内容：接口已实现，附测试报告。"
    task, agent_id, _ = agent_task(client, requester, admin)
    run_agent(client, requester, task)

    logs = delivery_logs(task["id"])
    assert len(logs) == 1
    assert logs[0].user_id == agent_id
    assert logs[0].content == "交付内容：接口已实现，附测试报告。"


def test_agt064_delivery_text_reaches_the_dispute_evidence_export(client, requester, runner,
                                                                  moderation):
    """`agent_runs` 与 `progress_logs` 是两本账。产出只写前者的话，纠纷侧看不见。"""
    admin = make_admin(client, "13800056004")
    runner.output = "交付内容：这段话必须出现在证据里。"
    task, _, _ = agent_task(client, requester, admin)
    run_agent(client, requester, task)

    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付内容与约定不符，要求重做"}, headers=auth(requester))
    assert d.status_code == 201, d.text
    pkg = client.get(f"/api/v1/legal/disputes/{d.json()['id']}/evidence-export",
                     headers=auth(admin))
    assert pkg.status_code == 200, pkg.text
    assert "这段话必须出现在证据里" in str(pkg.json())


# --------------------------------------------- AGT-061 代交付不是后门
def test_agt061_failed_criteria_still_blocks_the_platform_delivery(client, requester, runner,
                                                                   moderation):
    """新开的路必须**比原来的路更窄**：代交付调闸门，不重写闸门。"""
    admin = make_admin(client, "13800056010")
    task, _, _ = agent_task(client, requester, admin, acceptance_criteria=[
        {"text": "必须包含验收口令", "kind": "auto",
         "check": {"op": "contains", "value": "验收口令"}},
    ])
    runner.output = "交付内容：写完了。"          # 不含口令 → 判据不过
    run = run_agent(client, requester, task)
    assert run["status"] == "failed"
    assert run["delivered"] is False
    assert task_status(client, requester, task) == "in_progress"
    assert delivery_logs(task["id"]) == []


def test_agt061_low_confidence_still_blocks_the_platform_delivery(client, requester, runner,
                                                                  moderation):
    admin = make_admin(client, "13800056011")
    agent_id = make_agent(client, admin, confidence_threshold_bps=9000)
    task, _, _ = agent_task(client, requester, admin, agent_id=agent_id)
    runner.confidence_bps = 4000
    run = run_agent(client, requester, task)
    assert run["status"] == "escalated" and run["delivered"] is False
    assert task_status(client, requester, task) == "in_progress"


def test_agt061_gate_is_not_bypassed_when_block_is_non_empty(client, requester, runner,
                                                             moderation):
    """直接钉住实现：闸门非空时 `submit_agent_delivery` 必须返回 False。

    这条是防回归用的——有人把 `delivery_block` 那两行从代交付里删掉时，
    上面两条集成测试也会红，但这条会**指着那一行**红。
    """
    admin = make_admin(client, "13800056012")
    agent_id = make_agent(client, admin, confidence_threshold_bps=9000)
    task, _, _ = agent_task(client, requester, admin, agent_id=agent_id)
    runner.confidence_bps = 4000
    run_agent(client, requester, task)
    with SessionLocal() as db:
        t = db.get(Task, task["id"])
        assert agent_service.delivery_block(db, t) != ""
        assert agent_service.submit_agent_delivery(db, t) is False
        assert t.status == "in_progress"


def test_agt060_human_tasks_are_never_touched_by_the_platform_path(client, requester,
                                                                   moderation):
    """代交付对人类执行的任务恒为 no-op：这条闸门只管 agent。"""
    worker = register(client, "13800056013", "人类执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    with SessionLocal() as db:
        t = db.get(Task, task["id"])
        assert agent_service.submit_agent_delivery(db, t) is False
        db.commit()
    # 人类那条路一点没变
    assert client.post(f"/api/v1/tasks/{task['id']}/deliver",
                       headers=auth(worker)).status_code == 200
    assert task_status(client, requester, task) == "pending_acceptance"


# ------------------------------------------------------------ AGT-062 幂等
def test_agt062_repeated_runs_produce_one_delivery(client, requester, runner, moderation):
    """`agent-run` 可以被重复触发（AGT-014 只挡并发，不挡串行重试）。"""
    admin = make_admin(client, "13800056020")
    task, _, _ = agent_task(client, requester, admin)
    first = run_agent(client, requester, task)
    before = delivery_logs(task["id"])[0]
    delivered_at_first = client.get(f"/api/v1/tasks/{task['id']}",
                                    headers=auth(requester)).json().get("delivered_at")

    second = run_agent(client, requester, task)
    assert first["delivered"] is True and second["delivered"] is False
    logs = delivery_logs(task["id"])
    assert len(logs) == 1 and logs[0].id == before.id
    after = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    assert after.get("delivered_at") == delivered_at_first, "delivered_at 被第二次执行重置了"


# ------------------------------------------- AGT-063 核验通过后自动交付
def test_agt063_approved_verification_delivers(client, requester, runner, moderation):
    """闸门解除了，但此前**没有任何东西去推那一下**。"""
    admin = make_admin(client, "13800056030")
    agent_id = make_agent(client, admin, confidence_threshold_bps=9000)
    task, _, _ = agent_task(client, requester, admin, agent_id=agent_id)
    runner.confidence_bps = 4000
    assert run_agent(client, requester, task)["status"] == "escalated"

    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    verifier = make_verifier(client, "13800056031")
    assert client.post(f"/api/v1/verification-orders/{order['id']}/claim",
                       headers=auth(verifier)).status_code == 200
    r = client.post(f"/api/v1/verification-orders/{order['id']}/outcome",
                    json={"outcome": "approved", "comment": "抽查三处，结论无误"},
                    headers=auth(verifier))
    assert r.status_code == 200, r.text
    assert r.json()["delivered"] is True
    assert task_status(client, requester, task) == "pending_acceptance"


def test_agt063_revised_delivers_the_revision_not_the_original(client, requester, runner,
                                                               moderation):
    """修正稿之所以存在，正因为原始产出不合格。

    把原始产出交出去，等于让发布方验收一份已被判定为不合格的东西，
    而他还刚为核验费买过单。
    """
    admin = make_admin(client, "13800056032")
    agent_id = make_agent(client, admin, confidence_threshold_bps=9000)
    task, _, _ = agent_task(client, requester, admin, agent_id=agent_id)
    runner.output = "原始产出：半成品。"
    runner.confidence_bps = 4000
    run_agent(client, requester, task)

    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    verifier = make_verifier(client, "13800056033")
    client.post(f"/api/v1/verification-orders/{order['id']}/claim", headers=auth(verifier))
    r = client.post(f"/api/v1/verification-orders/{order['id']}/outcome",
                    json={"outcome": "revised", "comment": "补齐了缺的一节",
                          "revised_output": "修正稿：补齐后的完整交付。"},
                    headers=auth(verifier))
    assert r.status_code == 200 and r.json()["delivered"] is True
    logs = delivery_logs(task["id"])
    assert len(logs) == 1
    assert logs[0].content == "修正稿：补齐后的完整交付。"
    assert "原始产出" not in logs[0].content


def test_agt063_rejected_verification_does_not_deliver(client, requester, runner, moderation):
    admin = make_admin(client, "13800056034")
    agent_id = make_agent(client, admin, confidence_threshold_bps=9000)
    task, _, _ = agent_task(client, requester, admin, agent_id=agent_id)
    runner.confidence_bps = 4000
    run_agent(client, requester, task)
    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    verifier = make_verifier(client, "13800056035")
    client.post(f"/api/v1/verification-orders/{order['id']}/claim", headers=auth(verifier))
    r = client.post(f"/api/v1/verification-orders/{order['id']}/outcome",
                    json={"outcome": "rejected", "comment": "与任务要求不符"},
                    headers=auth(verifier))
    assert r.json()["delivered"] is False
    assert task_status(client, requester, task) == "in_progress"


# ---------------------------------- AGT-067 判据没过的 run 只能被「已修正」解锁
def test_agt067_approved_cannot_unlock_a_criteria_failure(client, requester, runner,
                                                          moderation):
    """`approved` 只是一个人说了句「行」——那是**覆盖**判据，不是满足判据。

    AGT-030 的整个立论是「不让执行方自己判卷」，换成核验人判也一样。
    """
    admin = make_admin(client, "13800056040")
    task, _, _ = agent_task(client, requester, admin, acceptance_criteria=[
        {"text": "必须包含验收口令", "kind": "auto",
         "check": {"op": "contains", "value": "验收口令"}},
    ])
    runner.output = "交付内容：写完了。"
    assert run_agent(client, requester, task)["status"] == "failed"

    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    verifier = make_verifier(client, "13800056041")
    client.post(f"/api/v1/verification-orders/{order['id']}/claim", headers=auth(verifier))
    r = client.post(f"/api/v1/verification-orders/{order['id']}/outcome",
                    json={"outcome": "approved", "comment": "我觉得可以"},
                    headers=auth(verifier))
    assert r.status_code == 200
    assert r.json()["delivered"] is False, "一个人点一下就覆盖掉了平台的客观判据"
    assert task_status(client, requester, task) == "in_progress"


def test_agt067_revision_unlocks_a_criteria_failure(client, requester, runner, moderation):
    """能解锁靠的不是核验人的权威，而是 VER-030 强制修正稿**重跑一遍判据**。

    所以客观闸门一次也没被绕过，变的是那份被判的文本。
    改造前这里是个死胡同：核验费花了，闸门纹丝不动。
    """
    admin = make_admin(client, "13800056042")
    task, _, _ = agent_task(client, requester, admin, acceptance_criteria=[
        {"text": "必须包含验收口令", "kind": "auto",
         "check": {"op": "contains", "value": "验收口令"}},
    ])
    runner.output = "交付内容：写完了。"
    assert run_agent(client, requester, task)["status"] == "failed"

    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    verifier = make_verifier(client, "13800056043")
    client.post(f"/api/v1/verification-orders/{order['id']}/claim", headers=auth(verifier))
    # 不过判据的修正稿仍然被 VER-030 挡住
    bad = client.post(f"/api/v1/verification-orders/{order['id']}/outcome",
                      json={"outcome": "revised", "comment": "改好了",
                            "revised_output": "还是没写口令"}, headers=auth(verifier))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "criteria_failed"

    good = client.post(f"/api/v1/verification-orders/{order['id']}/outcome",
                       json={"outcome": "revised", "comment": "补上了",
                             "revised_output": "补齐：验收口令 已包含。"},
                       headers=auth(verifier))
    assert good.status_code == 200 and good.json()["delivered"] is True
    assert task_status(client, requester, task) == "pending_acceptance"


# ------------------------------------------------- AGT-051/065/066 产出审核
def test_agt051_output_is_actually_sent_to_moderation(client, requester, runner, moderation):
    """这条专门防「又一次建好了没接上」——V64 那个洞的同一个形状。"""
    admin = make_admin(client, "13800056050")
    runner.output = "交付内容：一段正常的产出。"
    task, _, _ = agent_task(client, requester, admin)
    run_agent(client, requester, task)
    assert moderation.calls, "agent 产出根本没有送内容审核"
    kind, text, _media = moderation.calls[-1]
    assert (kind, text) == ("text", "交付内容：一段正常的产出。")


def test_agt051_rejected_output_fails_the_run_and_is_not_stored(client, requester, runner,
                                                                moderation):
    """被拒的产出**不入库**（与 UMOD-011 对称），但 labels 留下来。

    labels 不留的话，运营面对「我的任务失败了」的工单只能看到一句
    「未通过审核」，答不上来为什么。
    """
    admin = make_admin(client, "13800056051")
    runner.output = "交付内容：违规文本。"
    task, _, _ = agent_task(client, requester, admin)
    # 发布环节用的是同一个审核供应商，所以裁决在**建完任务之后**才切
    moderation.status, moderation.labels = "reject", ["赌博"]
    run = run_agent(client, requester, task)

    assert run["status"] == "failed" and run["delivered"] is False
    assert run["output"] == "", "被拒的产出不该留在库里"
    assert run["moderation_status"] == "reject"
    assert "赌博" in run["error"]
    assert task_status(client, requester, task) == "in_progress"

    from app.modules.agent.models import AgentRun
    with SessionLocal() as db:
        row = db.get(AgentRun, run["id"])
        assert row.output == "" and row.moderation_labels == ["赌博"]


def test_agt065_moderation_runs_before_criteria(client, requester, runner, moderation):
    """一份违规的产出，判据过没过不重要。"""
    admin = make_admin(client, "13800056052")
    task, _, _ = agent_task(client, requester, admin, acceptance_criteria=[
        {"text": "必须包含验收口令", "kind": "auto",
         "check": {"op": "contains", "value": "验收口令"}},
    ])
    moderation.status, moderation.labels = "reject", ["色情"]
    runner.output = "验收口令 已包含，但内容违规。"      # 判据全过
    run = run_agent(client, requester, task)
    assert run["status"] == "failed"
    assert "内容安全审核" in run["error"], run["error"]
    assert run["criteria_results"] == [], "判据在审核之前跑了"


def test_agt066_moderation_outage_escalates_instead_of_delivering(client, requester, runner,
                                                                  moderation):
    """供应商故障时**不放行、也不销毁**：升级人审。

    与 UMOD-010 的 fail-open 方向一致（不因第三方抖动销毁内容），
    但不 open 到直接交付——上传物的用途是自证，agent 产出的用途是换钱。
    **分界线是代价落在谁身上。**
    """
    admin = make_admin(client, "13800056053")
    task, _, _ = agent_task(client, requester, admin)
    verifier = make_verifier(client, "13800056054")
    moderation.raises = True          # 其余用到审核的动作都做完了，再让供应商挂掉
    run = run_agent(client, requester, task)
    assert run["status"] == "escalated" and run["delivered"] is False
    assert run["moderation_status"] == "review"
    assert run["output"], "故障不该销毁产出，人还要看它"
    assert task_status(client, requester, task) == "in_progress"

    # 出口仍然是人工核验
    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    client.post(f"/api/v1/verification-orders/{order['id']}/claim", headers=auth(verifier))
    r = client.post(f"/api/v1/verification-orders/{order['id']}/outcome",
                    json={"outcome": "approved", "comment": "人工看过，没有问题"},
                    headers=auth(verifier))
    assert r.json()["delivered"] is True


def test_agt065_moderation_text_does_not_leak_into_the_vendor_log(client, requester, runner,
                                                                  moderation):
    """送审文本不进调用日志：抄一份到日志里，等于给违规内容多开一个落点。"""
    admin = make_admin(client, "13800056055")
    runner.output = "交付内容：独一无二的待审正文字符串。"
    task, _, _ = agent_task(client, requester, admin)
    run_agent(client, requester, task)

    from app.vendors.models import VendorCall
    with SessionLocal() as db:
        rows = (db.query(VendorCall)
                .filter(VendorCall.operation == "check_agent_output").all())
        assert rows, "审核调用没有留痕"
        for row in rows:
            assert "独一无二的待审正文字符串" not in (row.request_digest or "")
            assert "chars" in (row.request_digest or "")


# ---------------------------------------------------- 资金侧：闭环真的闭上了
def test_agt060_money_reaches_the_platform_through_the_http_path(client, requester, runner,
                                                                 moderation):
    """AGT-019 此前只能在服务层验证这件事。现在整条链路都能从 HTTP 走完，
    五条资金不变量仍然成立。"""
    from app.modules.wallet import service as wallet

    admin = make_admin(client, "13800056060")
    task, agent_id, _ = agent_task(client, requester, admin)
    run_agent(client, requester, task)
    assert client.post(f"/api/v1/tasks/{task['id']}/accept-delivery",
                       headers=auth(requester)).status_code == 200

    with SessionLocal() as db:
        assert wallet.get_or_create(db, agent_id).available_cents == 0, "agent 钱包应被归集"
        assert wallet.get_or_create(db, wallet.PLATFORM_USER_ID).available_cents > 0
    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert r["ok"] is True, r
