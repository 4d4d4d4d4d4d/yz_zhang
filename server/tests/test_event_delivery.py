"""EVT-040~046 事件投递：失败隔离、留痕、补做、死信（28 号 spec）。

核心那条是 EVT-040，它盯的是一个**已用探针复现过的生产事故路径**：
`task.completed` 上挂着 6 个派生 handler，改造前任何一个抛异常，
验收放款整笔回滚——知识卡片生成失败（走 LLM，超时很正常），
执行方就拿不到钱。知识库是锦上添花，放款是这个平台的存在理由。
"""
import pytest

from app.core import events
from app.core.db import SessionLocal

from .conftest import JOB_HEADERS, auth, register, topup
from .test_task_flow import match_and_fund, publish_task


@pytest.fixture()
def clean_bus():
    """订阅表是进程级的，测试注册的 handler 必须还原，否则污染后续测试。"""
    snapshot = {k: list(v) for k, v in events._handlers.items()}
    yield events
    events._handlers.clear()
    events._handlers.update(snapshot)


def boom(db, payload):
    raise RuntimeError("知识卡片生成失败（比如 LLM 超时）")


def deliver_and_accept(client, requester, worker, task):
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    return client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))


def ready_contract(client, requester, worker, budget=30000):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=budget)
    match_and_fund(client, requester, worker, task)
    return task


def deliveries(status=None):
    with SessionLocal() as db:
        q = db.query(events.EventDelivery)
        if status:
            q = q.filter(events.EventDelivery.status == status)
        return q.all()


# ---------- EVT-040 派生副作用失败不能拖死资金交易 ----------
def test_evt040_derived_handler_failure_does_not_roll_back_the_payout(
    client, requester, worker, clean_bus,
):
    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", boom, retry=True)

    r = deliver_and_accept(client, requester, worker, task)
    assert r.status_code == 200, r.text

    # 钱照常到账（30000 扣 8% 平台佣金）
    wallet = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert wallet["available_cents"] == 27600

    # 但失败没有被吞掉——留了痕，且是可补做状态
    failed = [d for d in deliveries("failed") if d.handler.endswith("boom")]
    assert len(failed) == 1
    assert "RuntimeError" in failed[0].last_error


def test_evt042_one_broken_subscriber_does_not_drag_down_the_others(
    client, requester, worker, clean_bus,
):
    """一个订阅者坏了不该拖累其他人：同事件的其它 handler 照常生效。"""
    from app.modules.knowledge.models import KnowledgeCard

    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", boom, retry=True)

    assert deliver_and_accept(client, requester, worker, task).status_code == 200
    with SessionLocal() as db:
        # 经验入库（同一事件的另一个 handler）没有受影响
        assert db.query(KnowledgeCard).filter(
            KnowledgeCard.source_task_id == task["id"]
        ).first() is not None


def test_evt040_savepoint_rolls_back_only_the_failing_handler(
    client, requester, worker, clean_bus,
):
    """失败 handler 已经写进去的东西必须回滚干净，否则重试会建在半成品上。"""
    from app.modules.notification.models import Notification

    def write_then_fail(db, payload):
        db.add(Notification(user_id=1, category="task", title="半成品", body=""))
        db.flush()
        raise RuntimeError("写了一半才炸")

    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", write_then_fail, retry=True)

    assert deliver_and_accept(client, requester, worker, task).status_code == 200
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.title == "半成品").count() == 0


# ---------- EVT-041 critical handler 失败必须让业务事务失败 ----------
def test_evt041_critical_handler_failure_aborts_the_business_transaction(
    client, requester, worker, clean_bus,
):
    """存证入链这类 handler 不是「副作用」，是业务本身——它失败就该整笔失败。

    签了字却没有链上记录，等于平台对外承诺的证据能力有洞。
    """
    from app.modules.wallet.models import WalletAccount

    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("contract.released", boom, retry=False, critical=True)

    with pytest.raises(RuntimeError):
        deliver_and_accept(client, requester, worker, task)

    with SessionLocal() as db:
        acct = db.get(WalletAccount, worker["id"])
        assert (acct.available_cents if acct else 0) == 0  # 钱一分没动


# ---------- EVT-045 发件箱与业务同生共死 ----------
def test_evt045_rolled_back_transaction_leaves_no_event(client, clean_bus):
    with SessionLocal() as db:
        events.publish(db, "task.completed", {"task_id": 999999})
        db.rollback()
    with SessionLocal() as db:
        assert db.query(events.OutboxEvent).count() == 0
        assert db.query(events.EventDelivery).count() == 0


def test_evt001_committed_transaction_records_the_event(client, requester, worker):
    ready_contract(client, requester, worker)
    with SessionLocal() as db:
        rows = db.query(events.OutboxEvent).all()
        names = {r.event for r in rows}
        assert {"task.published", "contract.funded"} <= names
        # 发布副本要记下来：排查「只有某个副本出问题」时的第一手线索
        assert all(r.instance for r in rows)


