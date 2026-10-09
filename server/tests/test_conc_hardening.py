"""CONC-050~052 并发硬化验证（18 号 spec）。

前几套「防重放」测试验证的是**串行重复提交**被拒；本套验证**真并发**：
多线程同时打同一资源，断言只有一次成功、资金不变量不破、job 不重复执行。

注意：测试库是 SQLite，没有 `SELECT ... FOR UPDATE`。这恰恰是价值所在——
这里通过的用例证明**即使拿不到行锁**，乐观锁（lock_version）+ 状态机
也足以挡住并发写；Postgres 上再叠一层行锁只会更严格，不会更松。
"""
import threading

import pytest
import sqlalchemy as sa

from app.core.db import SessionLocal, engine
from app.core.locks import acquire_job_lock, release_job_lock

from .conftest import JOB_HEADERS, auth, bind_payout, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _parallel(fn, n: int):
    """并发执行 n 次 fn(i)，返回结果列表（异常也收集，不吞）。"""
    results: list = [None] * n
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()  # 尽量对齐到同一瞬间发车
        try:
            results[i] = fn(i)
        except Exception as exc:  # noqa: BLE001 - 记录异常本身也是结果
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def _money_snapshot() -> dict:
    with engine.begin() as conn:
        rows = conn.execute(
            sa.text("SELECT user_id, available_cents, escrow_cents, frozen_cents FROM wallet_accounts")
        ).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def _assert_conservation(total_topup: int):
    """CONC-050 全局守恒：所有账户三态之和 == 累计充值（提现会减少，测试内不提现）。"""
    snap = _money_snapshot()
    total = sum(a + e + f for a, e, f in snap.values())
    assert total == total_topup, f"资金总额漂移：{total} != {total_topup}, 明细={snap}"
    for uid, (a, e, f) in snap.items():
        assert a >= 0 and e >= 0 and f >= 0, f"账户 {uid} 出现负数：{(a, e, f)}"


# ---------- CONC-050 并发放款：只有一次成功 ----------
def test_concurrent_accept_delivery_releases_once(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=50000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))

    def hit(_i):
        return client.post(
            f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester)
        ).status_code

    codes = _parallel(hit, 6)
    ok = [c for c in codes if c == 200]
    assert len(ok) == 1, f"并发验收应只成功一次，实际 {codes}"

    # 放款只发生一次：执行者到账 = 50000 - 8% 佣金
    snap = _money_snapshot()
    assert snap[worker["id"]][0] == 50000 - 50000 * 800 // 10000
    assert snap[requester["id"]][1] == 0  # 托管清零
    _assert_conservation(100000)


# ---------- CONC-050 并发托管：只有一次成功且只扣一次 ----------
def test_concurrent_fund_holds_escrow_once(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    r = client.post(
        f"/api/v1/tasks/{task['id']}/applications", json={"message": "我来"}, headers=auth(worker)
    )
    app_id = r.json()["id"]
    cid = client.post(
        f"/api/v1/applications/{app_id}/accept", headers=auth(requester)
    ).json()["contract_id"]
    for u in (requester, worker):
        client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(u))

    def hit(_i):
        return client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester)).status_code

    codes = _parallel(hit, 6)
    assert len([c for c in codes if c == 200]) == 1, f"并发托管应只成功一次，实际 {codes}"
    snap = _money_snapshot()
    assert snap[requester["id"]] == (70000, 30000, 0)
    _assert_conservation(100000)


# ---------- CONC-050 并发提现：额度不被绕过 ----------
def test_concurrent_withdraw_cannot_overdraw(client):
    user = register(client, "13800009001", "提现者")
    verify_user(client, user)
    bind_payout(client, user)
    topup(client, user, 50000)

    def hit(_i):
        return client.post(
            "/api/v1/wallet/withdraw", json={"amount_cents": 20000}, headers=auth(user)
        ).status_code

    codes = _parallel(hit, 5)
    ok = len([c for c in codes if c == 200])
    assert ok <= 2, f"余额 500 元最多支持 2 笔 200 元提现，实际成功 {ok} 笔（{codes}）"
    snap = _money_snapshot()
    available = snap[user["id"]][0]
    assert available == 50000 - ok * 20000
    assert available >= 0


# ---------- CONC-051 乐观锁：并发改同一合约行，第二个拿冲突 ----------
def test_optimistic_lock_rejects_lost_update(client, requester, worker):
    """直接在 ORM 层制造「两个会话读到同一版本、各自写回」，
    验证 lock_version 让后写者失败而不是静默覆盖（丢失更新）。"""
    from sqlalchemy.orm.exc import StaleDataError

    from app.modules.contract.models import Contract

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=40000)
    cid = match_and_fund(client, requester, worker, task)

    with SessionLocal() as db_a, SessionLocal() as db_b:
        a = db_a.get(Contract, cid)
        b = db_b.get(Contract, cid)
        assert a.lock_version == b.lock_version  # 两个会话看到同一版本
        a.terms = a.terms + "\nA 的修改"
        db_a.commit()  # 先提交者成功，版本 +1
        b.terms = b.terms + "\nB 的修改"
        with pytest.raises(StaleDataError):
            db_b.commit()  # 后提交者基于陈旧版本 → 冲突，不覆盖 A


