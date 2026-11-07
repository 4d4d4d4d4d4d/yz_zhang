"""TEAM-050~054 额度必须是累计的（62 号 spec）。

探针实测：一个「单笔额度 ¥10」的普通成员，**零审批**从团队钱包划走了 ¥200——
同一笔申请发 20 次，每次都在额度内，每次都自动批准并执行。

    团队余额: 80000   成员到手: 20000
    成员单笔额度 1000，无需任何审批就划走了： 20000

平台自己修过这个洞：V55 的提现风控「改造前只判单笔，连提 5 笔 ¥9,999
可以 ¥49,995 零人审出账」。一模一样的形状，在那之后写的团队模块里又来一次。

**一个只管单笔的额度不是额度，是一张可以无限刷的卡。**
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.wallet import service as wallet
from tests.conftest import auth, register, verify_user


def make_team(client, owner_phone="13800062001", balance=1000000):
    owner = register(client, owner_phone, "队长")
    verify_user(client, owner, name="队长")
    team_id = client.post("/api/v1/teams", json={"name": "设计组"},
                          headers=auth(owner)).json()["id"]
    with SessionLocal() as db:
        acct = wallet.get_or_create(db, team_id)
        acct.available_cents = balance
        wallet._log(db, team_id, "topup", balance, None, "测试充值")
        db.commit()
    return owner, team_id


def add_member(client, owner, team_id, phone, *, role="member", limit=1000):
    user = register(client, phone, "队员")
    verify_user(client, user, name="队员")
    r = client.post(f"/api/v1/teams/{team_id}/members",
                    json={"user_id": user["id"], "role": role, "spend_limit_cents": limit},
                    headers=auth(owner))
    assert r.status_code == 201, r.text
    return user


def spend(client, user, team_id, amount, purpose="买素材"):
    return client.post(f"/api/v1/teams/{team_id}/spends",
                       json={"amount_cents": amount, "purpose": purpose, "task_id": None},
                       headers=auth(user))


def balance(team_id):
    with SessionLocal() as db:
        return wallet.get_or_create(db, team_id).available_cents


# ------------------------------------------------- TEAM-050 拆单不再能绕
def test_team050_splitting_no_longer_bypasses_the_limit(client):
    """改造前：单笔额度 ¥10 的成员发 20 次，零审批划走 ¥200。"""
    owner, team_id = make_team(client)
    member = add_member(client, owner, team_id, "13800062002", limit=1000)
    before = balance(team_id)

    executed, needing_approval = 0, 0
    for _ in range(20):
        body = spend(client, member, team_id, 1000).json()
        if body.get("status") == "executed":
            executed += 1000
        if body.get("needed_approval"):
            needing_approval += 1

    assert executed == 1000, f"月度额度 ¥10，却自助划走了 {executed} 分"
    assert needing_approval == 19, "超出额度的申请应该转审批，而不是被拒或被执行"
    assert balance(team_id) == before - 1000


def test_team050_single_spend_over_the_monthly_limit_needs_approval(client):
    """单笔超过月度额度天然过不去——所以不再需要单独的单笔限额。"""
    owner, team_id = make_team(client, "13800062010")
    member = add_member(client, owner, team_id, "13800062011", limit=1000)
    body = spend(client, member, team_id, 5000).json()
    assert body["needed_approval"] is True
    assert "剩余" in body["reason"], "提示要说还剩多少，不是只说「超额」"


def test_team050_limit_message_says_how_much_is_left(client):
    """只说「超额」的话，对方不知道该改金额还是该走审批。"""
    owner, team_id = make_team(client, "13800062020")
    member = add_member(client, owner, team_id, "13800062021", limit=10000)
    spend(client, member, team_id, 6000)
    body = spend(client, member, team_id, 6000).json()
    assert body["needed_approval"] is True
    assert "已用 ¥60.00" in body["reason"] and "剩余 ¥40.00" in body["reason"], body["reason"]


# ------------------------------------------------- TEAM-051 admin 不再无限额
def test_team051_admins_are_bounded_too(client):
    """admin 是**被授予权限的人**，不是授予权限的人。"""
    owner, team_id = make_team(client, "13800062030")
    admin = add_member(client, owner, team_id, "13800062031", role="admin", limit=2000)
    assert spend(client, admin, team_id, 2000).json()["status"] == "executed"
    second = spend(client, admin, team_id, 2000).json()
    assert second["needed_approval"] is True, "admin 仍然可以无限刷"


def test_team051_owner_stays_exempt(client):
    """owner 豁免是讲得通的：他就是定额度的那个人，给他设限不增加安全性。"""
    owner, team_id = make_team(client, "13800062040")
    for _ in range(3):
        assert spend(client, owner, team_id, 50000).json()["status"] == "executed"


# ------------------------------------------------- TEAM-052 团队预算池
def test_team052_pool_binds_everyone_including_the_owner(client):
    """池子是总量，不是权限：owner 也受它约束（但他能改它）。"""
    owner, team_id = make_team(client, "13800062050")
    r = client.post(f"/api/v1/teams/{team_id}/budget",
                    json={"monthly_budget_cents": 30000}, headers=auth(owner))
    assert r.status_code == 200, r.text

    assert spend(client, owner, team_id, 20000).json()["status"] == "executed"
    blocked = spend(client, owner, team_id, 20000).json()
    assert blocked["needed_approval"] is True
    assert "预算池" in blocked["reason"]


def test_team052_zero_pool_means_no_pool(client):
    """0 = 不设池：给老数据凭空安一个池子，会让他们在毫不知情的情况下被拦住。"""
    owner, team_id = make_team(client, "13800062060")
    detail = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert detail["monthly_budget_cents"] == 0
    for _ in range(3):
        assert spend(client, owner, team_id, 100000).json()["status"] == "executed"


def test_team052_only_owner_can_change_the_pool(client):
    """让 admin 自己改池子，等于让他绕过自己受的约束。"""
    owner, team_id = make_team(client, "13800062070")
    admin = add_member(client, owner, team_id, "13800062071", role="admin", limit=1000)
    r = client.post(f"/api/v1/teams/{team_id}/budget",
                    json={"monthly_budget_cents": 999999}, headers=auth(admin))
    assert r.status_code == 403


# --------------------------------- TEAM-053 批准了也不能突破池子
def test_team053_approved_requests_still_hit_the_pool_at_execution(client):
    """批准 N 笔、逐个执行——只在申请时判池子的话，这 N 笔会全部通过。

    审批到执行之间，世界会变。
    """
    owner, team_id = make_team(client, "13800062080")
    member = add_member(client, owner, team_id, "13800062081", limit=1000)
    client.post(f"/api/v1/teams/{team_id}/budget",
                json={"monthly_budget_cents": 30000}, headers=auth(owner))

    ids = []
    for _ in range(3):
        body = spend(client, member, team_id, 20000).json()
        assert body["needed_approval"] is True
        ids.append(body["id"])
    for rid in ids:
        r = client.post(f"/api/v1/teams/{team_id}/spends/{rid}/decide",
                        json={"approve": True, "reason": "同意"}, headers=auth(owner))
        assert r.status_code == 200, r.text

    results = [
        client.post(f"/api/v1/teams/{team_id}/spends/{rid}/execute", headers=auth(member))
        for rid in ids
    ]
    ok = [r for r in results if r.status_code == 200]
    assert len(ok) == 1, "池子 ¥300，却执行了多于一笔 ¥200 的支出"
    rejected = [r for r in results if r.status_code != 200]
    assert all(r.json()["detail"]["code"] == "monthly_budget_exceeded" for r in rejected)


# ------------------------------------------------- TEAM-054 月份边界
def test_team054_last_months_spending_does_not_count(client):
    """上个月的支出不占本月额度。"""
    owner, team_id = make_team(client, "13800062090")
    member = add_member(client, owner, team_id, "13800062091", limit=5000)
    assert spend(client, member, team_id, 5000).json()["status"] == "executed"

    # 把这笔挪到上个月
    from app.modules.team.models import SpendRequest
    from app.modules.team.service import month_start

    with SessionLocal() as db:
        row = db.query(SpendRequest).filter(SpendRequest.team_id == team_id).first()
        row.created_at = month_start() - timedelta(days=1)
        db.add(row)
        db.commit()

    assert spend(client, member, team_id, 5000).json()["status"] == "executed", \
        "上个月的支出占了本月的额度"
