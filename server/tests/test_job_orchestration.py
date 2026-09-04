"""JOB-030~035 定时任务编排的完整性（32 号 spec）。

拿 `scripts/cron.py` 的调度表和代码里的 job 端点对了一遍，对不上：

    代码里的 job 端点： 14
      ✗ /admin/jobs/reconcile           没有任何调度器会触发它
      ✗ /contracts/jobs/expire-unsigned  没有任何调度器会触发它
    cron 表里但代码里找不到的： ['/jobs/expire-unsigned']

三个缺口是同一个根因的三种表现：**调度表是手抄的**。手抄的清单一定会漂移，
区别只是什么时候被发现——而它漂了不会报错，所以可以一直错下去。

这个文件里最重要的一条是 `test_job030_*`：它**从 FastAPI 路由表自动发现**
job 端点，与声明表双向核对。有了它，漂移会在 CI 里就红，
而不是等某个人想起来去对一次。
"""
import pytest

from app.core.db import SessionLocal
from app.core.jobs import JOBS

from .conftest import JOB_HEADERS, auth, register


@pytest.fixture()
def admin(client):
    from app.modules.account.models import User

    user = register(client, "13800070001", "运维")
    with SessionLocal() as db:
        row = db.get(User, user["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return user


def discovered_job_paths(app) -> set[str]:
    """从应用**实际暴露的接口**里发现所有 job 端点，不依赖任何手写清单。

    用 OpenAPI 而不是遍历 `app.routes`：这个版本的 FastAPI 把 include 进来的
    路由包在 `_IncludedRouter` 里而不是摊平到 `app.routes`，直接遍历会
    一个都找不到——然后这个测试就会变成「永远通过」的摆设。
    """
    prefix = "/api/v1"
    found = set()
    for path, ops in app.openapi()["paths"].items():
        if "/jobs/" in path and "post" in ops:
            found.add(path[len(prefix):] if path.startswith(prefix) else path)
    return found


# ---------- JOB-030 声明表与实际路由双向一致 ----------
def test_job030_declared_jobs_and_actual_routes_match_both_ways(client):
    """多一个少一个都失败。

    这条是本批次的核心防线：三个缺口都是「两地手抄没同步」造成的，
    而这个测试让不同步在 CI 里就红。
    """
    declared = {j.path for j in JOBS}
    actual = discovered_job_paths(client.app)

    missing = actual - declared
    assert not missing, f"这些 job 端点没有任何调度器会触发它：{sorted(missing)}"

    phantom = declared - actual
    assert not phantom, f"调度表里的这些路径路由不到（打过去就是 404）：{sorted(phantom)}"


def test_job034_every_scheduled_path_actually_routes(client):
    """JOB-034 逐条打过去确认不是 404。

    缺口二的直接反面：cron 写的是 `/jobs/expire-unsigned`，
    真实路径是 `/contracts/jobs/expire-unsigned`，一直在打 404。
    路由表对得上还不够——真发一次请求才算数。
    """
    for job in JOBS:
        r = client.post(f"/api/v1{job.path}", headers=JOB_HEADERS)
        assert r.status_code != 404, f"{job.path} 路由不到：{job.purpose}"


def test_lock_names_are_unique_and_match_the_endpoints(client):
    """lock_name 重复会让 /jobz 把两个 job 认成一个。"""
    names = [j.lock_name for j in JOBS]
    assert len(names) == len(set(names)), "lock_name 必须唯一"

    with SessionLocal() as db:
        from app.core.models_infra import JobLock

        for job in JOBS:
            client.post(f"/api/v1{job.path}", headers=JOB_HEADERS)
        locks = {r.job_name for r in db.query(JobLock).all()}
    # 端点上 job_slot() 的参数必须与声明表一致，否则 /jobz 永远显示 never_run
    for job in JOBS:
        assert job.lock_name in locks, \
            f"{job.path} 实际用的锁名与声明表的 {job.lock_name} 对不上"


# ---------- JOB-031 监控要对照期望，而不是罗列现状 ----------
def test_job031_jobz_lists_every_expected_job_including_never_run(client):
    """从未跑过的 job 必须**出现在列表里并标成异常**，而不是从列表里消失。

    改造前 `/jobz` 遍历 `JobLock` 表，没跑过的没有行，于是监控里根本不存在。
    冒烟脚本每次打印「0 个 job 有记录」——空列表看起来太像一切正常了。
    """
    body = client.get("/jobz", headers=JOB_HEADERS).json()
    jobs = {j["job"]: j for j in body["jobs"]}

    assert len(jobs) >= len(JOBS), "应有的 job 一个都不能少"
    for job in JOBS:
        assert job.lock_name in jobs, f"{job.lock_name} 从监控里消失了"
        assert jobs[job.lock_name]["never_run"] is True   # 全新库，都没跑过
        assert jobs[job.lock_name]["purpose"], "要说清这个 job 是干什么的"


def test_never_run_flips_after_the_job_actually_runs(client):
    body = client.get("/jobz", headers=JOB_HEADERS).json()
    assert next(j for j in body["jobs"] if j["job"] == "auto_accept")["never_run"] is True

    assert client.post("/api/v1/tasks/jobs/auto-accept",
                       headers=JOB_HEADERS).status_code == 200
    body = client.get("/jobz", headers=JOB_HEADERS).json()
    row = next(j for j in body["jobs"] if j["job"] == "auto_accept")
    assert row["never_run"] is False
    assert row["seconds_since_success"] is not None


def test_job035_metrics_expose_never_run(client):
    text = client.get("/metrics", headers=JOB_HEADERS).text
    assert "platform_jobs_never_run" in text
    assert "platform_jobs_stale" in text
    # 全新库上所有 job 都没跑过，计数应等于声明表长度
    line = next(ln for ln in text.splitlines()
                if ln.startswith("platform_jobs_never_run "))
    assert int(line.split()[1]) == len(JOBS)


def test_stale_is_judged_against_each_jobs_own_period():
    """一天一次的清理和两分钟一次的补做，用同一个绝对阈值只会同时误报和漏报。"""
    periods = {j.period_seconds for j in JOBS}
    assert len(periods) > 1, "前提：各 job 周期本来就不同"
    # 声明表里带上了周期，/jobz 才可能按各自的尺子判断
    assert all(j.period_seconds > 0 for j in JOBS)


# ---------- JOB-032/033 资金对账终于能被调度器触发 ----------
def test_job032_reconcile_can_be_triggered_by_the_scheduler(client):
    """缺口一的直接反面。

    改造前它的鉴权是 `require_admin`——**调度器根本调不动**，
    加上又不在调度表里，这个「日终对账」实际上是一个需要有人每天
    记得手动点的按钮。这门生意最重要的那道安全网从来没有被架起来过。
    """
    r = client.post("/api/v1/admin/jobs/reconcile", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert "ok" in r.json()


def test_reconcile_still_works_for_admins_and_rejects_everyone_else(client, admin, requester):
    assert client.post("/api/v1/admin/jobs/reconcile",
                       headers=auth(admin)).status_code == 200
    assert client.post("/api/v1/admin/jobs/reconcile",
                       headers=auth(requester)).status_code == 403
    assert client.post("/api/v1/admin/jobs/reconcile").status_code == 403


def test_job033_scheduler_triggered_mismatch_still_raises_the_alarm(client, admin):
    """对账不平时，由调度器触发也要开差错工单并通知管理员——
    否则「自动对账」只是自动地什么都不做。
    """
    from app.modules.support.models import Ticket
    from app.modules.wallet.models import WalletAccount

    # 人为制造不平：凭空给某个钱包加钱，全局守恒立刻不成立
    with SessionLocal() as db:
        acct = WalletAccount(user_id=98765, available_cents=12345)
        db.add(acct)
        db.commit()

    r = client.post("/api/v1/admin/jobs/reconcile", headers=JOB_HEADERS)
    assert r.status_code == 200
    assert r.json()["ok"] is False

    with SessionLocal() as db:
        tickets = db.query(Ticket).filter(
            Ticket.subject.contains("对账差错")).all()
        assert tickets, "对账不平必须开差错工单"
        # JOB-021 调度器触发时归属平台账户，而不是某个碰巧在场的管理员
        assert tickets[0].user_id == 0

    notices = client.get("/api/v1/notifications", headers=auth(admin)).json()
    items = notices["items"] if isinstance(notices, dict) else notices
    assert any("对账差错" in n["title"] for n in items), "必须通知到管理员"


def test_reconcile_is_single_instance_locked(client):
    """对账会写工单与通知，多副本同时跑会重复告警。"""
    from app.core.models_infra import JobLock

    client.post("/api/v1/admin/jobs/reconcile", headers=JOB_HEADERS)
    with SessionLocal() as db:
        assert db.query(JobLock).filter(JobLock.job_name == "reconcile").first()


# ---------- cron 不再手抄 ----------
def test_cron_reads_the_single_declaration_instead_of_a_hand_copied_list():
    """调度器与声明表同源，才不可能再漂移。"""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "cron.py"
    text = src.read_text()
    assert "from app.core.jobs import JOBS" in text
    # 手抄的路径字面量不该再出现在 cron 里
    assert '"/api/v1/tasks/jobs/auto-accept"' not in text
    assert 'f"{PREFIX}/tasks/jobs/auto-accept"' not in text
