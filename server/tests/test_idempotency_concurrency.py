"""FIN-071 / FIN-072 / FIN-073 幂等：并发同键、过期、以及「从来没人带过键」（104 号 spec）。

V130 第一次探针（真并发，同一个键，6 个线程）：

    concurrent same key [500, 500, 500, 500, 500, 200]

六个请求**都把钱动了一遍**，前五个在最后记录幂等键时撞唯一约束而 500，
靠整个事务回滚才没有多入账。用户看到的是钱包页上的「服务器错误」，
而且他不知道钱动没动——于是他会再点一次。

同一次探针还查出：超过 80 个字符的键存进去的是 `key[:80]`、查的是完整的 key，
**永远查不到自己**，每次重试都重跑一遍再撞约束；以及两端的 SDK 从来没有
发过 `Idempotency-Key`——服务端把空键当成「不要幂等」，这条保护对真实用户
一次都没有生效过。
"""
import threading
from datetime import timedelta

import sqlalchemy as sa

from app.core.db import SessionLocal, engine
from tests.conftest import JOB_HEADERS, auth, bind_payout, money, register, verify_user


def _parallel(fn, n):
    results = [None] * n
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        try:
            results[i] = fn(i)
        except Exception as exc:  # noqa: BLE001 - 异常本身就是结果
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def _available(uid):
    with engine.begin() as conn:
        return conn.execute(sa.text("SELECT available_cents FROM wallet_accounts WHERE user_id=:u"),
                            {"u": uid}).scalar() or 0


# ------------------------------------------------- FIN-072 并发同键
def test_fin072_concurrent_same_key_topups_all_get_the_same_200(client):
    """六个同键请求同时到：钱只动一次，**每个人都拿到同一个 200**。"""
    u = register(client, "13800130001", "并发充值")
    headers = {**auth(u), "Idempotency-Key": "same-key-concurrent"}

    def hit(_i):
        r = client.post("/api/v1/wallet/topup", json={"amount_cents": 1000}, headers=headers)
        return r.status_code, r.json()

    results = _parallel(hit, 6)
    codes = [r[0] if isinstance(r, tuple) else repr(r) for r in results]
    assert codes == [200] * 6, f"同键并发不该有人拿到错误：{codes}"
    orders = {r[1]["order_no"] for r in results}
    assert len(orders) == 1, f"同一个键回放出了不同的结果：{orders}"
    assert _available(u["id"]) == 1000, "同键并发入账了不止一次"


def test_fin072_concurrent_same_key_withdrawals_move_money_once(client):
    """提现是钱出去的方向，重复的代价更高。"""
    u = register(client, "13800130002", "并发提现")
    verify_user(client, u)
    bind_payout(client, u)
    client.post("/api/v1/wallet/topup", json={"amount_cents": 50000}, headers=money(auth(u)))
    headers = {**auth(u), "Idempotency-Key": "same-key-withdraw"}

    results = _parallel(lambda _i: client.post(
        "/api/v1/wallet/withdraw", json={"amount_cents": 10000}, headers=headers).status_code, 5)
    assert results == [200] * 5, results
    assert _available(u["id"]) == 40000, "同键并发提现扣了不止一次"


def test_fin072_the_key_is_claimed_before_the_money_moves():
    """结构断言：先占键（ON CONFLICT DO NOTHING），再 run()。

    进程内线程复现不了 Postgres 上「后到的插入等前一个提交」的那个窗口；
    而顺序反过来（先跑再记）正是 V130 修掉的病——所以把顺序本身钉住。
    也钉住**不用 SAVEPOINT**：pysqlite 下它在占键时就提交了空占位（V130 第一版）。
    """
    import inspect

    from app.core import idempotency

    run_src = inspect.getsource(idempotency.replay_or_run)
    claim_src = inspect.getsource(idempotency._claim)
    assert "on_conflict_do_nothing" in claim_src
    assert run_src.index("_claim(") < run_src.index("result = run()"), "又变回先动钱再记键了"
    assert "begin_nested" not in run_src + claim_src, "SAVEPOINT 在 pysqlite 下会提前提交空占位"


# ------------------------------------------------- 键的长度
def test_long_keys_are_refused_not_truncated(client):
    """存 `key[:80]`、查完整 key：超长的键永远查不到自己。现在入口直接拒。"""
    u = register(client, "13800130003", "长键")
    r = client.post("/api/v1/wallet/topup", json={"amount_cents": 1000},
                    headers={**auth(u), "Idempotency-Key": "x" * 81})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "idempotency_key_invalid", r.text
    assert _available(u["id"]) == 0
    ok = {**auth(u), "Idempotency-Key": "y" * 80}
    first = client.post("/api/v1/wallet/topup", json={"amount_cents": 1000}, headers=ok)
    again = client.post("/api/v1/wallet/topup", json={"amount_cents": 1000}, headers=ok)
    assert first.status_code == again.status_code == 200, again.text
    assert first.json() == again.json() and _available(u["id"]) == 1000


