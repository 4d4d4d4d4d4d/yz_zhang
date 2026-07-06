"""工程硬化：14.6/05.B 资金幂等 / ACC-001 防刷限流 / 越权访问拒绝"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import CLEAN_TASK, match_and_fund, publish_task


# ---------- 资金操作幂等（14.6/05.B） ----------
def test_topup_idempotency(client, requester):
    key = "topup-abc-123"
    r1 = client.post("/api/v1/wallet/topup", json={"amount_cents": 10000},
                     headers={**auth(requester), "Idempotency-Key": key})
    r2 = client.post("/api/v1/wallet/topup", json={"amount_cents": 10000},
                     headers={**auth(requester), "Idempotency-Key": key})
    assert r1.json() == r2.json()
    # 重复提交只入账一次
    w = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert w["available_cents"] == 10000
    # 不同 key 正常累加
    client.post("/api/v1/wallet/topup", json={"amount_cents": 5000},
                headers={**auth(requester), "Idempotency-Key": "topup-xyz"})
    w = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert w["available_cents"] == 15000


def test_withdraw_idempotency(client, requester):
    topup(client, requester, 20000)
    key = "wd-1"
    r1 = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 8000},
                     headers={**auth(requester), "Idempotency-Key": key})
    r2 = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 8000},
                     headers={**auth(requester), "Idempotency-Key": key})
    assert r1.json() == r2.json()
    w = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert w["available_cents"] == 12000  # 只提一次


def test_idempotency_scoped_per_user(client, requester, worker):
    # 同一 key 在不同用户间互不干扰
    client.post("/api/v1/wallet/topup", json={"amount_cents": 3000},
                headers={**auth(requester), "Idempotency-Key": "shared"})
    client.post("/api/v1/wallet/topup", json={"amount_cents": 7000},
                headers={**auth(worker), "Idempotency-Key": "shared"})
    assert client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"] == 3000
    assert client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"] == 7000


# ---------- 认证防刷（ACC-001） ----------
def test_acc001_register_rate_limit(client):
    # 同手机号 60s 内注册尝试限流（第 4 次被拒）
    ok = 0
    for i in range(5):
        r = client.post("/api/v1/auth/register", json={
            "phone": "15000000001", "password": "pass123456",
            "nickname": f"n{i}", "sms_code": "000000",  # 故意错码，仍计入尝试
        })
        if r.status_code == 400 and r.json()["detail"]["code"] == "rate_limited":
            break
        ok += 1
    assert ok == 3  # 前 3 次放行（都因错码失败），第 4 次限流


def test_acc001_sms_login_rate_limit(client):
    hit = False
    for _ in range(7):
        r = client.post("/api/v1/auth/login-sms",
                        json={"phone": "15000000002", "sms_code": "000000"})
        if r.status_code == 400 and r.json()["detail"]["code"] == "rate_limited":
            hit = True
            break
    assert hit  # 5 次后触发限流


# ---------- 越权访问拒绝（资源级鉴权，14.6） ----------
def test_cross_user_authorization_denied(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    stranger = register(client, "15000000003", "路人")
    verify_user(client, stranger, "路人甲")

    # 路人不能看别人任务的报名列表
    r = client.get(f"/api/v1/tasks/{task['id']}/applications", headers=auth(stranger))
    assert r.status_code == 403
    # 路人不能查看别人任务的 AI 推荐
    r = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(stranger))
    assert r.status_code == 403

    contract_id = match_and_fund(client, requester, worker, task)
    # 路人不能查看别人合约
    r = client.get(f"/api/v1/contracts/{contract_id}", headers=auth(stranger))
    assert r.status_code == 403
    # 路人不能导出别人合约凭证
    r = client.get(f"/api/v1/contracts/{contract_id}/export", headers=auth(stranger))
    assert r.status_code == 403
    # 路人不能打卡/交付别人的任务
    r = client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(stranger))
    assert r.status_code == 403
    # 路人不能进任务会话
    convs = client.get("/api/v1/conversations", headers=auth(worker)).json()
    conv_id = convs[0]["id"]
    r = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth(stranger))
    assert r.status_code == 403


def test_admin_only_endpoints_reject_regular_user(client, requester):
    for path in ["/api/v1/admin/metrics", "/api/v1/admin/reports",
                 "/api/v1/admin/funnels", "/api/v1/admin/jobs/reconcile"]:
        method = client.post if "reconcile" in path else client.get
        r = method(path, headers=auth(requester))
        assert r.status_code == 403, path
