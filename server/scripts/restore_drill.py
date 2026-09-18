"""DRILL-020 备份恢复演练：**真的删库，真的恢复，真的校验。**

`deploy/backup.sh` 与 `deploy/restore.sh` 写得很仔细，但它们需要
完整的 Postgres + docker compose 生产栈，而且 `restore.sh` 会停下来
等人敲 `yes`。结果是：**这套备份从来没有被恢复过一次。**

一份没有恢复过的备份，不是备份，是一个关于备份的假设。

这个演练跑完整个循环，CI 每次都跑；**SQLite 与 Postgres 两条路径都覆盖**：

    1. 建库 → 造一笔真实闭环交易（有钱、有合约、有存证）
    2. 备份
    3. **把库删掉**（不是清空表，是删文件——模拟机器没了）
    4. 从备份恢复
    5. 跑 `scripts.consistency_check`——**和生产恢复时跑的是同一段代码**

DRILL-061：Postgres 那条路径此前只存在于 `backup.sh`/`restore.sh` 里，
从未被执行过。现在设了 `PLATFORM_DATABASE_URL=postgresql+...` 就走真实的
`pg_dump --clean --if-exists` + `psql` —— 与生产脚本**相同的命令与参数**。

    python -m scripts.restore_drill                      # SQLite 路径
    PLATFORM_DATABASE_URL=postgresql+psycopg://... \
        python -m scripts.restore_drill                  # Postgres 路径
"""
import os
import shutil
import sys
import tempfile

DRILL_DB = os.environ.get("DRILL_DB", "./drill.db")


def _fresh_env() -> None:
    os.environ["PLATFORM_DATABASE_URL"] = f"sqlite:///{DRILL_DB}"
    os.environ.setdefault("PLATFORM_LOG_LEVEL", "WARNING")


def seed() -> dict:
    """造一笔真实闭环：充值 → 发布 → 成交 → 托管 → 交付 → 验收放款。

    用 TestClient 走真实 HTTP 管线，而不是直接塞数据库——
    直接塞出来的数据可能本来就不满足不变量，那样演练就是在校验一个假数据。
    """
    from fastapi.testclient import TestClient

    from app.core.db import Base, engine
    from app.main import create_app

    Base.metadata.create_all(engine)
    app = create_app()
    with TestClient(app) as c:
        def reg(phone, nick):
            r = c.post("/api/v1/auth/register", json={
                "phone": phone, "password": "pass123456", "nickname": nick,
                "sms_code": "123456"})
            assert r.status_code == 201, r.text
            return r.json()["token"], r.json()["user"]["id"]

        def h(tok):
            return {"Authorization": f"Bearer {tok}"}

        a, _ = reg("13700000001", "发布方")
        b, bid = reg("13700000002", "执行方")
        for tok, name in ((a, "甲发布"), (b, "乙执行")):
            c.post("/api/v1/users/me/verify",
                   json={"real_name": name, "id_number": f"11010119900101{tok[-4:]}"},
                   headers=h(tok))
        c.post("/api/v1/wallet/topup", json={"amount_cents": 50000}, headers=h(a))
        r = c.post("/api/v1/tasks", json={"ip_assignment": "assign", 
            "title": "演练任务：周末大扫除", "description": "两室一厅深度保洁",
            "category": "保洁", "task_type": "service", "required_skills": ["保洁"],
            "budget_cents": 20000, "city": "上海", "lat": 31.2304, "lng": 121.4737,
            "address_hint": "静安寺商圈", "address_exact": "静安区南京西路 1234 号 5 栋 302",
            "publish_now": True}, headers=h(a))
        assert r.status_code == 201, r.text
        t = r.json()
        app_id = c.post(f"/api/v1/tasks/{t['id']}/applications",
                        json={"message": "我可以做"}, headers=h(b)).json()["id"]
        cid = c.post(f"/api/v1/applications/{app_id}/accept",
                     headers=h(a)).json()["contract_id"]
        c.post(f"/api/v1/contracts/{cid}/sign", headers=h(a))
        c.post(f"/api/v1/contracts/{cid}/sign", headers=h(b))
        c.post(f"/api/v1/contracts/{cid}/fund", headers=h(a))
        c.post(f"/api/v1/tasks/{t['id']}/deliver", headers=h(b))
        c.post(f"/api/v1/tasks/{t['id']}/accept-delivery", headers=h(a))
        wallet = c.get("/api/v1/wallet", headers=h(b)).json()
    return {"executor_id": bid, "executor_available_cents": wallet["available_cents"]}


def _pg_conn_args(url: str) -> list[str]:
    """把 SQLAlchemy URL 拆成 psql/pg_dump 的连接参数。"""
    from urllib.parse import parse_qs, urlparse

    u = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
    q = parse_qs(u.query)
    args = ["-d", (u.path or "/").lstrip("/") or "postgres"]
    host = q.get("host", [u.hostname])[0]
    if host:
        args += ["-h", host]
    port = q.get("port", [str(u.port) if u.port else ""])[0]
    if port:
        args += ["-p", port]
    if u.username:
        args += ["-U", u.username]
    return args


