"""DRILL-030 压测：把「不知道能扛多少」变成一个数字。

此前这套系统的并发**正确性**有测试钉着（行锁 + 乐观锁 + 状态机，
`test_concurrency_guards.py`），但**容量一无所知**：不知道单副本能扛多少
QPS、不知道瓶颈在哪、不知道 p95 是 20ms 还是 2s。

「有并发测试」和「知道能扛多少」是两件事。前者防的是算错钱，
后者防的是上线当天被正常流量打垮——而后者从来没有人量过。

只用标准库（不引入 locust/k6：CI 里多一个依赖就多一个不跑的理由）。

    # 先起一个服务
    PLATFORM_API_BASE=http://127.0.0.1:8000 python -m scripts.loadtest
    python -m scripts.loadtest --concurrency 32 --requests 2000 --scenario read

场景：
    read   （默认）广场列表 + 任务详情——最高频的只读路径
    write  发布任务——带鉴权与写库的路径
"""
import argparse
import json
import os
import statistics
import threading
import time
import urllib.error
import urllib.request

BASE = os.environ.get("PLATFORM_API_BASE", "http://127.0.0.1:8000")
API = BASE + "/api/v1"


def req(method: str, path: str, body=None, token: str = "") -> tuple[int, dict | list | None, float]:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else None), time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        return exc.code, None, time.perf_counter() - started
    except Exception:
        return 0, None, time.perf_counter() - started


def setup() -> tuple[str, int]:
    """造一个账号和一条已发布任务，供压测读写。"""
    phone = f"139{int(time.time()) % 100000000:08d}"
    status, body, _ = req("POST", "/auth/register", {
        "phone": phone, "password": "pass123456", "nickname": "压测", "sms_code": "123456"})
    assert status == 201 and body, f"注册失败：{status}"
    token = body["token"]
    status, task, _ = req("POST", "/tasks", {
        "title": "压测任务：周末大扫除", "description": "两室一厅深度保洁",
        "category": "保洁", "task_type": "service", "required_skills": ["保洁"],
        "budget_cents": 20000, "city": "上海", "lat": 31.2304, "lng": 121.4737,
        "address_hint": "静安寺商圈", "address_exact": "静安区南京西路 1234 号 5 栋 302",
        "publish_now": True}, token)
    assert status == 201 and task, f"发布失败：{status}"
    return token, task["id"]


def run(concurrency: int, total: int, scenario: str, token: str, task_id: int) -> dict:
    lock = threading.Lock()
    latencies: list[float] = []
    codes: dict[int, int] = {}
    remaining = [total]

    def worker():
        while True:
            with lock:
                if remaining[0] <= 0:
                    return
                remaining[0] -= 1
            if scenario == "write":
                status, _, dt = req("POST", "/tasks", {
                    "title": "压测写入：周末大扫除", "description": "两室一厅深度保洁",
                    "category": "保洁", "task_type": "service", "required_skills": ["保洁"],
                    "budget_cents": 20000, "city": "上海", "lat": 31.2304, "lng": 121.4737,
                    "address_hint": "静安寺商圈",
                    "address_exact": "静安区南京西路 1234 号 5 栋 302"}, token)
            else:
                status, _, dt = req("GET", f"/tasks/{task_id}", token=token)
            with lock:
                latencies.append(dt)
                codes[status] = codes.get(status, 0) + 1

    started = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - started

    latencies.sort()

    def pct(p):
        return latencies[min(int(len(latencies) * p), len(latencies) - 1)] * 1000

    ok = sum(n for c, n in codes.items() if 200 <= c < 300)
    return {
        "scenario": scenario, "concurrency": concurrency, "requests": len(latencies),
        "elapsed_s": round(elapsed, 2),
        "throughput_rps": round(len(latencies) / elapsed, 1) if elapsed else 0,
        "ok": ok, "error_rate": round(1 - ok / max(len(latencies), 1), 4),
        "p50_ms": round(pct(0.50), 1), "p95_ms": round(pct(0.95), 1),
        "p99_ms": round(pct(0.99), 1),
        "mean_ms": round(statistics.mean(latencies) * 1000, 1),
        "codes": dict(sorted(codes.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--requests", type=int, default=500)
    ap.add_argument("--scenario", choices=["read", "write"], default="read")
    args = ap.parse_args()

    print(f"压测目标：{BASE}（{args.scenario} 场景，并发 {args.concurrency}，共 {args.requests} 次）")
    token, task_id = setup()
    result = run(args.concurrency, args.requests, args.scenario, token, task_id)
    for k, v in result.items():
        print(f"  {k:14} {v}")
    # 这里**不设阈值断言**：容量取决于机器，写死一个数字只会在别人的机器上误报。
    # 这个脚本的职责是给出数字，判断由看数字的人来做。
    if result["error_rate"] > 0.5:
        print("错误率过半——大概率是服务没起来或被限流打满，数字不可用。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
