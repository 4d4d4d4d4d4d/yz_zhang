"""DEP-050 定时任务驱动器（worker 容器的入口）。

按各自周期调用 job 端点。**不做业务逻辑**——业务全在 job 端点里，
这里只负责「按时敲门」，因此换成 K8s CronJob / Airflow 也是平移。

安全前提：所有 job 端点都要 `X-Job-Token`（OPS-011），且端点内部还有
DB 执行锁（CONC-040）——即便这个 worker 被误起多份也不会重复执行。
"""
import logging
import os
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("PLATFORM_API_BASE", "http://localhost:8000")
JOB_TOKEN = os.environ.get("PLATFORM_JOB_TOKEN", "dev-job-token-change-me")
PREFIX = "/api/v1"

# (路径, 周期秒)。周期按「延迟一个周期的业务代价」定：
# 自动验收、纠纷 SLA 直接关系资金滞留，跑勤一点；位置清理是合规保留期，一天一次够了。
JOBS: list[tuple[str, int]] = [
    (f"{PREFIX}/tasks/jobs/auto-accept", 300),
    (f"{PREFIX}/tasks/jobs/expire-tasks", 600),
    (f"{PREFIX}/tasks/jobs/settle-reviews", 3600),
    (f"{PREFIX}/tasks/jobs/deadline-alerts", 3600),
    (f"{PREFIX}/jobs/expire-unsigned", 3600),
    (f"{PREFIX}/disputes/jobs/escalate-overdue", 3600),
    (f"{PREFIX}/missions/jobs/tick-all", 300),
    (f"{PREFIX}/tasks/jobs/purge-locations", 86400),
    # LAW-011 存证锚定：一天一次足够，区间越大回执越少也越便宜
    (f"{PREFIX}/anchors/jobs/notarize", 86400),
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
