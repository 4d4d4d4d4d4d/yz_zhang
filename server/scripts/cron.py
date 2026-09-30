"""DEP-050 定时任务驱动器（worker 容器的入口）。

按各自周期调用 job 端点。**不做业务逻辑**——业务全在 job 端点里，
这里只负责「按时敲门」，因此换成 K8s CronJob / Airflow 也是平移。

安全前提：所有 job 端点都要 `X-Job-Token`（OPS-011），且端点内部还有
DB 执行锁（CONC-040）——即便这个 worker 被误起多份也不会重复执行。
"""
import logging
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("PLATFORM_API_BASE", "http://localhost:8000")
JOB_TOKEN = os.environ.get("PLATFORM_JOB_TOKEN", "dev-job-token-change-me")
PREFIX = "/api/v1"

# JOB-001 调度表**不再手抄**：直接读 app.core.jobs 里唯一的那份声明。
# 手抄的清单一定会漂移——上一版就漂出三处：资金对账根本不在表里、
# 签署超期作废的路径少了 /contracts 前缀（一直在打 404）、
# 而监控看不见「从未跑过」的 job，所以这些错了几个月也没人知道。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.jobs import JOBS as _DECLARED  # noqa: E402

JOBS: list[tuple[str, int]] = [
    (f"{PREFIX}{j.path}", j.period_seconds) for j in _DECLARED
]

log = logging.getLogger("cron")


def call(path: str) -> tuple[int, str]:
    req = urllib.request.Request(
        API_BASE + path, method="POST", data=b"",
        headers={"X-Job-Token": JOB_TOKEN, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read(500).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(500).decode("utf-8", "replace")
    except Exception as exc:  # 网络抖动不该让 worker 退出
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> None:
    from app.core.observability import setup_logging

    setup_logging(os.environ.get("PLATFORM_LOG_LEVEL", "INFO"))
    next_run = {path: 0.0 for path, _ in JOBS}
    log.info("cron worker 启动，API=%s，共 %d 个 job", API_BASE, len(JOBS))
    while True:
        now = time.monotonic()
        for path, period in JOBS:
            if now < next_run[path]:
                continue
            status, body = call(path)
            next_run[path] = now + period
            if status == 200:
                log.info("job ok %s %s", path, body[:200])
            elif status == 409:
                log.info("job skipped(其它实例在跑) %s", path)  # CONC-040 正常情形
            else:
                log.error("job failed %s status=%s %s", path, status, body[:200])
        time.sleep(10)


if __name__ == "__main__":
    main()
