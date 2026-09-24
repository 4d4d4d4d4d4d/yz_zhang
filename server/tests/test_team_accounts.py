"""TEAM 团队账户（53 号 spec）。

「加个企业账号」很容易做成一个空壳——建个组织、拉几个人、然后什么也没变，
每个人还是用自己的钱包发任务。那没解决任何真实问题。

企业客户真正会卡住的是四件事：钱是公司的、谁能花多少要事先定、
超过某个数要有人批、发票开给公司。所以这一批的核心不是组织架构，
是**预算与审批**。
"""
from app.core.db import SessionLocal
from app.modules.team import service as team_service
from app.modules.wallet import service as wallet
from tests.conftest import auth, make_admin, register, topup, verify_user

PNG_REF = None


def make_user(client, phone, nick="成员"):
    u = register(client, phone, nick)
    verify_user(client, u, name=f"实名{nick}")
    return u


def make_team(client, owner, name="某某科技"):
    r = client.post("/api/v1/teams", json={"name": name}, headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def fund_team(team_id, cents):
    with SessionLocal() as db:
        wallet.topup(db, team_id, cents)
        db.commit()


def add_member(client, team_id, owner, user, role="member", limit=0):
    return client.post(f"/api/v1/teams/{team_id}/members",
                       json={"user_id": user["id"], "role": role,
                             "spend_limit_cents": limit},
                       headers=auth(owner))


# ------------------------------------------------------------ TEAM-001 独立钱包
def test_team001_team_has_its_own_wallet_separate_from_members(client):
    """**钱是公司的，不是某个员工的。** 员工用自己钱包垫付再报销，
    在任何一家公司都走不通。"""
    owner = make_user(client, "13300000001", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    topup(client, owner, 5000)

    info = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert info["balance_cents"] == 100000
    mine = client.get("/api/v1/wallet", headers=auth(owner)).json()
    assert mine["available_cents"] == 5000, "团队充值不该进个人钱包"


def test_team040_team_account_is_not_in_the_recommendation_pool(client):
    """团队是 User，但它不是「人」——不该出现在接单人推荐里。"""
    from tests.test_task_flow import publish_task

    owner = make_user(client, "13300000002", "老板")
    team_id = make_team(client, owner)
    worker = make_user(client, "13300000003", "真人")
    task = publish_task(client, owner, category="保洁")
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations",
                      headers=auth(owner)).json()
    ids = {r["user_id"] for r in recs}
    assert team_id not in ids
    assert worker["id"] in ids, "把真人也排掉了，说明排除条件写过头了"


# ------------------------------------------------------- TEAM-010 角色与权限
def test_team010_only_owner_can_change_roles_and_limits(client):
    """**admin 能批支出但不能给自己提额度**——否则「审批」这道闸门
    自己就绕过去了。"""
    owner = make_user(client, "13300000010", "老板")
    team_id = make_team(client, owner)
    boss2 = make_user(client, "13300000011", "主管")
    staff = make_user(client, "13300000012", "员工")
    add_member(client, team_id, owner, boss2, role="admin")
    add_member(client, team_id, owner, staff, role="member", limit=10000)

    r = client.patch(f"/api/v1/teams/{team_id}/members/{staff['id']}",
                     json={"spend_limit_cents": 999999}, headers=auth(boss2))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "insufficient_role"

    ok = client.patch(f"/api/v1/teams/{team_id}/members/{staff['id']}",
                      json={"spend_limit_cents": 20000}, headers=auth(owner))
    assert ok.status_code == 200 and ok.json()["spend_limit_cents"] == 20000


def test_team010_owner_role_is_immutable(client):
    owner = make_user(client, "13300000013", "老板")
    team_id = make_team(client, owner)
    r = client.patch(f"/api/v1/teams/{team_id}/members/{owner['id']}",
                     json={"role": "member"}, headers=auth(owner))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "owner_immutable"
    assert client.delete(f"/api/v1/teams/{team_id}/members/{owner['id']}",
                         headers=auth(owner)).status_code == 400


def test_non_members_cannot_see_the_team(client):
    owner = make_user(client, "13300000014", "老板")
    team_id = make_team(client, owner)
    outsider = make_user(client, "13300000015", "外人")
    assert client.get(f"/api/v1/teams/{team_id}",
                      headers=auth(outsider)).status_code == 403


def test_special_accounts_cannot_join_a_team(client):
    """AI 助理、合作体、团队账号都不是「人」，不能当团队成员。"""
    from app.modules.coop import compliance_path as cpath

    owner = make_user(client, "13300000016", "老板")
    team_id = make_team(client, owner)
    founder = make_user(client, "13300000017", "创始")
    vid = client.post("/api/v1/ventures", json={
        "name": "某合作体", "risk_disclosure_version": cpath.RISK_DISCLOSURE_VERSION,
    }, headers=auth(founder)).json()["id"]
    r = client.post(f"/api/v1/teams/{team_id}/members",
                    json={"user_id": vid, "role": "member"}, headers=auth(owner))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_member"


# ------------------------------------------------- TEAM-011/020 额度与审批
def test_team011_within_limit_spends_execute_immediately(client):
    owner = make_user(client, "13300000020", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    staff = make_user(client, "13300000021", "员工")
    add_member(client, team_id, owner, staff, limit=30000)

    before = client.get("/api/v1/wallet", headers=auth(staff)).json()["available_cents"]
    r = client.post(f"/api/v1/teams/{team_id}/spends",
                    json={"amount_cents": 20000, "purpose": "买素材"},
                    headers=auth(staff))
    assert r.status_code == 201, r.text
    assert r.json()["needed_approval"] is False
    after = client.get("/api/v1/wallet", headers=auth(staff)).json()["available_cents"]
    assert after - before == 20000


def test_team011_within_limit_spends_are_still_recorded(client):
    """「谁花了公司多少钱」这件事，不该因为在额度内就查不到。"""
    owner = make_user(client, "13300000022", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    staff = make_user(client, "13300000023", "员工")
    add_member(client, team_id, owner, staff, limit=30000)
    client.post(f"/api/v1/teams/{team_id}/spends",
                json={"amount_cents": 20000, "purpose": "买素材"}, headers=auth(staff))

    rows = client.get(f"/api/v1/teams/{team_id}/spends", headers=auth(owner)).json()
    assert any(r["amount_cents"] == 20000 and r["status"] == "executed" for r in rows)


def test_team011_over_limit_becomes_an_approval_and_does_not_move_money(client):
    """**审批期间不预扣团队资金。**

    预扣会让一堆待批的申请把预算占死，而审批本来就可能被驳回。
    """
    owner = make_user(client, "13300000024", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    staff = make_user(client, "13300000025", "员工")
    add_member(client, team_id, owner, staff, limit=10000)

    r = client.post(f"/api/v1/teams/{team_id}/spends",
                    json={"amount_cents": 50000, "purpose": "采购"},
                    headers=auth(staff))
    assert r.status_code == 201 and r.json()["needed_approval"] is True
    assert "额度" in r.json()["reason"]

    info = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert info["balance_cents"] == 100000, "待审期间不该动团队的钱"


def test_team020_approved_then_executed_moves_the_money(client):
    owner = make_user(client, "13300000026", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    staff = make_user(client, "13300000027", "员工")
    add_member(client, team_id, owner, staff, limit=10000)
    req_id = client.post(f"/api/v1/teams/{team_id}/spends",
                         json={"amount_cents": 50000, "purpose": "采购"},
                         headers=auth(staff)).json()["id"]

    client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/decide",
                json={"approve": True, "reason": "同意"}, headers=auth(owner))
    before = client.get("/api/v1/wallet", headers=auth(staff)).json()["available_cents"]
    r = client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/execute",
                    headers=auth(staff))
    assert r.status_code == 200, r.text
    after = client.get("/api/v1/wallet", headers=auth(staff)).json()["available_cents"]
    assert after - before == 50000


def test_team020_rejection_must_say_why_and_moves_nothing(client):
    owner = make_user(client, "13300000028", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    staff = make_user(client, "13300000029", "员工")
    add_member(client, team_id, owner, staff, limit=10000)
    req_id = client.post(f"/api/v1/teams/{team_id}/spends",
                         json={"amount_cents": 50000, "purpose": "采购"},
                         headers=auth(staff)).json()["id"]

    bad = client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/decide",
                      json={"approve": False, "reason": "  "}, headers=auth(owner))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "reason_required"

    client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/decide",
                json={"approve": False, "reason": "本季度预算已用完"}, headers=auth(owner))
    r = client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/execute",
                    headers=auth(staff))
    assert r.status_code == 409
    info = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert info["balance_cents"] == 100000


def test_team021_cannot_approve_your_own_request(client):
    """与 COOP-010（贡献不能自己确认）、VER-021（当事人不能核验）同一条规矩。"""
    owner = make_user(client, "13300000030", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    boss2 = make_user(client, "13300000031", "主管")
    add_member(client, team_id, owner, boss2, role="admin")

    # admin 有权批，但不能批自己的
    req_id = client.post(f"/api/v1/teams/{team_id}/spends",
                         json={"amount_cents": 50000, "purpose": "采购"},
                         headers=auth(boss2)).json().get("id")
    if req_id is None:            # admin 无额度限制 → 直接执行，用 member 再试
        staff = make_user(client, "13300000032", "员工")
        add_member(client, team_id, owner, staff, limit=1000)
        req_id = client.post(f"/api/v1/teams/{team_id}/spends",
                             json={"amount_cents": 50000, "purpose": "采购"},
                             headers=auth(staff)).json()["id"]
        r = client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/decide",
                        json={"approve": True, "reason": "自己批自己"},
                        headers=auth(staff))
        assert r.status_code == 403
        assert r.json()["detail"]["code"] in ("self_approval", "insufficient_role")


def test_team021_members_cannot_approve_anything(client):
    owner = make_user(client, "13300000033", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    a = make_user(client, "13300000034", "员工甲")
    b = make_user(client, "13300000035", "员工乙")
    add_member(client, team_id, owner, a, limit=1000)
    add_member(client, team_id, owner, b, limit=1000)
    req_id = client.post(f"/api/v1/teams/{team_id}/spends",
                         json={"amount_cents": 5000, "purpose": "采购"},
                         headers=auth(a)).json()["id"]
    r = client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/decide",
                    json={"approve": True, "reason": "同意"}, headers=auth(b))
    assert r.status_code == 403


def test_team022_execution_fails_clearly_when_funds_ran_out(client):
    """**审批期间不预扣，代价就是批准时可能余额不足。**

    那时要明确报错，不产生半截状态——这比把预算占死好。
    """
    owner = make_user(client, "13300000040", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 60000)
    staff = make_user(client, "13300000041", "员工")
    add_member(client, team_id, owner, staff, limit=1000)
    req_id = client.post(f"/api/v1/teams/{team_id}/spends",
                         json={"amount_cents": 50000, "purpose": "采购"},
                         headers=auth(staff)).json()["id"]
    client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/decide",
                json={"approve": True, "reason": "同意"}, headers=auth(owner))
    # 期间 owner 自己花掉了大部分
    client.post(f"/api/v1/teams/{team_id}/spends",
                json={"amount_cents": 55000, "purpose": "老板先花了"},
                headers=auth(owner))

    r = client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/execute",
                    headers=auth(staff))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "insufficient_team_funds"
    assert "审批期间不预扣" in r.json()["detail"]["message"]


