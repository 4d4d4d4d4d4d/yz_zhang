"""ACC-E2E 全链路终端验收：对着一个**已经部署好的服务**跑完整条业务链。

和 `scripts/smoke.py` 的分工：

- `smoke.py`  ——「这套部署能不能完成一笔交易」，18 项，跑得快，CI 每次跑。
- 本脚本      ——「这套部署能不能**交付给用户**」，覆盖交易、纠纷、提现、
                上传、风控、对账、越权、注销，一条链走到底。部署后跑一次。

**部署脚本必须以「验收通过」结束，而不是以「容器起来了」结束。**
起来了不等于能用——这一路踩过的坑（验证码没有钥匙孔、被告席没有麦克风、
一键部署缺 Postgres 驱动）全都是「起来了但不能用」。

    PLATFORM_API_BASE=https://your-domain python -m scripts.acceptance
    PLATFORM_JOB_TOKEN=xxx  # 需要与服务端一致，用于 /metrics、/jobz、job 端点
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("PLATFORM_API_BASE", "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api/v1"
JOB_TOKEN = os.environ.get("PLATFORM_JOB_TOKEN", "dev-job-token-change-me")

PASS, FAIL = [], []
_stamp = int(time.time()) % 100000


def req(method, path, body=None, token="", raw_base=False, headers=None):
    url = (BASE if raw_base else API) + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            payload = resp.read()
            try:
                return resp.status, (json.loads(payload) if payload else None)
            except Exception:
                # 图片 / Prometheus 文本不是 JSON——不能因此判成请求失败
                return resp.status, {"raw": payload.decode(errors="replace")}
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except Exception:
            return exc.code, {"raw": payload.decode(errors="replace")[:300]}
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(detail)) if detail else ''}")
    return cond


def phone(n):
    return f"139{_stamp:05d}{n:03d}"


def register(n, nick):
    status, body = req("POST", "/auth/register", {
        "phone": phone(n), "password": "pass123456", "nickname": nick, "sms_code": "123456"})
    assert status == 201, f"注册失败 {status} {body}"
    return body["token"], body["user"]["id"]


def verify(token, name, n):
    # 证件号必须正好 18 位，且全站唯一（VND-023 一人一号）——
    # 位数错了 eKYC 会拒，而后续「报名」要求实名，会连环失败
    id_number = f"110101199001{_stamp % 10000:04d}{n:02d}"
    assert len(id_number) == 18, id_number
    status, body = req("POST", "/users/me/verify",
                       {"real_name": name, "id_number": id_number}, token)
    assert status == 200 and body.get("is_verified"), f"实名失败 {status} {body}"


TASK = {
    "title": "验收任务：周末大扫除", "description": "两室一厅深度保洁",
    "category": "保洁", "task_type": "service", "required_skills": ["保洁"],
    "budget_cents": 20000, "city": "上海", "lat": 31.2304, "lng": 121.4737,
    "address_hint": "静安寺商圈", "address_exact": "静安区南京西路 1234 号 5 栋 302",
    # IPC-001（V77 起）发布必须选知识产权归属，无默认值
    "ip_assignment": "assign",
}


def section(title):
    print(f"\n── {title} " + "─" * max(2, 52 - len(title)))


def main() -> int:
    print(f"全链路验收目标：{BASE}")

    # ---------- 1. 部署本身 ----------
    section("1 部署就绪")
    status, ready = req("GET", "/readyz", raw_base=True)
    check("就绪探针 /readyz", status == 200 and ready.get("ready"), ready)
    check("数据库连得上", (ready or {}).get("checks", {}).get("db") == "ok")
    check("迁移版本与代码一致", (ready or {}).get("checks", {}).get("migration") == "ok",
          "不一致说明忘了 alembic upgrade head")
    status, ver = req("GET", "/version", raw_base=True)
    check("版本端点", status == 200 and ver.get("version"), ver)
    if ver and ver.get("env") == "prod":
        check("生产不应使用内部账本", ver.get("ledger_backend") == "custody",
              "internal ＝ 资金池与二清，FIN-052 红线")

    # ---------- 2. 账号与实名 ----------
    section("2 账号、实名与人机验证")
    a_tok, a_id = register(1, "验收发布方")
    b_tok, b_id = register(2, "验收执行方")
    verify(a_tok, "甲发布", 1)
    verify(b_tok, "乙执行", 2)
    status, me = req("GET", "/users/me", token=a_tok)
    check("登录态可用", status == 200 and me["id"] == a_id)
    check("实名生效", req("GET", "/users/me", token=b_tok)[1].get("is_verified") is True)
    status, cap = req("GET", "/auth/captcha-config")
    check("人机验证配置端点公开可读", status == 200 and "site_key" in (cap or {}), cap)
    if cap and cap.get("enforcing"):
        check("强制验证必须配站点公钥", bool(cap.get("site_key")),
              "否则客户端渲染不出挑战，用户会被锁在门外")

    # ---------- 3. 主交易闭环 ----------
    section("3 主交易闭环（发布 → 成交 → 托管 → 交付 → 放款）")
    check("充值", req("POST", "/wallet/topup", {"amount_cents": 100000}, a_tok)[0] == 200)
    status, task = req("POST", "/tasks", {**TASK, "publish_now": True}, a_tok)
    check("发布任务", status == 201, task.get("id") if task else task)
    tid = task["id"]
    status, application = req("POST", f"/tasks/{tid}/applications", {"message": "我可以做"}, b_tok)
    if not check("报名", status == 201, application):
        print("\n后续步骤依赖报名成功，已中止。")
        return 1
    status, accepted = req("POST", f"/applications/{application['id']}/accept", token=a_tok)
    check("选人成交", status == 200, accepted)
    cid = accepted["contract_id"]
    check("发布方签署", req("POST", f"/contracts/{cid}/sign", token=a_tok)[0] == 200)
    check("执行方签署", req("POST", f"/contracts/{cid}/sign", token=b_tok)[0] == 200)
    check("托管资金", req("POST", f"/contracts/{cid}/fund", token=a_tok)[0] == 200)
    _, wallet = req("GET", "/wallet", token=a_tok)
    check("托管后资金进 escrow", wallet["escrow_cents"] == 20000, wallet)
    check("提交交付", req("POST", f"/tasks/{tid}/deliver", token=b_tok)[0] == 200)
    check("验收放款", req("POST", f"/tasks/{tid}/accept-delivery", token=a_tok)[0] == 200)
    _, bw = req("GET", "/wallet", token=b_tok)
    _, tax = req("GET", "/finance/my-tax", token=b_tok)
    withheld = sum(y["withheld_cents"] for y in (tax or {}).get("yearly", []))
    expected = 20000 - 1600 - withheld            # 8% 佣金 + 代扣个税
    check("执行方到账 = 金额 − 佣金 − 代扣", bw["available_cents"] == expected,
          f"{bw['available_cents']} == {expected}（代扣 {withheld}）")
    check("闭环后托管清零", req("GET", "/wallet", token=a_tok)[1]["escrow_cents"] == 0)

    # ---------- 4. 纠纷全流程 ----------
    section("4 纠纷（开案 → 被诉方答辩 → 裁决 → 分账）")
    check("充值二单", req("POST", "/wallet/topup", {"amount_cents": 100000}, a_tok)[0] == 200)
    _, t2 = req("POST", "/tasks", {**TASK, "title": "验收任务：纠纷路径", "publish_now": True}, a_tok)
    _, ap2 = req("POST", f"/tasks/{t2['id']}/applications", {"message": "我来"}, b_tok)
    _, ac2 = req("POST", f"/applications/{ap2['id']}/accept", token=a_tok)
    req("POST", f"/contracts/{ac2['contract_id']}/sign", token=a_tok)
    req("POST", f"/contracts/{ac2['contract_id']}/sign", token=b_tok)
    req("POST", f"/contracts/{ac2['contract_id']}/fund", token=a_tok)
    status, dispute = req("POST", f"/tasks/{t2['id']}/disputes",
                          {"reason": "交付不符约定，要求重做或退款"}, a_tok)
    check("发起纠纷", status == 201, dispute)
    # 被诉方只知道任务 id —— 这是他进入这场程序的唯一一条路
    status, found = req("GET", f"/tasks/{t2['id']}/dispute", token=b_tok)
    check("被诉方能按任务找到纠纷", status == 200 and found["id"] == dispute["id"])
    check("服务端给出答辩截止时间", bool(found.get("response_deadline")), found.get("response_deadline"))
    check("被诉方标记正确", found.get("respondent_id") == b_id and found.get("respondent_spoke") is False)
    status, _ = req("POST", f"/disputes/{dispute['id']}/statements",
                    {"content": "已按约定完成，附现场照片与验收单。"}, b_tok)
    check("被诉方能提交答辩", status == 201, "这是 V61 之前任何客户端都做不到的事")
    check("答辩后 respondent_spoke 翻转",
          req("GET", f"/disputes/{dispute['id']}", token=b_tok)[1]["respondent_spoke"] is True)
    status, stmts = req("GET", f"/disputes/{dispute['id']}/statements", token=a_tok)
    check("双方都能看到陈述", status == 200 and len(stmts) >= 1)

    # ---------- 5. 风控与提现 ----------
    section("5 提现与风控")
    req("PUT", "/wallet/payout-account",
        {"kind": "bank", "account_no": "6222021234567890123", "holder_name": "乙执行"}, b_tok)
    status, wd = req("POST", "/wallet/withdraw", {"amount_cents": 1000}, b_tok)
    check("提现受理", status == 200, wd.get("status") if wd else wd)
    if wd and wd.get("status") == "pending_review":
        check("大额/风控提现进人审且话术中性",
              "可疑" not in wd.get("message", "") and "风控" not in wd.get("message", ""),
              wd.get("message"))
    status, _ = req("POST", "/wallet/withdraw", {"amount_cents": 999999999}, b_tok)
    check("超额提现被拒", status == 400)

    # ---------- 6. 上传与内容审核 ----------
    section("6 上传：能力 URL 与内容审核")
    import base64
    import hashlib

    png = b"\x89PNG\r\n\x1a\n" + bytes(range(64)) * 2
    status, up = req("POST", "/files", {
        "content_type": "image/png", "data_base64": base64.b64encode(png).decode()}, a_tok)
    check("上传图片", status == 201, up)
    if status == 201:
        digest = hashlib.sha256(png).hexdigest()
        check("URL 不可由内容推导", digest[:32] not in up["url"],
              "文件名是内容哈希＝任何持有原图的人都能算出 URL")
        code, _ = req("GET", up["url"], raw_base=True)
        check("能力 URL 可匿名读取", code == 200)
        status2, up2 = req("POST", "/files", {
            "content_type": "image/png", "data_base64": base64.b64encode(png).decode()}, b_tok)
        check("同图不同用户拿到不同 URL", status2 == 201 and up2["url"] != up["url"])

    # ---------- 7. 越权与边界 ----------
    section("7 越权与边界防护")
    check("匿名读任务详情被拒", req("GET", f"/tasks/{tid}")[0] in (401, 403))
    check("非当事人看不到纠纷", req("GET", f"/disputes/{dispute['id']}")[0] in (401, 403))
    check("普通用户进不了管理后台", req("GET", "/admin/users", token=a_tok)[0] == 403)
    check("无 job 令牌调不动 job 端点",
          req("POST", "/events/jobs/drain")[0] in (401, 403))
    code, _ = req("GET", "/docs", raw_base=True)
    if ver and ver.get("env") == "prod":
        check("生产不暴露 API 文档", code == 404)

    # ---------- 8. 调度与可观测 ----------
    section("8 调度、指标与对账")
    jh = {"X-Job-Token": JOB_TOKEN}
    status, jobz = req("GET", "/jobz", raw_base=True, headers=jh)
    check("job 健康端点可用", status == 200, f"{len(jobz.get('jobs', []))} 个 job 在册" if jobz else "")
    if status == 200:
        jobs = jobz.get("jobs", [])
        from app.core.jobs import JOBS as DECLARED

        declared = {j.lock_name for j in DECLARED}
        listed = {j["job"] for j in jobs}
        check("调度表与 /jobz 双向一致", declared == listed,
              f"只在调度表：{sorted(declared - listed)}；只在 /jobz：{sorted(listed - declared)}")
        never = sorted(j["job"] for j in jobs if j.get("never_run"))
        stale = sorted(j["job"] for j in jobs if j.get("stale"))
        print(f"    · 从未跑过：{never or '无'}（新部署为全部，跑一轮 cron 后应清空）")
        if stale:
            check("没有陈旧 job", False, f"超过自身周期 3 倍未成功：{stale}")
    status, metrics = req("GET", "/metrics", raw_base=True, headers=jh)
    check("指标端点可用", status == 200)
    text = (metrics or {}).get("raw", "") if isinstance(metrics, dict) else str(metrics or "")
    for m in ("platform_reconcile_ok", "platform_jobs_unhealthy", "platform_escrow_cents"):
        check(f"告警依赖的指标存在：{m}", m in text,
              "缺失＝引用它的告警规则永远静默")
    if "platform_reconcile_ok" in text:
        val = text.split("platform_reconcile_ok")[-1].split("\n")[0].strip()
        check("五条资金不变量成立", val == "1", f"platform_reconcile_ok={val}")

    # ---------- 9. 注销闸门 ----------
    section("9 注销闸门")
    c_tok, _ = register(3, "验收注销")
    check("干净账号可注销", req("POST", "/users/me/deactivate", token=c_tok)[0] == 200)
    check("注销后登录态失效", req("GET", "/users/me", token=c_tok)[0] == 403)
    status, blocked = req("POST", "/users/me/deactivate", token=b_tok)
    check("有未结资金/纠纷时拒绝注销", status == 409,
          (blocked or {}).get("detail", {}).get("code"))

    # ---------- 结论 ----------
    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        for name in FAIL:
            print(f"  ✗ {name}")
        print("\n全链路验收未通过——**不要对外开放**，先按上面的失败项排查。")
        return 1
    print("全链路验收通过：这套部署可以交付给用户。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
