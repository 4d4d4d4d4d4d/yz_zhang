"""ADMIN-060 / MOD-060 / FIN-060 运营侧剩下的四条（73 号 spec）。

V96 把提现复核与可疑活动接上了，管理后台仍有四条只有端点没有界面。
其中两条不是「少个页面」的量级：

- **审计日志不可读**：V96 的测试能断言「批准提现写下了审计行」，
  而**谁批了那笔三万块**这个问题，此前只能靠查数据库回答。
- **封禁影响面没接**：V58 专门算了在途合约、受影响的托管资金、
  会被下架的招募中任务，而后台直接调 `banUser`——**管理员在盲封**。
"""
from app.core.db import SessionLocal
from tests.conftest import auth, make_admin, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task


# ------------------------------------------------- ADMIN-060 审计日志读得到
def test_admin060_audit_log_answers_who_approved_that_payout(client):
    """「谁批了那笔三万块」——这个问题必须在界面上答得出来。"""
    u = register(client, "13800092001", "提现的人")
    verify_user(client, u, name="提现")
    topup(client, u, 5000000)
    client.put("/api/v1/wallet/payout-account",
               json={"kind": "bank", "account_no": "6222020000092001", "holder_name": "提现"},
               headers=auth(u))
    rid = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 3000000},
                      headers=auth(u)).json()["request_id"]
    admin = make_admin(client, "13800092009")
    client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))

    rows = client.get("/api/v1/admin/audit-log?action=withdraw_approve&limit=20",
                      headers=auth(admin)).json()
    assert rows, "批准提现的审计行读不出来"
    row = rows[0]
    assert row["admin_id"] == admin["id"], "看不出是谁批的"
    assert row["target_id"] == rid
    assert "3000000" in row["detail"] or "30000" in row["detail"], \
        f"明细里没有金额，回溯时还得再查一次：{row['detail']}"


def test_admin060_audit_log_is_admin_only(client):
    """审计日志里有「谁对谁做了什么」，不是用户能看的东西。"""
    u = register(client, "13800092010", "路人")
    assert client.get("/api/v1/admin/audit-log", headers=auth(u)).status_code == 403


def test_admin060_audit_log_filters_by_action(client):
    """按动作过滤——不然一屏全是登录记录，找不到那笔放款。"""
    admin = make_admin(client, "13800092019")
    victim = register(client, "13800092020", "被封的人")
    client.post(f"/api/v1/admin/users/{victim['id']}/ban", headers=auth(admin))

    banned = client.get("/api/v1/admin/audit-log?action=ban_user&limit=20",
                        headers=auth(admin)).json()
    assert banned, "封禁没有留下可过滤的审计行"
    assert all(r["action"] == "ban_user" for r in banned), "过滤没生效"


# ------------------------------------------------- MOD-060 封禁前看得见代价
def test_mod060_ban_impact_shows_what_a_ban_would_cost(client, requester):
    """封禁是不可逆的处置，代价必须在按下之前摆在眼前。"""
    worker = register(client, "13800092030", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    admin = make_admin(client, "13800092039")

    impact = client.get(f"/api/v1/admin/users/{worker['id']}/ban-impact",
                        headers=auth(admin)).json()
    assert impact["in_flight_count"] == 1, "在途合约数不对"
    assert impact["escrow_at_risk_cents"] == 20000, "受影响的托管资金没算出来"
    assert impact["in_flight_contracts"][0]["counterparty_id"] == requester["id"], \
        "看不到对手方是谁——封禁会连带影响他"
    # 服务端一直返回这两个键，而 SDK 的行内类型里没有（V89 那一类漂移）
    assert "open_task_ids" in impact and "open_task_count" in impact


def test_mod060_ban_impact_counts_open_tasks_that_would_be_delisted(client, requester):
    """招募中的任务会被下架——发布方和已报名的人都会受影响。"""
    admin = make_admin(client, "13800092049")
    topup(client, requester, 200000)
    publish_task(client, requester, title="会被下架的一单")
    impact = client.get(f"/api/v1/admin/users/{requester['id']}/ban-impact",
                        headers=auth(admin)).json()
    assert impact["open_task_count"] >= 1
    assert impact["open_task_ids"], "只给了个数，回溯不到是哪几单"


# ------------------------------------------------- FIN-060 平台自己的钱
def test_fin060_platform_finance_and_settlement_leave_an_audit_trail(client, requester):
    """结算是动钱的动作，必须留痕——所以它属于后台，不属于一条脚本。"""
    worker = register(client, "13800092050", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    admin = make_admin(client, "13800092059")
    fin = client.get("/api/v1/admin/platform-finance", headers=auth(admin)).json()
    assert fin["total_fee_cents"] > 0, "放款完成了却看不到佣金收入"
    assert fin["fee_count"] >= 1

    r = client.post("/api/v1/admin/platform-finance/settle",
                    json={"amount_cents": 100, "memo": "测试结算"}, headers=auth(admin))
    assert r.status_code == 200, r.text

    # 资金不变量不因结算而破
    assert client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()["ok"] is True


def test_fin060_settlement_cannot_exceed_platform_balance(client):
    """不能把不存在的钱结算出去。"""
    admin = make_admin(client, "13800092069")
    r = client.post("/api/v1/admin/platform-finance/settle",
                    json={"amount_cents": 999999999, "memo": "超额"}, headers=auth(admin))
    assert r.status_code == 400, r.text


# ------------------------------------------------- 公告
def test_announcement_reports_how_many_people_it_reached(client):
    """公告发出去收不回来，所以要让发的人看到自己刚影响了多少人。"""
    admin = make_admin(client, "13800092079")
    register(client, "13800092080", "甲")
    r = client.post("/api/v1/admin/announcements",
                    json={"title": "系统维护", "body": "今晚 0 点起 30 分钟",
                          "verified_only": False}, headers=auth(admin))
    assert r.status_code == 200, r.text
    assert r.json()["delivered"] >= 2, "送达人数不对"

    with SessionLocal() as db:
        from app.modules.notification.models import Notification

        assert db.query(Notification).filter(Notification.title == "系统维护").count() >= 2
