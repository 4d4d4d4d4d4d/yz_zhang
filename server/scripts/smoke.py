"""DEP-060 部署冒烟：对**已启动的实例**跑一遍主闭环并对账。

与单元测试的区别：这里打的是真实 HTTP 端口、真实容器、真实数据库，
验证的是「这套部署确实能做生意」，而不是「代码逻辑对」。

    python -m scripts.smoke                       # 默认 http://localhost:8000
    PLATFORM_API_BASE=http://api:8000 python -m scripts.smoke
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("PLATFORM_API_BASE", "http://localhost:8000")
JOB_TOKEN = os.environ.get("PLATFORM_JOB_TOKEN", "dev-job-token-change-me")
API = BASE + "/api/v1"
SUFFIX = str(int(time.time()))[-6:]


def req(method: str, path: str, body=None, token: str = "", headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(path if path.startswith("http") else API + path,
                                     data=data, method=method, headers=h)
    def _parse(status, raw):
        try:
            return status, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return status, {"raw": raw}

    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return _parse(resp.status, resp.read().decode())
    except urllib.error.HTTPError as exc:
        return _parse(exc.code, exc.read().decode())


def step(name: str, ok: bool, detail=""):
    text = str(detail)
    if len(text) > 300:
        text = text[:300] + "…"
    print(f"  {'✓' if ok else '✗'} {name}{'  ' + text if text else ''}")
    if not ok:
        sys.exit(1)


def main() -> None:
    print(f"冒烟目标：{BASE}")

    status, body = req("GET", BASE + "/readyz")
    step("就绪探针 /readyz", status == 200, body)
    status, version = req("GET", BASE + "/version")
    step("版本 /version", status == 200, version)

    # 注册两个账号并实名
    users = {}
    for role, phone in (("requester", f"199{SUFFIX}1"), ("worker", f"199{SUFFIX}2")):
        status, body = req("POST", "/auth/register",
                           {"phone": phone, "password": "smoke123456",
                            "nickname": f"冒烟-{role}", "sms_code": "123456"})
        step(f"注册 {role}", status == 201, body.get("user", {}).get("id"))
        users[role] = {"token": body["token"], "id": body["user"]["id"], "phone": phone}
        status, _ = req("POST", "/users/me/verify",
                        {"real_name": f"冒烟{role}", "id_number": f"11010119900101{body['user']['id']:04d}"},
                        token=users[role]["token"])
        step(f"实名 {role}", status == 200)

    r_tok, w_tok = users["requester"]["token"], users["worker"]["token"]

    status, body = req("POST", "/wallet/topup", {"amount_cents": 50000}, token=r_tok)
    step("充值 500 元", status == 200 and body.get("status") == "succeeded", body.get("status"))

    status, task = req("POST", "/tasks",
                       {"title": f"冒烟任务 {SUFFIX}", "description": "部署冒烟用，勿接",
                        "category": "跑腿", "budget_cents": 20000, "city": "杭州",
                        "lat": 30.2741, "lng": 120.1551, "address_hint": "西湖区"},
                       token=r_tok)
    step("发布任务", status == 201, task if status != 201 else task.get("id"))

    status, appl = req("POST", f"/tasks/{task['id']}/applications", {"message": "冒烟报名"}, token=w_tok)
    step("报名", status == 201, appl.get("id"))

    status, accepted = req("POST", f"/applications/{appl['id']}/accept", token=r_tok)
    step("选人成交", status == 200, accepted.get("contract_id"))
    cid = accepted["contract_id"]

    for role, token in (("requester", r_tok), ("worker", w_tok)):
        status, _ = req("POST", f"/contracts/{cid}/sign", token=token)
        step(f"签署 {role}", status == 200)

    status, _ = req("POST", f"/contracts/{cid}/fund", token=r_tok)
    step("托管资金", status == 200)

    status, _ = req("POST", f"/tasks/{task['id']}/deliver", token=w_tok)
    step("提交交付", status == 200)

    status, _ = req("POST", f"/tasks/{task['id']}/accept-delivery", token=r_tok)
    step("验收放款", status == 200)

    status, wallet = req("GET", "/wallet", token=w_tok)
    expected = 20000 - 20000 * 800 // 10000
    step("执行方到账（扣 8% 佣金）", wallet.get("available_cents") == expected,
         f"{wallet.get('available_cents')} == {expected}")

    # 闭环结束后托管必须清零——用指标端点验证，无需管理员账号
    status, metrics = req("GET", BASE + "/metrics", headers={"X-Job-Token": JOB_TOKEN})
    text = metrics.get("raw", "") if isinstance(metrics, dict) else ""
    escrow = next((line for line in text.splitlines()
                   if line.startswith("platform_escrow_cents ")), "")
    step("指标端点可用", status == 200 and bool(escrow), escrow or metrics)
    step("闭环后托管清零", escrow.split()[-1] == "0", escrow)

    status, jobs = req("GET", BASE + "/jobz", headers={"X-Job-Token": JOB_TOKEN})
    rows = jobs.get("jobs", [])
    step("job 健康端点", status == 200, f"{len(rows)} 个 job 在册")
    # JOB-031 这一行以前打印的是「0 个 job 有记录」，而我读过很多遍都当成了正常输出——
    # 空列表看起来太像一切正常了。现在它必须**列全**应有的 job，
    # 一个都不能少，否则「有 job 从来没被调度过」这件事又会没人发现
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.core.jobs import JOBS as DECLARED

    listed = {r["job"] for r in rows}
    missing = {j.lock_name for j in DECLARED} - listed
    step("全部应有 job 都在监控里", not missing, f"缺失：{sorted(missing)}")

    print("冒烟通过：这套部署能完成一笔真实交易并正确分账。")


if __name__ == "__main__":
    main()
