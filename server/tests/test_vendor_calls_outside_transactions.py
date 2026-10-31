"""CONC-067 调外部服务时不许挂着数据库事务（113 号 spec）。

量过：全量测试里 260 次供应商调用有 259 次发生在一个没结束的事务里。Postgres 上那是
`idle in transaction`——每次等供应商都占着一条池连接与行锁，供应商一慢，连接池先耗尽，
与它无关的接口一起挂。

守卫在开发 / 测试环境**直接抛错**，所以整套后端测试本身就是这条闸门：哪个用例走到了
事务内调供应商的路径，哪个用例就红。这里另外钉住守卫自己：会抓、不误抓、生产不打挂请求、
`release` 不替调用方提前提交写入。
"""
import pytest
import sqlalchemy as sa

from app.core import txguard
from app.core.db import SessionLocal
from app.vendors import base as vendor_base
from app.vendors import registry


class _Fake:
    name = "fake"

    def ping(self):
        return "pong"


@pytest.fixture()
def guarded():
    txguard.reset()
    yield txguard.Guarded("fake", _Fake())
    txguard.reset()


def test_the_guard_catches_a_call_inside_an_open_transaction(client, guarded):
    """扫描器自检：故意在事务里调一次，必须被抓到。"""
    with SessionLocal() as db:
        db.execute(sa.text("SELECT 1"))
        assert txguard.in_transaction()
        with pytest.raises(txguard.TransactionHeldAcrossVendorCall):
            guarded.ping()
        db.rollback()
    assert txguard.violations["fake.ping"] == 1


def test_no_transaction_no_complaint(client, guarded):
    with SessionLocal() as db:
        db.execute(sa.text("SELECT 1"))
        db.commit()
        assert not txguard.in_transaction()
        assert guarded.ping() == "pong"
    assert not txguard.violations