def _run_pg(cmd: list[str], **kw):
    import subprocess

    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def _pg_drill(url: str, before: dict) -> int:
    """Postgres 路径：用与 deploy/backup.sh / restore.sh **完全相同**的命令。"""
    import subprocess

    conn = _pg_conn_args(url)
    backup_dir = tempfile.mkdtemp(prefix="drill-backup-")
    dump = os.path.join(backup_dir, "snapshot.sql")

    print("② 备份（pg_dump --clean --if-exists，与 backup.sh 同参数）…")
    with open(dump, "w") as f:
        subprocess.run(["pg_dump", *conn, "--no-owner", "--clean", "--if-exists"],
                       check=True, stdout=f, text=True)
    print(f"   → {dump}（{os.path.getsize(dump)} 字节）")

    print("③ 删库（DROP SCHEMA public CASCADE——不是清表）…")
    _run_pg(["psql", *conn, "-v", "ON_ERROR_STOP=1", "-c",
             "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"])
    left = _run_pg(["psql", *conn, "-tAc",
                    "select count(*) from information_schema.tables "
                    "where table_schema='public'"]).stdout.strip()
    assert left == "0", f"库没删干净，还剩 {left} 张表"

    print("④ 恢复（psql -v ON_ERROR_STOP=1，与 restore.sh 同参数）…")
    with open(dump) as f:
        subprocess.run(["psql", *conn, "-v", "ON_ERROR_STOP=1"],
                       check=True, stdin=f, stdout=subprocess.DEVNULL, text=True)

    ok = _verify(before)
    shutil.rmtree(backup_dir, ignore_errors=True)
    return 0 if ok else 1


def _verify(before: dict) -> bool:
    print("⑤ 校验（与生产恢复跑的是同一段代码）…")
    from app.core.db import engine

    engine.dispose()          # 删库前连过旧库，必须重建连接池，否则校验的是缓存

    from scripts.consistency_check import check

    try:
        result = check()
    except Exception as exc:
        print(f"演练失败：恢复后的库读不出来（{type(exc).__name__}: {exc}）")
        return False
    print("   资金对账:", result["money"].get("ok"))
    print("   存证链:", result["chain"].get("valid"))

    from app.core.db import SessionLocal
    from app.modules.wallet.service import get_or_create

    with SessionLocal() as db:
        after = get_or_create(db, before["executor_id"]).available_cents
    print(f"   执行方余额 {after} 分（恢复前 {before['executor_available_cents']} 分）")
    return result["ok"] and after == before["executor_available_cents"]


def main() -> int:
    pg_url = os.environ.get("PLATFORM_DATABASE_URL", "")
    if pg_url.startswith("postgresql"):
        print(f"① 造一笔真实闭环交易（Postgres 路径）…")
        before = seed()
        assert before["executor_available_cents"] > 0, "演练数据没造出来"
        print(f"   执行方到账 {before['executor_available_cents']} 分")
        rc = _pg_drill(pg_url, before)
        print("演练通过：删库之后确实能把这笔交易原样恢复，且五条不变量成立。"
              if rc == 0 else "演练失败：备份恢复后数据或不变量对不上。")
        return rc

    _fresh_env()
    for leftover in (DRILL_DB, DRILL_DB + "-wal", DRILL_DB + "-shm"):
        if os.path.exists(leftover):
            os.remove(leftover)

    print("① 造一笔真实闭环交易…")
    before = seed()
    assert before["executor_available_cents"] > 0, "演练数据没造出来，后面的校验没有意义"
    print(f"   执行方到账 {before['executor_available_cents']} 分")

    print("② 备份…")
    backup_dir = tempfile.mkdtemp(prefix="drill-backup-")
    backup = os.path.join(backup_dir, "snapshot.db")
    # SQLite 的备份用 .backup 而不是文件复制：复制正在写的库可能拿到撕裂的页
    import sqlite3

    src = sqlite3.connect(DRILL_DB)
    dst = sqlite3.connect(backup)
    src.backup(dst)
    dst.close()
    src.close()
    print(f"   → {backup}（{os.path.getsize(backup)} 字节）")

    print("③ 删库（不是清表，是删文件——模拟机器没了）…")
    for f in (DRILL_DB, DRILL_DB + "-wal", DRILL_DB + "-shm"):
        if os.path.exists(f):
            os.remove(f)
    assert not os.path.exists(DRILL_DB)

    print("④ 恢复…")
    shutil.copy(backup, DRILL_DB)

    ok = _verify(before)
    shutil.rmtree(backup_dir, ignore_errors=True)
    for f in (DRILL_DB, DRILL_DB + "-wal", DRILL_DB + "-shm"):
        if os.path.exists(f):
            os.remove(f)

    if not ok:
        print("演练失败：备份恢复后数据或不变量对不上。")
        return 1
    print("演练通过：删库之后确实能把这笔交易原样恢复，且五条不变量成立。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
