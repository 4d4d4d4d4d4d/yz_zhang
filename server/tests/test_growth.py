"""GRW-070~074 增长运营验证（22 号 spec）。

补贴是唯一能凭空「造钱」的功能——因此这里的重点全部围绕一件事：
**每一分补贴都能追到出资方，资金四不变量恒成立**。
其次是防薅：一单一券、一人一券、仅一级分销、预算硬顶。
"""
from app.core.db import SessionLocal

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def make_admin(client, phone="13800006999", nickname="运营"):
    from app.modules.account.models import User

    admin = register(client, phone, nickname)
    with SessionLocal() as db:
        row = db.get(User, admin["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return admin


def fund_pool(client, admin, amount=100000):
    r = client.post("/api/v1/admin/subsidy-pool/fund",
                    json={"amount_cents": amount}, headers=auth(admin))
    assert r.status_code == 200, r.text
    return r.json()


def new_coupon(client, admin, **over):
    body = {"title": "满100减20", "kind": "requester_discount", "amount_cents": 2000,
            "min_order_cents": 10000, "per_user_limit": 1, "valid_days": 30}
    body.update(over)
    r = client.post("/api/v1/admin/coupons", json=body, headers=auth(admin))
    assert r.status_code == 201, r.text
    return r.json()


def claim(client, user, coupon_id):
    r = client.post(f"/api/v1/coupons/{coupon_id}/claim", headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def reconcile(client, admin):
    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin))
    assert r.status_code == 200, r.text
    return r.json()


def sign_and_get_contract(client, requester, worker, task):
    r = client.post(f"/api/v1/tasks/{task['id']}/applications",
                    json={"message": "我来"}, headers=auth(worker))
    app_id = r.json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept",
                      headers=auth(requester)).json()["contract_id"]
    for u in (requester, worker):
        assert client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(u)).status_code == 200
    return cid


# ---------- GRW-003/070 补贴资金口径 ----------
def test_coupon_redemption_keeps_money_invariants(client, requester, worker):
    """核销后：平台账户被真实扣减、发布方少掏钱、资金四不变量成立。"""
    admin = make_admin(client)
    fund_pool(client, admin, 100000)
    coupon = new_coupon(client, admin)

    topup(client, requester, 100000)
    uc = claim(client, requester, coupon["id"])

    task = publish_task(client, requester, budget_cents=50000)
    cid = sign_and_get_contract(client, requester, worker, task)

    before = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    r = client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc['id']}",
                    headers=auth(requester))
    assert r.status_code == 200, r.text
    assert r.json()["coupon_discount_cents"] == 2000

    after = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    # 托管 50000，但补贴 2000 先到账 → 净扣 48000
    assert after == before - 50000 + 2000

    finance = client.get("/api/v1/admin/finance", headers=auth(admin))
    if finance.status_code == 200:
        assert finance.json()["balance_cents"] == 100000 - 2000

    assert reconcile(client, admin)["ok"] is True


def test_coupon_cannot_exceed_subsidy_pool(client, requester, worker):
    """平台补贴池不足 → 核销失败，绝不透支（补贴不能凭空生成）。"""
    admin = make_admin(client)
    fund_pool(client, admin, 500)  # 池子里只有 5 元
    coupon = new_coupon(client, admin)

    topup(client, requester, 100000)
    uc = claim(client, requester, coupon["id"])
    task = publish_task(client, requester, budget_cents=50000)
    cid = sign_and_get_contract(client, requester, worker, task)

    r = client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc['id']}",
                    headers=auth(requester))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "subsidy_pool_exhausted"
    # 失败即零副作用：券仍可用、钱没动
    assert client.get("/api/v1/me/coupons", headers=auth(requester)).json()["coupons"][0]["status"] == "unused"
    assert reconcile(client, admin)["ok"] is True


