"""NTF-060~061 / AGT-070/071 错过就无法挽回的通知（65 号 spec）。

三天后，发布方的钱会自动放给执行方。提醒他这件事的那条通知，改造前
**可以被用户在设置里关掉**，而且它**没有说「三天」**：

    notify(db, task.creator_id, "task", "待验收提醒",
           f"任务《{task.title}》已提交验收，超时将自动通过")

平台自己立过这条规矩——V61 给纠纷开案通知加 `force=True` 时写着：
「把它归到 task 类，等于允许用户用一个通知开关放弃自己的陈述权」。
待验收提醒是同一件事，而且后果是钱。
"""
import pytest

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.agent.runner import set_runner
from app.modules.notification.models import Notification
from app.modules.notification.service import MUST_REACH
from tests.conftest import auth, make_admin, register, topup, verify_user
from tests.test_agent_execution import FakeRunner, make_agent, remote_task
from tests.test_task_flow import match_and_fund, publish_task


def disable_category(client, user, category: str):
    """真的把用户的偏好关掉——**要验的是关了开关之后它到底还到不到**，
    不是检查 `force=True` 这个参数写没写（那只是实现细节）。"""
    r = client.put(f"/api/v1/notifications/prefs?category={category}&enabled=false",
                   headers=auth(user))
    assert r.status_code == 200, r.text


def notices(user_id: int, title: str | None = None) -> list[Notification]:
    with SessionLocal() as db:
        q = db.query(Notification).filter(Notification.user_id == user_id)
        if title:
            q = q.filter(Notification.title == title)
        return q.all()


# ------------------------------------------------- NTF-060 必达通知
def test_ntf060_pending_acceptance_notice_survives_the_switch(client, requester):
    """关掉「任务通知」之后，三天后钱自动放出去，而他一次提醒都收不到。"""
    worker = register(client, "13800065001", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    disable_category(client, requester, "task")
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))

    got = notices(requester["id"], "待验收提醒")
    assert got, "关掉任务通知后，待验收提醒就收不到了——而它到期会自动放款"


def test_ntf060_ordinary_notices_can_still_be_switched_off(client, requester):
    """开关不是摆设：不在声明表里的通知照常可以被关掉。

    把所有通知都做成不可关，用户会连真正重要的那几条一起屏蔽掉。
    """
    worker = register(client, "13800065010", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)

    disable_category(client, worker, "task")
    r = client.post(f"/api/v1/tasks/{task['id']}/invitations",
                    json={"user_id": worker["id"], "message": "来接单"},
                    headers=auth(requester))
    assert r.status_code in (200, 201), r.text
    assert not notices(worker["id"], "收到任务邀约"), "普通通知也关不掉，开关就是摆设"


def test_ntf060_every_declared_notice_actually_reaches(client, requester):
    """声明表逐条验：**关掉偏好之后仍然送达**。

    这条不看 `force=True` 写没写——那是实现细节；要验的是行为。
    """
    user = register(client, "13800065020", "收信人")
    # 只有 task/system/interaction 三类可关；其余类别（contract/account/…）
    # 根本没有开关，进表主要是为了**将来有人把它们做成可关时已经被保护住**
    for category, _title in MUST_REACH:
        if category in ("task", "system", "interaction"):
            disable_category(client, user, category)
    from app.modules.notification.service import notify

    with SessionLocal() as db:
        for category, title in MUST_REACH:
            notify(db, user["id"], category, title, "正文")
        db.commit()
    for category, title in MUST_REACH:
        assert notices(user["id"], title), f"声明为必达的「{title}」被开关拦住了"


def test_ntf060_declaration_table_says_why(client):
    """表里的值是**理由**，不是 True。判定标准只有一条：
    错过它，用户会失去一个他本可以行使的权利，或者失去一笔钱。"""
    assert len(MUST_REACH) >= 5
    for key, reason in MUST_REACH.items():
        assert isinstance(reason, str) and len(reason) >= 8, f"{key} 的理由太敷衍"


# ------------------------------------------------- NTF-061 期限要说出来
def test_ntf061_notice_states_the_deadline_from_config(client, requester, monkeypatch):
    """「超时将自动通过」——多久？改造前不说。

    而且数字必须取自配置：运维改成 7 天，这句话要跟着变（V61 同款教训）。
    """
    worker = register(client, "13800065030", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    monkeypatch.setattr(settings, "AUTO_ACCEPT_DAYS", 7)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))

    body = notices(requester["id"], "待验收提醒")[-1].body
    assert "7 天" in body, f"文案没跟着配置走：{body}"
    assert "自动验收并放款" in body