def test_stale_data_maps_to_409(client):
    """CONC-013 冲突要以 409 concurrent_modification 出现在 API 边界，而不是 500。"""
    from sqlalchemy.orm.exc import StaleDataError

    app = client.app

    @app.get("/api/v1/_test/stale")
    def _boom():  # pragma: no cover - 仅测试路由
        raise StaleDataError("simulated")

    r = client.get("/api/v1/_test/stale")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "concurrent_modification"


# ---------- CONC-052 job 执行锁 ----------
def test_job_lock_allows_one_holder_and_expires(client):
    with SessionLocal() as db:
        assert acquire_job_lock(db, "unit_job", "holder-a", ttl_seconds=60) is True
        db.commit()
    with SessionLocal() as db:
        assert acquire_job_lock(db, "unit_job", "holder-b", ttl_seconds=60) is False
        db.commit()
    # 持锁者释放后，另一实例可接手
    with SessionLocal() as db:
        release_job_lock(db, "unit_job", "holder-a")
        db.commit()
    with SessionLocal() as db:
        assert acquire_job_lock(db, "unit_job", "holder-b", ttl_seconds=60) is True
        db.commit()


def test_job_lock_ttl_reclaimable_after_crash(client):
    """持锁进程崩溃（不释放）时，TTL 到期后必须能被抢占，否则 job 永久停摆。"""
    with SessionLocal() as db:
        assert acquire_job_lock(db, "crashy_job", "dead-instance", ttl_seconds=0) is True
        db.commit()
    with SessionLocal() as db:
        assert acquire_job_lock(db, "crashy_job", "live-instance", ttl_seconds=60) is True
        db.commit()


def test_job_endpoint_is_serialized_and_reusable(client, requester):
    """job 端点串行调用始终可用（执行完即释放锁），并发时最多一个在跑。"""
    for _ in range(3):
        r = client.post("/api/v1/tasks/jobs/auto-accept", headers=JOB_HEADERS)
        assert r.status_code == 200, r.text

    def hit(_i):
        return client.post("/api/v1/tasks/jobs/expire-tasks", headers=JOB_HEADERS).status_code

    codes = _parallel(hit, 4)
    assert 200 in codes
    assert all(c in (200, 409) for c in codes), codes


# ---------- DEP-010/011 探针 ----------
def test_health_and_ready_probes(client):
    assert client.get("/healthz").json() == {"ok": True}
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["ratelimit"] == "memory"  # 未配 Redis 时的缺省后端


# ---------- CONC-021 限流降级 ----------
def test_ratelimit_degrades_to_memory_when_backend_fails(monkeypatch):
    """Redis 挂掉不能挡住登录：连续失败进入冷却期并落回内存实现。"""
    from app.core import ratelimit as rl

    class Broken:
        def hit(self, *_a, **_k):
            raise RuntimeError("connection refused")

        def reset(self):
            pass

    rl.reset()
    monkeypatch.setattr(rl.settings, "REDIS_URL", "redis://unused")
    monkeypatch.setattr(rl, "_get_remote", lambda: Broken())
    for _ in range(rl.settings.RATELIMIT_FAIL_THRESHOLD):
        rl.check("degrade-key", limit=100, window_seconds=60)  # 不抛异常 = 已降级放行
    assert "degraded" in rl.backend_status()
    # 降级后内存实现仍然真的限流（不是无脑放行）
    with pytest.raises(Exception) as exc:
        for _ in range(5):
            rl.check("degrade-limit", limit=2, window_seconds=60)
    assert exc.value.detail["code"] == "rate_limited"
    rl.reset()


# ---------- PAY-046 第一次读钱包不许 500 ----------
def test_conc053_first_wallet_touch_never_raises(requester):
    """并发第一次碰钱包账户，不许有人拿到异常，且只能建出一行。

    `get_or_create` 原来是 check-then-insert：两个并发请求同时看到「没有」，
    都插入，后一个撞上 `wallet_accounts.user_id` 唯一约束 → **500**。
    探针实测：新用户并发 12 次 `GET /wallet`，稳定出 1 次 500。

    这条不是理论竞态。真实触发路径至少两条：客户端首屏同时发两个请求
    （web 与 App 都登着，或手抖点两下）；放款后的事件处理与用户请求并发——
    用户刚收到到账通知就点开钱包，正是最可能撞上的那一刻。
    而 500 的那个页面是**钱包**：**在钱的页面上报 500，比在别处报 500 更贵。**
    """
    from app.modules.wallet import service as wallet_service

    uid = requester["id"]
    with SessionLocal() as db:
        db.execute(sa.text("DELETE FROM wallet_accounts WHERE user_id = :u"), {"u": uid})
        db.commit()

    def once(_i):
        with SessionLocal() as db:
            acct = wallet_service.get_or_create(db, uid)
            db.commit()
            return acct.user_id

    results = _parallel(once, 8)
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, f"并发建钱包抛异常了（就是用户看到的那个 500）：{errors!r}"
    assert all(r == uid for r in results), f"返回了别人的账户：{results!r}"

    with engine.begin() as conn:
        n = conn.execute(sa.text("SELECT COUNT(*) FROM wallet_accounts WHERE user_id = :u"),
                         {"u": uid}).scalar()
    assert n == 1, f"并发之后 {n} 行钱包账户——唯一约束本该只允许一行"