# ---------- GRW-071 一单一券 / 一人限领 ----------
def test_one_coupon_per_order(client, requester, worker):
    admin = make_admin(client)
    fund_pool(client, admin)
    c1 = new_coupon(client, admin, title="券A")
    c2 = new_coupon(client, admin, title="券B")

    topup(client, requester, 200000)
    uc1 = claim(client, requester, c1["id"])
    uc2 = claim(client, requester, c2["id"])

    task = publish_task(client, requester, budget_cents=50000)
    cid = sign_and_get_contract(client, requester, worker, task)
    assert client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc1['id']}",
                       headers=auth(requester)).status_code == 200
    r = client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc2['id']}",
                    headers=auth(requester))
    assert r.status_code == 409  # 合约已托管，状态机先拦；券也未被消耗
    used = {c["id"]: c for c in client.get("/api/v1/me/coupons",
                                           headers=auth(requester)).json()["coupons"]}
    assert used[uc2["id"]]["status"] == "unused"


def test_per_user_claim_limit(client, requester):
    admin = make_admin(client)
    coupon = new_coupon(client, admin, per_user_limit=1)
    claim(client, requester, coupon["id"])
    r = client.post(f"/api/v1/coupons/{coupon['id']}/claim", headers=auth(requester))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "per_user_limit"


def test_claim_requires_verification(client):
    """未实名不得领券——否则批量注册即可薅。"""
    admin = make_admin(client)
    coupon = new_coupon(client, admin)
    user = register(client, "13800006001", "未实名")
    r = client.post(f"/api/v1/coupons/{coupon['id']}/claim", headers=auth(user))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "verification_required"


def test_quota_exhausted(client):
    admin = make_admin(client)
    coupon = new_coupon(client, admin, total_quota=1)
    a = register(client, "13800006002", "甲")
    b = register(client, "13800006003", "乙")
    verify_user(client, a)
    verify_user(client, b)
    claim(client, a, coupon["id"])
    r = client.post(f"/api/v1/coupons/{coupon['id']}/claim", headers=auth(b))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "coupon_exhausted"


def test_min_order_enforced(client, requester, worker):
    admin = make_admin(client)
    fund_pool(client, admin)
    coupon = new_coupon(client, admin, min_order_cents=100000)  # 满 1000 元可用
    topup(client, requester, 100000)
    uc = claim(client, requester, coupon["id"])
    task = publish_task(client, requester, budget_cents=20000)
    cid = sign_and_get_contract(client, requester, worker, task)
    r = client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc['id']}",
                    headers=auth(requester))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "below_min_order"


# ---------- GRW-001 券模板校验 ----------
def test_percent_coupon_requires_cap(client):
    admin = make_admin(client)
    r = client.post("/api/v1/admin/coupons",
                    json={"title": "9折", "percent_bps": 1000, "max_discount_cents": 0},
                    headers=auth(admin))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "percent_needs_cap"


def test_percent_coupon_capped(client, requester, worker):
    """比例券必须按封顶截断，否则大额单会把预算烧光。"""
    admin = make_admin(client)
    fund_pool(client, admin)
    coupon = new_coupon(client, admin, title="9折封顶30",
                        amount_cents=0, percent_bps=1000, max_discount_cents=3000)
    topup(client, requester, 200000)
    uc = claim(client, requester, coupon["id"])
    task = publish_task(client, requester, budget_cents=100000)  # 10% = 10000，应被截到 3000
    cid = sign_and_get_contract(client, requester, worker, task)
    r = client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc['id']}",
                    headers=auth(requester))
    assert r.json()["coupon_discount_cents"] == 3000
    assert reconcile(client, admin)["ok"] is True


# ---------- GRW-002 取消退券 ----------
def test_cancel_returns_coupon_and_subsidy(client, requester, worker):
    admin = make_admin(client)
    fund_pool(client, admin, 100000)
    coupon = new_coupon(client, admin)
    topup(client, requester, 100000)
    uc = claim(client, requester, coupon["id"])

    task = publish_task(client, requester, budget_cents=50000)
    cid = sign_and_get_contract(client, requester, worker, task)
    client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc['id']}",
                headers=auth(requester))
    r = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(requester))
    assert r.status_code == 200, r.text

    rows = client.get("/api/v1/me/coupons", headers=auth(requester)).json()["coupons"]
    assert rows[0]["status"] == "unused", "取消后券必须退回，不能因平台侧原因白丢"
    assert rows[0]["contract_id"] is None
    assert reconcile(client, admin)["ok"] is True