# ---------- EVT-043 补做，且不重复补 ----------
def test_evt043_drain_recovers_and_does_not_double_apply(
    client, requester, worker, clean_bus,
):
    from app.modules.notification.models import Notification

    calls = {"n": 0}

    def flaky(db, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("第一次失败")
        db.add(Notification(user_id=payload["task_id"], category="task",
                            title="补做成功", body=""))
        db.flush()

    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", flaky, retry=True)
    assert deliver_and_accept(client, requester, worker, task).status_code == 200

    first = client.post("/api/v1/events/jobs/drain", headers=JOB_HEADERS).json()
    assert first["recovered"] == 1
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.title == "补做成功").count() == 1

    # 重复 drain 不该重复补：已 done 的投递不再进入扫描范围
    second = client.post("/api/v1/events/jobs/drain", headers=JOB_HEADERS).json()
    assert second["scanned"] == 0
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.title == "补做成功").count() == 1


def test_evt023_repeated_failures_become_dead_letters(client, requester, worker, clean_bus):
    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", boom, retry=True)
    assert deliver_and_accept(client, requester, worker, task).status_code == 200

    for _ in range(events.MAX_ATTEMPTS):
        client.post("/api/v1/events/jobs/drain", headers=JOB_HEADERS)

    dead = [d for d in deliveries("dead") if d.handler.endswith("boom")]
    assert len(dead) == 1
    assert dead[0].attempts >= events.MAX_ATTEMPTS
    # 转死信后不再被 drain 扫到，避免无限重试打爆日志与数据库
    assert client.post("/api/v1/events/jobs/drain", headers=JOB_HEADERS).json()["scanned"] == 0


# ---------- EVT-044 不可重试的直接进死信 ----------
def test_evt044_non_retryable_handler_goes_straight_to_dead_letter(
    client, requester, worker, clean_bus,
):
    """周期任务续期会**创建一个带预算的新任务**：几小时后由后台悄悄补出来一单，
    比缺这一期更糟。所以它失败不自动补做，留给人判断。
    """
    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", boom, retry=False)
    assert deliver_and_accept(client, requester, worker, task).status_code == 200

    dead = [d for d in deliveries("dead") if d.handler.endswith("boom")]
    assert len(dead) == 1
    assert dead[0].attempts == 1  # 一次都没重试过
    assert client.post("/api/v1/events/jobs/drain", headers=JOB_HEADERS).json()["scanned"] == 0


def test_evt022_dead_letters_are_visible_to_operators(
    client, requester, worker, clean_bus, admin,
):
    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", boom, retry=False)
    deliver_and_accept(client, requester, worker, task)

    body = client.get("/api/v1/events/dead-letters", headers=auth(admin)).json()
    assert any(i["handler"].endswith("boom") for i in body["items"])
    assert "未发生的副作用" in body["note"]


def test_dead_letters_require_admin(client, requester):
    assert client.get("/api/v1/events/dead-letters", headers=auth(requester)).status_code == 403


# ---------- EVT-046 新增 handler 必须回答「能不能自动补做」 ----------
def test_evt046_subscribe_without_retry_declaration_is_rejected():
    with pytest.raises(TypeError):
        events.subscribe("task.completed", boom)  # type: ignore[call-arg]


def test_every_registered_handler_declared_its_retry_policy():
    """全站扫一遍：不允许有 handler 绕过声明。"""
    assert events._handlers, "订阅表不该是空的（模块注册没跑起来）"
    for event, subs in events._handlers.items():
        for sub in subs:
            assert isinstance(sub.retry, bool), f"{event} → {sub.name} 未声明 retry"


# ---------- EVT-030/031 可观测 ----------
def test_evt031_health_and_metrics_expose_backlog(client, requester, worker, clean_bus):
    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", boom, retry=True)
    deliver_and_accept(client, requester, worker, task)

    health = client.get("/api/v1/events/health", headers=JOB_HEADERS).json()
    assert health["pending_retry"] == 1
    assert any(k.endswith("boom") for k in health["by_handler"])

    metrics = client.get("/metrics", headers=JOB_HEADERS).text
    assert "platform_event_pending_retry 1" in metrics
    assert "platform_event_dead_letters 0" in metrics


def test_event_ops_endpoints_require_job_token(client):
    for path in ("/api/v1/events/jobs/drain", "/api/v1/events/jobs/purge"):
        assert client.post(path).status_code == 403
    assert client.get("/api/v1/events/health").status_code == 403


# ---------- EVT-004 保留期清理 ----------
def test_evt004_purge_keeps_unfinished_deliveries(client, requester, worker, clean_bus):
    """清理只删已完成的旧事件——失败与死信留着，它们还等着人处理。"""
    from datetime import timedelta

    from app.modules.account.models import utcnow

    task = ready_contract(client, requester, worker)
    clean_bus.subscribe("task.completed", boom, retry=True)
    deliver_and_accept(client, requester, worker, task)

    old = utcnow() - timedelta(days=events.RETENTION_DAYS + 1)
    with SessionLocal() as db:
        db.query(events.OutboxEvent).update({"created_at": old}, synchronize_session=False)
        db.commit()

    result = client.post("/api/v1/events/jobs/purge", headers=JOB_HEADERS).json()
    assert result["deleted"] > 0
    assert result["kept_unfinished"] == 1
    # 失败的那条连同它的事件都还在，否则重试时读不到 payload
    failed = [d for d in deliveries("failed") if d.handler.endswith("boom")]
    assert len(failed) == 1
    with SessionLocal() as db:
        assert db.get(events.OutboxEvent, failed[0].event_id) is not None


@pytest.fixture()
def admin(client):
    from app.modules.account.models import User

    user = register(client, "13800030001", "运维")
    with SessionLocal() as db:
        row = db.get(User, user["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return user