# ------------------------------------------------- FIN-073 资金类强制带键
def test_fin073_money_endpoints_refuse_requests_without_a_key(client):
    """「资金类强制」写在 14.6 里，而服务端此前把空键当成不要幂等。"""
    u = register(client, "13800130004", "不带键")
    verify_user(client, u)
    bind_payout(client, u)
    for path, amount in (("/api/v1/wallet/topup", 1000), ("/api/v1/wallet/withdraw", 1000)):
        r = client.post(path, json={"amount_cents": amount}, headers=auth(u))
        assert r.status_code == 400, f"{path}：{r.status_code} {r.text}"
        assert r.json()["detail"]["code"] == "idempotency_required"
    assert _available(u["id"]) == 0


def test_fin073_failures_are_not_cached(client):
    """失败不缓存：余额不足被拒之后，同一个键在充值后重试会真的再试一次。"""
    u = register(client, "13800130005", "失败重试")
    verify_user(client, u)
    bind_payout(client, u)
    key = {**auth(u), "Idempotency-Key": "retry-after-failure"}
    first = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 5000}, headers=key)
    assert first.status_code == 400, first.text
    client.post("/api/v1/wallet/topup", json={"amount_cents": 10000}, headers=money(auth(u)))
    second = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 5000}, headers=key)
    assert second.status_code == 200, f"失败被缓存了，重试拿到的还是旧错误：{second.text}"
    # 只看状态码不够：被缓存的东西也可能以 200 回放出来。钱真的出去了才算真的重试了
    assert second.json().get("status") in ("done", "pending_review"), second.text
    assert _available(u["id"]) == 5000, "重试回放了旧东西，提现并没有真的发生"


# ------------------------------------------------- FIN-071 过期
def _age(uid, key, hours):
    from app.core.idempotency import IdempotencyRecord

    with SessionLocal() as db:
        row = db.query(IdempotencyRecord).filter_by(user_id=uid, key=key).one()
        row.created_at = row.created_at - timedelta(hours=hours)
        db.commit()


def test_fin071_expired_keys_are_new_keys_even_before_the_purge_runs(client):
    """过期在**读的时候**就生效，不靠清理 job 准时跑。"""
    from app.core.config import settings

    u = register(client, "13800130006", "过期键")
    key = {**auth(u), "Idempotency-Key": "old-key"}
    client.post("/api/v1/wallet/topup", json={"amount_cents": 1000}, headers=key)
    _age(u["id"], "old-key", settings.IDEMPOTENCY_RETENTION_HOURS - 1)
    client.post("/api/v1/wallet/topup", json={"amount_cents": 1000}, headers=key)
    assert _available(u["id"]) == 1000, "保留期内的键没有回放"
    _age(u["id"], "old-key", 2)
    r = client.post("/api/v1/wallet/topup", json={"amount_cents": 1000}, headers=key)
    assert r.status_code == 200, r.text
    assert _available(u["id"]) == 2000, "过期的键仍在回放旧结果"


def test_fin071_purge_job_deletes_only_expired_records(client):
    from app.core.config import settings
    from app.core.idempotency import IdempotencyRecord

    u = register(client, "13800130007", "清理")
    for k in ("keep", "drop"):
        client.post("/api/v1/wallet/topup", json={"amount_cents": 100},
                    headers={**auth(u), "Idempotency-Key": k})
    _age(u["id"], "drop", settings.IDEMPOTENCY_RETENTION_HOURS + 1)
    r = client.post("/api/v1/wallet/jobs/purge-idempotency", headers=JOB_HEADERS)
    assert r.status_code == 200 and r.json()["purged"] >= 1, r.text
    with SessionLocal() as db:
        left = {x.key for x in db.query(IdempotencyRecord).filter_by(user_id=u["id"])}
    assert left == {"keep"}, left


def test_fin071_purge_job_is_scheduled_and_guarded(client):
    from app.core.jobs import JOBS

    assert any(j.path == "/wallet/jobs/purge-idempotency" for j in JOBS), "清理 job 没进调度表"
    assert client.post("/api/v1/wallet/jobs/purge-idempotency").status_code in (401, 403)


def test_fin072_ci_runs_this_file_on_postgres():
    """这组测试在 SQLite 上全绿不说明什么：V130 第一版就是 SQLite 全绿、
    Postgres 上每一笔充值都 409。CI 的 Postgres job 里必须真的跑它。"""
    import re
    from pathlib import Path

    ci = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = re.search(r"^  postgres-acceptance:\n(.*?)(?=^  [\w-]+:\n|\Z)", ci, re.M | re.S)
    assert job, "CI 里找不到 postgres-acceptance job"
    body = job.group(1)
    assert "tests/test_idempotency_concurrency.py" in body, "Postgres job 不跑资金幂等与并发测试"
    assert "tests/test_decompose_tree.py" in body, "Postgres job 不跑逐层拆解测试（V132 只在 Postgres 上才看得见的那个 500）"
    assert "postgresql+psycopg://" in body
    for bad in ("|| true", "continue-on-error"):
        assert bad not in body