# ---------- GRW-072/073 邀请奖励 ----------
def _register_with_ref(client, phone, code, nickname="被邀请"):
    r = client.post("/api/v1/auth/register",
                    json={"phone": phone, "password": "pass123456", "nickname": nickname,
                          "sms_code": "123456", "referral_code": code})
    assert r.status_code == 201, r.text
    return {"token": r.json()["token"], "id": r.json()["user"]["id"]}


def test_referral_pays_only_after_first_completed_order(client):
    """GRW-012 注册不发奖，完成首单才发——注册即奖是刷号的邀请函。"""
    admin = make_admin(client)
    fund_pool(client, admin, 100000)

    inviter = register(client, "13800006101", "邀请人")
    verify_user(client, inviter)
    code = client.get("/api/v1/users/me", headers=auth(inviter)).json()["referral_code"]

    invitee = _register_with_ref(client, "13800006102", code)
    verify_user(client, invitee)

    stats = client.get("/api/v1/me/referrals", headers=auth(inviter)).json()
    assert stats["invited_count"] == 1
    assert stats["achieved_count"] == 0
    assert stats["earned_cents"] == 0  # 仅注册，不发钱

    # 被邀请人作为执行者完成首单
    topup(client, inviter, 100000)
    task = publish_task(client, inviter, budget_cents=30000)
    match_and_fund(client, inviter, invitee, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(invitee))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(inviter))

    stats = client.get("/api/v1/me/referrals", headers=auth(inviter)).json()
    assert stats["achieved_count"] == 1
    assert stats["earned_cents"] == 1000
    assert stats["levels"] == 1
    assert reconcile(client, admin)["ok"] is True


def test_referral_is_single_level_only(client):
    """GRW-060 合规红线：只发一级。A 邀 B、B 邀 C，C 成单时 A 不得任何奖励。"""
    admin = make_admin(client)
    fund_pool(client, admin, 100000)

    a = register(client, "13800006201", "A")
    verify_user(client, a)
    code_a = client.get("/api/v1/users/me", headers=auth(a)).json()["referral_code"]
    b = _register_with_ref(client, "13800006202", code_a, "B")
    verify_user(client, b)
    code_b = client.get("/api/v1/users/me", headers=auth(b)).json()["referral_code"]
    c = _register_with_ref(client, "13800006203", code_b, "C")
    verify_user(client, c)

    topup(client, b, 100000)
    task = publish_task(client, b, budget_cents=30000)
    match_and_fund(client, b, c, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(c))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(b))

    assert client.get("/api/v1/me/referrals", headers=auth(b)).json()["earned_cents"] == 1000
    # A 是 B 的邀请人，但 C 成单与 A 无关——多层级返利是合规红线
    assert client.get("/api/v1/me/referrals", headers=auth(a)).json()["earned_cents"] == 0


def test_referral_blocked_on_shared_payout_account(client):
    """GRW-013 反作弊：邀请双方同一收款账户 → 不发钱，转人工。"""
    from .conftest import bind_payout

    admin = make_admin(client)
    fund_pool(client, admin, 100000)

    inviter = register(client, "13800006301", "刷子甲")
    verify_user(client, inviter, name="张三")
    code = client.get("/api/v1/users/me", headers=auth(inviter)).json()["referral_code"]
    invitee = _register_with_ref(client, "13800006302", code, "刷子乙")
    verify_user(client, invitee, name="张三")
    bind_payout(client, inviter, holder="张三")
    bind_payout(client, invitee, holder="张三")

    topup(client, inviter, 100000)
    task = publish_task(client, inviter, budget_cents=30000)
    match_and_fund(client, inviter, invitee, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(invitee))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(inviter))

    stats = client.get("/api/v1/me/referrals", headers=auth(inviter)).json()
    assert stats["achieved_count"] == 0
    assert stats["blocked_count"] == 1
    assert stats["earned_cents"] == 0
    assert reconcile(client, admin)["ok"] is True