# ------------------------------------------------- AGT-070 AI 交的要说
@pytest.fixture()
def runner():
    r = FakeRunner()
    set_runner(r)
    yield r
    set_runner(None)


def test_agt070_agent_delivery_notice_says_it_was_ai(client, requester, runner):
    """发布方可能根本没意识到这一单是 AI 做的（尽管是他自己邀请的），
    而 N 天后就自动放款了。"""
    admin = make_admin(client, "13800065040")
    agent_id = make_agent(client, admin)
    topup(client, requester, 200000)
    task = remote_task(client, requester)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    cid = client.post(f"/api/v1/applications/{r.json()['id']}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester))

    body = notices(requester["id"], "待验收提醒")[-1].body
    assert "AI 助理" in body
    assert "责任主体" in body
    # V74 就建好的那条路，发布方在这个时点才需要知道它存在
    assert "人工核验" in body


# --------------------------------- AGT-071 「拿不准」下单，「没判成」不下单
class _Moderation:
    """可控的审核桩：分别造出「明确说拿不准」与「供应商挂了」两种 review。"""

    name = "local"

    def __init__(self):
        self.status, self.labels, self.raises = "pass", [], False

    def check(self, kind, text, media_urls=None):
        from app.vendors.base import VendorError, VendorResult

        if self.raises:
            raise VendorError("upstream_down", "内容安全服务不可用", retryable=True)
        return VendorResult(ok=True, external_ref="stub", status=self.status,
                            data={"labels": self.labels, "reason": "看不准"})


@pytest.fixture()
def moderation(monkeypatch):
    from app.vendors import registry

    stub = _Moderation()
    real = registry.get_provider
    monkeypatch.setattr(registry, "get_provider",
                        lambda kind: stub if kind == "moderation" else real(kind))
    return stub


def _agent_task_ready(client, requester, phone):
    admin = make_admin(client, phone)
    agent_id = make_agent(client, admin)
    topup(client, requester, 200000)
    task = remote_task(client, requester)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    cid = client.post(f"/api/v1/applications/{r.json()['id']}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    return task, admin


def _orders(task_id: int):
    from app.modules.verify.models import VerificationOrder

    with SessionLocal() as db:
        return db.query(VerificationOrder).filter(
            VerificationOrder.task_id == task_id).all()


def test_agt071_genuine_review_opens_a_platform_paid_order(client, requester, runner, moderation):
    """机器明确说「判不了」——这正是人工核验存在的理由。平台付费。"""
    task, admin = _agent_task_ready(client, requester, "13800065050")
    moderation.status = "review"
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run",
                      headers=auth(requester)).json()
    assert run["status"] == "escalated"

    orders = _orders(task["id"])
    assert len(orders) == 1, "审核说拿不准，却没有自动下核验单"
    from app.modules.wallet import service as wallet

    assert orders[0].payer_id == wallet.PLATFORM_USER_ID, "这笔钱不该由发布方出"
    assert orders[0].trigger == "escalation"
    # 资金不变量不因自动下单而破
    assert client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()["ok"] is True


def test_agt071_provider_outage_does_not_open_orders(client, requester, runner, moderation):
    """供应商挂了是基础设施问题。**花钱雇人去补一次宕机**，是把成本花在错误的
    地方；而且故障是批量的，一次抖动会瞬间下一堆单。"""
    task, _ = _agent_task_ready(client, requester, "13800065060")
    moderation.raises = True
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run",
                      headers=auth(requester)).json()
    assert run["status"] == "escalated"
    assert _orders(task["id"]) == [], "供应商宕机也自动下单，一次抖动就是一堆平台成本"

    # 出口仍在：发布方可以手动下单
    r = client.post(f"/api/v1/tasks/{task['id']}/verification", headers=auth(requester))
    assert r.status_code == 201, r.text


def test_agt071_low_confidence_alone_does_not_auto_open(client, requester, runner, moderation):
    """只有「审核拿不准」才自动下单。置信度不足是另一回事——
    那一条 V74 定的是发布方主动发起（平台付费），保持不变。"""
    admin = make_admin(client, "13800065070")
    agent_id = make_agent(client, admin, confidence_threshold_bps=9000)
    topup(client, requester, 200000)
    task = remote_task(client, requester)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    cid = client.post(f"/api/v1/applications/{r.json()['id']}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    runner.confidence_bps = 4000
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run",
                      headers=auth(requester)).json()
    assert run["status"] == "escalated"
    assert _orders(task["id"]) == []