# ---------- IM-052 单聊并发不许建出两条会话 ----------
def test_conc055_concurrent_direct_open_yields_one_conversation(client, requester, worker):
    """两个人同时开同一个单聊，只能有一条会话。

    改造前 `get_or_create_direct` 是 check-then-insert，而 `participants` 是
    JSON——库里**建不了唯一约束**，于是并发会建出两条：两人各说各话、
    消息分在两条线上，而**谁都不会看到错误**。
    探针实测：并发 10 次开同一个单聊，拿到两个会话 id。

    V112 的钱包是同一个形状，但那张表有唯一约束，所以它只是 500。
    **没有约束的地方，竞态不报错，只把数据悄悄弄错**——比 500 难查得多。

    这一条**两侧交替发起**：规范化键必须让 (A,B) 与 (B,A) 落到同一条，
    否则两个人各从自己那一侧点「发消息」就又分叉了。

    **边界要说清**：进程内的线程**不能稳定复现那个竞态窗口**——SQLite 把写
    串行化了，等第二个线程查的时候第一个常常已经提交。实测把修法退回
    check-then-insert，这一条仍然是绿的。所以真正的保证分两层：

    - **唯一索引**（迁移建的）让库拒绝重复行——那是兜底，不靠代码时序；
    - 代码接住冲突并重读，不把它变成 500——这一点由下面那条结构断言钉住。

    这一条本身钉的是「并发之后库里只有一条、而且没人拿到异常」。
    """
    from app.modules.im import service as im

    a, b = requester["id"], worker["id"]

    def once(i):
        with SessionLocal() as db:
            conv = im.get_or_create_direct(db, *( (a, b) if i % 2 else (b, a) ))
            db.commit()
            return conv.id

    results = _parallel(once, 8)
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, f"并发开单聊抛异常了：{errors!r}"
    assert len(set(results)) == 1, f"建出了多条会话：{sorted(set(results))}"

    with engine.begin() as conn:
        rows = conn.execute(sa.text(
            "SELECT COUNT(*) FROM conversations WHERE direct_key = :k"
        ), {"k": im.direct_key(a, b)}).scalar()
    assert rows == 1, f"库里有 {rows} 条同一对的单聊——唯一索引本该只允许一条"


def test_im052_key_is_normalised_so_either_side_finds_the_same_row(client, requester, worker):
    """(A,B) 与 (B,A) 必须是同一个键。

    不规范化的后果不是报错，是**两个人各有一条「和对方的会话」**，
    而各自都看不到对方发的话。
    """
    from app.modules.im import service as im

    a, b = requester["id"], worker["id"]
    assert im.direct_key(a, b) == im.direct_key(b, a)
    with SessionLocal() as db:
        first = im.get_or_create_direct(db, a, b)
        db.commit()
        again = im.get_or_create_direct(db, b, a)
        assert again.id == first.id


def test_im051_opening_a_direct_does_not_scan_every_conversation(client, requester, worker):
    """开单聊不许把全平台的单聊都取出来。

    改造前这个函数 `db.query(Conversation).filter(kind=='direct').all()`
    然后在 Python 里比参与者集合——**每开一次私聊扫一遍全表**，
    用户量一上来就是首屏最慢的那个请求。

    这一条不量时间（机器不同数字不同，而那种断言会在别人的机器上误报），
    而是钉住**查询里带着键**：按键查走的是唯一索引，与表里有多少行无关。
    """
    import inspect

    from app.modules.im import service as im

    src = inspect.getsource(im.get_or_create_direct)
    assert "direct_key ==" in src, "没有按 direct_key 查，可能又回到了全表扫描"
    assert ".all()" not in src, "函数里还有 .all()——那是把整张表取出来的写法"


def test_im052_the_unique_conflict_is_recovered_not_surfaced_as_500():
    """撞上唯一索引时要重读，而不是把 500 抛给用户。

    为什么这一条是**结构断言**而不是跑并发：进程内线程复现不了那个窗口
    （见上面那条的边界说明），而唯一索引在生产上一定会偶尔撞到——
    撞到时用户看到的应当是会话打开了，不是「服务器错误」。
    V112 的钱包是同一个写法，那一批已经证明过这条路径的必要性。
    """
    import inspect

    from app.modules.im import service as im

    src = inspect.getsource(im.get_or_create_direct)
    assert "IntegrityError" in src, "没有接住唯一约束冲突——并发撞上就是 500"
    assert "begin_nested" in src, (
        "没有用 SAVEPOINT：插入失败会毒化外层事务，"
        "而调用方常常正在做发消息/建任务会话这种多步写入"
    )
    assert "raise" in src, "冲突后读不到仍要抛——吞掉异常会换成后面更难查的 None"