def test_production_logs_and_counts_but_never_breaks_the_request(client, guarded, monkeypatch, caplog):
    """防御性检查不许在生产上把用户的请求打挂：记日志、记数、照常执行。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "prod")
    with SessionLocal() as db:
        db.execute(sa.text("SELECT 1"))
        with caplog.at_level("ERROR", logger="txguard"):
            assert guarded.ping() == "pong"
        db.rollback()
    assert txguard.violations["fake.ping"] == 1
    assert any("CONC-067" in r.getMessage() for r in caplog.records)


def test_release_commits_a_read_only_transaction(client, guarded):
    with SessionLocal() as db:
        db.execute(sa.text("SELECT 1"))
        vendor_base.release(db)
        assert not txguard.in_transaction()
        assert guarded.ping() == "pong"


def test_release_never_commits_someone_elses_half_finished_writes(client, guarded):
    """已经写过的事务不能替调用方提交：那会把一半的业务改动提前落库。守卫照样报。"""
    from app.modules.account.models import User

    with SessionLocal() as db:
        db.add(User(phone="13800167001", nickname="x", password_hash="x"))
        db.flush()
        vendor_base.release(db)
        assert txguard.in_transaction() and txguard.wrote_in_transaction()
        with pytest.raises(txguard.TransactionHeldAcrossVendorCall):
            guarded.ping()
        db.rollback()
    with SessionLocal() as db:
        assert db.query(User).filter_by(phone="13800167001").first() is None


def test_every_provider_the_registry_hands_out_is_guarded(client):
    registry.reset()
    try:
        for kind in registry._REGISTRY:
            assert isinstance(registry.get_provider(kind), txguard.Guarded), kind
    finally:
        registry.reset()


def test_violations_are_visible_on_the_metrics_endpoint(client, guarded, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "prod")
    with SessionLocal() as db:
        db.execute(sa.text("SELECT 1"))
        guarded.ping()
        db.rollback()
    r = client.get("/metrics", headers={"X-Job-Token": settings.JOB_TOKEN})
    assert 'vendor_call_in_transaction_total{call="fake.ping"} 1' in r.text


# ------------------------------------------------------------------ 显式提交点登记表
# 提前提交是一种语义变化：原来「失败就整笔回滚」的那部分保证，在提交点之前的改动上不再成立。
# 所以每一个 `checkpoint(...)` 都必须登记在这里，并说清「为什么到这一步为止本身就是一致的」。
CHECKPOINTS = {
    "app/modules/openapi/usage.py::record_rejected":
        "被挡回去的 API 请求也是独立的用量记账：回 429 之后请求会回滚，必须先落库",
    "app/modules/openapi/usage.py::consume_ex":
        "API Key 当日用量是独立记账：与最近使用时间一样在鉴权时当场提交，接口失败也算用过一次",
    "app/modules/orchestrator/service.py::_dispatch_step":
        "编排本来就逐步可续跑：每一步的状态独立成立，前面各步已提交不影响后面重试",
    "app/modules/account/router.py::verify_identity":
        "提交表单即构成对证件处理的单独同意，核验失败也要留下这条同意的记录",
    "app/vendors/payment_service.py::create_topup_order":
        "充值订单是发给渠道的指令：先落库才可对账；失败时订单置 failed、幂等占键由 replay_or_run 放掉",
    "app/vendors/sms_service.py::send_code":
        "验证码先落库再发：用户收到就会来校验；发送失败时那条码没人收到，留着无害",
    "app/modules/wallet/service.py::withdraw":
        "出款两阶段：冻结与出款单先落库，钱在冻结里、单号可追，银行结果回来再结",
    "app/modules/wallet/service.py::settle_payout":
        "银行明确拒绝：解冻 / 退回待审必须先落库，再把错误还给调用方（之后请求会回滚）",
    "app/modules/wallet/service.py::_settle_or_processing":
        "出款结账：银行已确认打款，划出冻结与流水当场落库；这一步再失败也只能报「处理中」，由补偿 job 结清",
    "app/modules/wallet/service.py::decide_withdraw":
        "人审批准：批准记录与出款单先落库，再调银行；明确失败回到待审",
    "app/modules/files/router.py::read_sensitive_file":
        "管理员读证件影像的审计先落库再读存储：访问尝试本身就是要留下的事实，读取失败也要知道有人试过",
    "app/modules/agent/service.py::run_agent":
        "AI 助理运行：running 记录先落库——它就是防重复触发的并发闸，提交后其他连接才看得见",
    "app/modules/openapi/service.py::resolve_key":
        "API Key 最近使用时间是独立的记账事实：当场提交，后面的业务从一个干净的事务开始",
    "app/core/events.py::drain":
        "补做事件：每条投递本来就是自己的事务，前面各条的状态已经一致",
}


def _checkpoint_calls() -> set[str]:
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    found = set()
    for path in (root / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    f = node.func
                    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    if name == "checkpoint" and fn.name != "checkpoint":
                        found.add(f"{path.relative_to(root).as_posix()}::{fn.name}")
    return found


def test_checkpoint_scanner_sees_the_calls():
    assert "app/modules/wallet/service.py::withdraw" in _checkpoint_calls()


def test_every_early_commit_is_registered_with_a_reason():
    calls = _checkpoint_calls()
    unregistered = sorted(calls - set(CHECKPOINTS))
    assert not unregistered, ("这些地方提前提交了事务却没登记理由（CONC-067）：\n  " + "\n  ".join(unregistered)
                              + "\n在 CHECKPOINTS 里写明「为什么到这一步为止本身就是一致的」。")
    dead = sorted(set(CHECKPOINTS) - calls)
    assert not dead, f"登记了却已经没有调用：{dead}"
    assert all(len(r) >= 15 for r in CHECKPOINTS.values())


def test_checkpoint_refuses_an_empty_reason(client):
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            vendor_base.checkpoint(db, " ")


def test_in_process_providers_really_make_no_network_calls():
    """`in_process = True` 让守卫放行：那就必须真的不发网络请求——模块里不许引网络库。"""
    import ast
    import inspect

    network = ("httpx", "requests", "urllib", "socket", "http.client", "aiohttp", "anthropic")
    marked = []
    for kind, impls in registry._REGISTRY.items():
        for impl in impls.values():
            if getattr(impl, "in_process", False):
                marked.append(impl)
                tree = ast.parse(inspect.getsource(inspect.getmodule(impl)))
                for node in ast.walk(tree):
                    mods = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                            else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
                    assert not any(m.split(".")[0] in network or m.startswith(network) for m in mods), \
                        f"{impl.__name__} 标了 in_process 却引了 {mods}"
    assert marked, "一个 in_process 实现都没有？扫描器写错了"


def test_a_transaction_committed_on_another_thread_does_not_haunt_the_thread_that_opened_it(client, guarded):
    """真服务端上跑出来的误报：带 yield 的依赖，进入与收尾可能在线程池的不同线程上。
    事务在线程 A 开、在线程 B 提交——第一版按线程计数，A 的计数永远减不回去，
    之后落到 A 上的请求一调供应商就 500（测试客户端很少换线程，整套测试因此一直绿）。"""
    import threading

    db = SessionLocal()
    db.execute(sa.text("SELECT 1"))          # 本线程开事务
    assert txguard.in_transaction()
    t = threading.Thread(target=lambda: (db.commit(), db.close()))   # 别的线程收尾
    t.start()
    t.join()
    assert not txguard.in_transaction()
    assert guarded.ping() == "pong"
    assert not txguard.violations


def test_another_requests_open_transaction_on_the_same_thread_is_not_mine(client, guarded):
    """真浏览器全量回归里偶发的 `/search` 500：请求 A 在线程 X 上开着一个只读事务（合法，还没结束），
    请求 B 恰好也落在线程 X 上调供应商——按线程归属的守卫把 A 的事务算给了 B。现在按请求归属。"""
    import contextvars

    a, b = contextvars.copy_context(), contextvars.copy_context()
    a.run(txguard.enter_request)
    b.run(txguard.enter_request)
    db = SessionLocal()
    a.run(lambda: db.execute(sa.text("SELECT 1")))     # A 在本线程开了事务
    assert a.run(txguard.in_transaction) and not b.run(txguard.in_transaction)
    assert b.run(guarded.ping) == "pong"                # B 在同一个线程上调供应商：不是 B 的事务
    with pytest.raises(txguard.TransactionHeldAcrossVendorCall):
        a.run(guarded.ping)                             # A 自己调，照样抓
    db.rollback()
    db.close()
    assert not a.run(txguard.in_transaction)


def test_the_report_names_the_write_that_keeps_the_transaction_open(client, guarded):
    from app.modules.account.models import User

    with SessionLocal() as db:
        db.add(User(phone="13800167002", nickname="x", password_hash="x"))
        db.flush()
        with pytest.raises(txguard.TransactionHeldAcrossVendorCall, match="INSERT INTO users"):
            guarded.ping()
        db.rollback()