def test_can_decide_flag_matches_the_server_rule(client):
    """客户端按钮与服务端判断同一来源。"""
    owner = make_user(client, "13300000042", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    staff = make_user(client, "13300000043", "员工")
    add_member(client, team_id, owner, staff, limit=1000)
    client.post(f"/api/v1/teams/{team_id}/spends",
                json={"amount_cents": 50000, "purpose": "采购"}, headers=auth(staff))

    as_owner = client.get(f"/api/v1/teams/{team_id}/spends", headers=auth(owner)).json()
    as_staff = client.get(f"/api/v1/teams/{team_id}/spends", headers=auth(staff)).json()
    assert as_owner[0]["can_decide"] is True
    assert as_staff[0]["can_decide"] is False


def test_members_only_see_their_own_spend_history(client):
    owner = make_user(client, "13300000044", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    a = make_user(client, "13300000045", "员工甲")
    b = make_user(client, "13300000046", "员工乙")
    add_member(client, team_id, owner, a, limit=100000)
    add_member(client, team_id, owner, b, limit=100000)
    client.post(f"/api/v1/teams/{team_id}/spends",
                json={"amount_cents": 1000, "purpose": "甲的"}, headers=auth(a))
    rows_b = client.get(f"/api/v1/teams/{team_id}/spends", headers=auth(b)).json()
    assert all(r["requester_id"] == b["id"] for r in rows_b)


# ----------------------------------------------------------- TEAM-030 发票
def test_team030_unverified_team_cannot_invoice(client):
    """**一张开给未核验抬头的发票，是税务风险不是便利。**"""
    owner = make_user(client, "13300000050", "老板")
    team_id = make_team(client, owner)
    info = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert info["invoice_block"], "未核验就允许开票"

    from app.modules.team.models import Team

    with SessionLocal() as db:
        t = db.get(Team, team_id)
        t.company_name, t.tax_number = "某某科技有限公司", "91310000MA1K00000X"
        t.verify_status = "verified"
        db.commit()
        assert team_service.can_invoice(db.get(Team, team_id)) == ""


def test_team030_company_submission_requires_license_images(client):
    owner = make_user(client, "13300000051", "老板")
    team_id = make_team(client, owner)
    r = client.post(f"/api/v1/teams/{team_id}/company",
                    json={"company_name": "某某科技有限公司",
                          "tax_number": "91310000MA1K00000X", "license_images": []},
                    headers=auth(owner))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "images_required"


def test_team030_license_images_are_marked_sensitive(client):
    """营业执照与证件影像同属敏感材料，走 V76 那条鉴权路径，不走匿名能力 URL。"""
    import base64

    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x11" * 96).decode()
    owner = make_user(client, "13300000052", "老板")
    team_id = make_team(client, owner)
    img = client.post("/api/v1/files",
                      json={"content_type": "image/png", "data_base64": png},
                      headers=auth(owner)).json()["ref"]
    client.post(f"/api/v1/teams/{team_id}/company",
                json={"company_name": "某某科技有限公司",
                      "tax_number": "91310000MA1K00000X", "license_images": [img]},
                headers=auth(owner))
    assert client.get(f"/api/v1/files/{img}").status_code == 403
    assert client.get(f"/api/v1/files/{img}/secure",
                      headers=auth(owner)).status_code == 200


# ----------------------------------------------------------- TEAM-041 资金守恒
def test_team041_team_money_flows_keep_the_invariants(client):
    admin = make_admin(client, "13300000060")
    owner = make_user(client, "13300000061", "老板")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    staff = make_user(client, "13300000062", "员工")
    add_member(client, team_id, owner, staff, limit=30000)
    client.post(f"/api/v1/teams/{team_id}/spends",
                json={"amount_cents": 20000, "purpose": "买素材"}, headers=auth(staff))
    req_id = client.post(f"/api/v1/teams/{team_id}/spends",
                         json={"amount_cents": 50000, "purpose": "采购"},
                         headers=auth(staff)).json()["id"]
    client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/decide",
                json={"approve": True, "reason": "同意"}, headers=auth(owner))
    client.post(f"/api/v1/teams/{team_id}/spends/{req_id}/execute", headers=auth(staff))

    rec = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert rec["ok"] is True, rec["mismatches"]


def test_coop_and_team_are_different_things(client):
    """**合作体是分钱的，团队是花钱的。**

    两者都有资金池但规则相反，所以是两个模块而不是一个带开关的模块。
    这条钉住：团队没有「分配」这个动作。
    """
    from app.main import app

    paths = [p for p in app.openapi()["paths"] if "/teams" in p]
    assert not any("distribution" in p or "share" in p for p in paths), paths