# ---------- GRW-074 活动预算硬顶 ----------
def test_campaign_budget_cap_stops_issuing(client, worker):
    admin = make_admin(client)
    fund_pool(client, admin, 100000)
    camp = client.post("/api/v1/admin/campaigns",
                       json={"name": "冷启动补贴", "budget_cap_cents": 3000, "days": 7},
                       headers=auth(admin)).json()
    coupon = new_coupon(client, admin, campaign_id=camp["id"], per_user_limit=1,
                        amount_cents=2000)

    codes = []
    for i in range(3):
        u = register(client, f"1380000640{i}", f"用户{i}")
        verify_user(client, u)
        topup(client, u, 100000)
        uc = claim(client, u, coupon["id"])
        task = publish_task(client, u, budget_cents=50000)
        cid = sign_and_get_contract(client, u, worker, task)
        codes.append(client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc['id']}",
                                 headers=auth(u)).status_code)

    assert codes.count(200) == 1, f"预算 30 元、每张 20 元，第二张就超顶：{codes}"
    assert 409 in codes
    camps = client.get("/api/v1/admin/campaigns", headers=auth(admin)).json()["campaigns"]
    assert camps[0]["spent_cents"] <= camps[0]["budget_cap_cents"]
    assert reconcile(client, admin)["ok"] is True


# ---------- GRW-020/022/052 看板 ----------
def test_newcomer_progress(client, requester):
    body = client.get("/api/v1/me/newcomer", headers=auth(requester)).json()
    assert body["total"] == 6
    keys = {s["key"] for s in body["steps"]}
    assert {"verified", "first_publish", "first_done"} <= keys
    verified = next(s for s in body["steps"] if s["key"] == "verified")
    assert verified["done"] is True  # requester fixture 已实名

    topup(client, requester, 50000)
    publish_task(client, requester, budget_cents=20000)
    after = client.get("/api/v1/me/newcomer", headers=auth(requester)).json()
    assert after["finished"] > body["finished"]


def test_market_health_flags_supply_gap(client, requester):
    admin = make_admin(client)
    topup(client, requester, 200000)
    for _ in range(2):
        publish_task(client, requester, budget_cents=20000)
    body = client.get("/api/v1/admin/market-health", headers=auth(admin)).json()
    assert body["cells"], "有任务就该有格子"
    cell = body["cells"][0]
    assert cell["active_workers"] == 0
    assert cell["gap"] == "supply"  # 有需求没人接


def test_supply_hint_for_publisher(client, requester):
    topup(client, requester, 50000)
    task = publish_task(client, requester, budget_cents=20000)
    r = client.get("/api/v1/market/supply-hint",
                   params={"city": task["city"], "category": task["category"]},
                   headers=auth(requester))
    assert r.status_code == 200
    assert "执行人较少" in r.json()["hint"]


def test_north_star_metrics(client, requester, worker):
    admin = make_admin(client)
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    body = client.get("/api/v1/admin/north-star", headers=auth(admin)).json()
    assert body["orders_completed"] == 1
    assert body["gmv_cents"] == 30000
    assert body["dispute_rate"] == 0.0


def test_coupon_report_shows_cost(client, requester, worker):
    admin = make_admin(client)
    fund_pool(client, admin)
    coupon = new_coupon(client, admin)
    topup(client, requester, 100000)
    uc = claim(client, requester, coupon["id"])
    task = publish_task(client, requester, budget_cents=50000)
    cid = sign_and_get_contract(client, requester, worker, task)
    client.post(f"/api/v1/contracts/{cid}/fund?user_coupon_id={uc['id']}", headers=auth(requester))

    report = client.get("/api/v1/admin/coupons", headers=auth(admin)).json()["coupons"][0]
    assert report["claimed"] == 1 and report["used"] == 1
    assert report["cost_cents"] == 2000
    assert report["use_rate"] == 1.0


def test_growth_admin_endpoints_require_admin(client, requester):
    for path in ("/api/v1/admin/coupons", "/api/v1/admin/campaigns",
                 "/api/v1/admin/market-health", "/api/v1/admin/north-star"):
        assert client.get(path, headers=auth(requester)).status_code == 403
    assert client.post("/api/v1/admin/subsidy-pool/fund", json={"amount_cents": 100},
                       headers=auth(requester)).status_code == 403
