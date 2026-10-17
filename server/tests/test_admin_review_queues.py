"""TEAM-031 / CERT-030 / UMOD-030 / CS-030 / SECEV-030 人审队列的出口（76 号 spec）。

这些测试刻意**全程走 HTTP**。上一版的团队核验「测试」是这样写的：

    with SessionLocal() as db:
        t = db.get(Team, team_id)
        t.verify_status = "verified"       # 直接写库
        db.commit()
        assert team_service.can_invoice(...) == ""

它绿了很久，而生产里**没有任何端点能做这件事**——
测试自己把状态改了，所以没有人发现没有人能改它。
"""
from app.core.db import SessionLocal
from tests.conftest import JOB_HEADERS, auth, make_admin, register, verify_user  # noqa: F401


def _notices(client, user, title):
    rows = client.get("/api/v1/notifications?limit=100", headers=auth(user)).json()
    items = rows["items"] if isinstance(rows, dict) else rows
    return [n for n in items if n["title"] == title]


def _team_with_company(client, phone: str, name: str = "开票队"):
    owner = register(client, phone, "老板")
    verify_user(client, owner, name="老板")
    tid = client.post("/api/v1/teams", json={"name": name}, headers=auth(owner)).json()["id"]
    r = client.post(f"/api/v1/teams/{tid}/company",
                    json={"company_name": "某某科技有限公司",
                          "tax_number": "91310000MA1K00000X",
                          "license_images": [f"lic-{phone[-4:]}.png"]},
                    headers=auth(owner))
    assert r.status_code == 200, r.text
    return owner, tid


# ------------------------------------------------- TEAM-031 团队企业核验
def test_team031_admin_can_see_the_pending_team(client):
    """提交完材料，核的那个人要能看到它。"""
    owner, tid = _team_with_company(client, "13800120001")
    admin = make_admin(client, "13800120009")

    rows = client.get("/api/v1/admin/teams/pending", headers=auth(admin)).json()
    row = [r for r in rows if r["team_id"] == tid]
    assert row, "提交了企业信息，待核验列表里看不到"
    row = row[0]
    assert row["company_name"] == "某某科技有限公司"
    assert row["owner_id"] == owner["id"]
    # 营业执照是企业敏感材料：影像走鉴权端点，不是匿名能力 URL（37 号 spec）
    assert row["license_urls"] and all(u.endswith("/secure") for u in row["license_urls"])


def test_team031_verifying_actually_unblocks_invoicing(client):
    """核过之后**真的**能开票——这条以前是靠直接写库断言的。"""
    owner, tid = _team_with_company(client, "13800120010")
    before = client.get(f"/api/v1/teams/{tid}", headers=auth(owner)).json()
    assert before["invoice_block"], "未核验就允许开票"

    admin = make_admin(client, "13800120019")
    r = client.post(f"/api/v1/admin/teams/{tid}/verify",
                    json={"approve": True, "reason": ""}, headers=auth(admin))
    assert r.status_code == 200, r.text
    assert r.json()["verify_status"] == "verified"

    after = client.get(f"/api/v1/teams/{tid}", headers=auth(owner)).json()
    assert not after["invoice_block"], "核验通过了还是不能开票"
    assert _notices(client, owner, "团队企业信息已核验通过"), "owner 不知道自己能开票了"


def test_team031_rejection_requires_a_reason_and_delivers_it(client):
    """驳回必须写理由，而且理由要送到 owner 面前。

    收不到理由，他只会把同一份材料再提交一遍（V92 那条的又一次）。
    """
    owner, tid = _team_with_company(client, "13800120020")
    admin = make_admin(client, "13800120029")

    r = client.post(f"/api/v1/admin/teams/{tid}/verify",
                    json={"approve": False, "reason": "   "}, headers=auth(admin))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "reason_required"

    r = client.post(f"/api/v1/admin/teams/{tid}/verify",
                    json={"approve": False, "reason": "执照影像模糊，请重新上传"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text
    told = _notices(client, owner, "团队企业信息未通过核验")
    assert told, "驳回了却没有人告诉 owner"
    assert "执照影像模糊" in told[0]["body"], "强制写下的理由没送到"


def test_team031_verification_leaves_an_audit_row(client):
    """它决定这个团队能不能开票——有后果的动作要留痕。"""
    _owner, tid = _team_with_company(client, "13800120030")
    admin = make_admin(client, "13800120039")
    client.post(f"/api/v1/admin/teams/{tid}/verify",
                json={"approve": True, "reason": ""}, headers=auth(admin))

    rows = client.get("/api/v1/admin/audit-log?action=team_verify&limit=10",
                      headers=auth(admin)).json()
    assert rows, "核验没有留下审计行"
    assert rows[0]["target_id"] == tid


def test_team031_only_pending_teams_can_be_verified(client):
    """没提交过材料的团队不该能被「核过」。"""
    owner = register(client, "13800120040", "老板")
    verify_user(client, owner, name="老板")
    tid = client.post("/api/v1/teams", json={"name": "没交材料队"},
                      headers=auth(owner)).json()["id"]
    admin = make_admin(client, "13800120049")

    r = client.post(f"/api/v1/admin/teams/{tid}/verify",
                    json={"approve": True, "reason": ""}, headers=auth(admin))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "not_pending"


def test_team031_is_admin_only(client):
    """核验是运营动作，团队自己不能核自己。"""
    owner, tid = _team_with_company(client, "13800120050")
    assert client.get("/api/v1/admin/teams/pending",
                      headers=auth(owner)).status_code == 403
    assert client.post(f"/api/v1/admin/teams/{tid}/verify",
                       json={"approve": True, "reason": ""},
                       headers=auth(owner)).status_code == 403


# ------------------------------------------------- CERT-030/031 资质核验与撤销
def _submit_cert(client, phone: str, name: str = "电工证"):
    user = register(client, phone, "持证人")
    verify_user(client, user, name="张三")
    r = client.post("/api/v1/users/me/certifications",
                    json={"name": name, "holder_name": "张三",
                          "cert_number": f"C{phone[-6:]}", "issuer": "某市人社局",
                          "images": [f"cert-{phone[-4:]}.png"]},
                    headers=auth(user))
    assert r.status_code == 201, r.text
    return user


def test_cert030_pending_queue_shows_whether_the_name_matches(client):
    """审核员要一眼看到「证件姓名 vs 实名」是否一致——服务端算好，界面不重算。"""
    _user = _submit_cert(client, "13800120060")
    admin = make_admin(client, "13800120069")
    rows = client.get("/api/v1/admin/certifications/pending", headers=auth(admin)).json()
    assert rows, "提交了资质申请，待核验列表是空的"
    assert rows[0]["name_matches"] is True
    assert all(u.endswith("/secure") for u in rows[0]["image_urls"])


def test_cert030_approving_lets_the_holder_take_restricted_work(client):
    """核过才算：通过之后持证人的有效资质里要真的有它。"""
    user = _submit_cert(client, "13800120070")
    admin = make_admin(client, "13800120079")
    app_id = client.get("/api/v1/admin/certifications/pending",
                        headers=auth(admin)).json()[0]["id"]

    r = client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                    json={"approve": True, "reason": ""}, headers=auth(admin))
    assert r.status_code == 200, r.text
    mine = client.get("/api/v1/users/me/certifications", headers=auth(user)).json()
    assert "电工证" in mine["active"], "核过了却没进有效资质"


def test_cert031_approved_certifications_can_be_listed_and_revoked(client):
    """撤销的对象是**已核准**的那些。

    此前后台只看得到待核验的，于是 `revoke` 这个端点没有任何入口——
    一张已经核过的假证件撤不下来，持证人会继续接受限类目的单。
    """
    user = _submit_cert(client, "13800120080")
    admin = make_admin(client, "13800120089")
    app_id = client.get("/api/v1/admin/certifications/pending",
                        headers=auth(admin)).json()[0]["id"]
    client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                json={"approve": True, "reason": ""}, headers=auth(admin))

    approved = client.get("/api/v1/admin/certifications?status=approved",
                          headers=auth(admin)).json()
    assert [r for r in approved if r["id"] == app_id], "已核准的资质列不出来"

    r = client.post(f"/api/v1/admin/certifications/{app_id}/revoke",
                    json={"approve": False, "reason": "证件经复核为伪造"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text
    mine = client.get("/api/v1/users/me/certifications", headers=auth(user)).json()
    assert "电工证" not in mine["active"], "撤销了却还在有效资质里"


def test_cert030_audit_target_is_the_application_id(client):
    """ADMIN-070 审计的 target_id 是整数（此前传的是 `str(...)`）。"""
    _user = _submit_cert(client, "13800120090")
    admin = make_admin(client, "13800120099")
    app_id = client.get("/api/v1/admin/certifications/pending",
                        headers=auth(admin)).json()[0]["id"]
    client.post(f"/api/v1/admin/certifications/{app_id}/decide",
                json={"approve": True, "reason": ""}, headers=auth(admin))

    rows = client.get("/api/v1/admin/audit-log?action=certification_decide&limit=5",
                      headers=auth(admin)).json()
    assert rows and rows[0]["target_id"] == app_id
    assert isinstance(rows[0]["target_id"], int), "target_id 不是整数——Postgres 上这条会写不进去"


# ------------------------------------------------- UMOD-030 图片人审
def test_umod030_flagged_upload_can_be_resolved_and_the_owner_is_told(client):
    """悄悄删掉文件、让页面变成裂图，是最差的一种处理。"""
    user = register(client, "13800120100", "上传的人")
    verify_user(client, user, name="上传")
    admin = make_admin(client, "13800120109")

    # 造一条待人审的记录（机审拿不准那条路径在 V81 已有测试覆盖）
    with SessionLocal() as db:
        from app.modules.files.models import UploadedFile

        db.add(UploadedFile(name="pending-review.png", owner_id=user["id"],
                            content_type="image/png", size_bytes=1234,
                            sha256="0" * 64, moderation_status="review",
                            moderation_labels=["可能含敏感内容"]))
        db.commit()

    rows = client.get("/api/v1/admin/uploads/pending", headers=auth(admin)).json()
    assert [r for r in rows if r["name"] == "pending-review.png"], "人审队列里看不到它"

    r = client.post("/api/v1/admin/uploads/pending-review.png/resolve",
                    json={"action": "reject", "reason": "含违规内容"}, headers=auth(admin))
    assert r.status_code == 200, r.text
    assert _notices(client, user, "一张图片已被移除"), "删了图却没告诉上传者"


# ------------------------------------------------- CS-030 工单
def test_cs030_ticket_can_be_answered_from_the_console(client):
    """用户的求助在这里，不回就是 SLA 是摆设。"""
    user = register(client, "13800120110", "提问的人")
    r = client.post("/api/v1/support/tickets",
                    json={"subject": "提现没到账", "body": "昨天提的现在还没到"},
                    headers=auth(user))
    assert r.status_code in (200, 201), r.text
    admin = make_admin(client, "13800120119")

    rows = client.get("/api/v1/admin/tickets", headers=auth(admin)).json()
    row = [t for t in rows if t["subject"] == "提现没到账"]
    assert row, "工单在后台队列里看不到"

    rr = client.post(f"/api/v1/admin/tickets/{row[0]['id']}/resolve",
                     json={"reply": "已核查，银行处理中，预计今日到账"}, headers=auth(admin))
    assert rr.status_code == 200, rr.text
    got = client.get("/api/v1/notifications?limit=50", headers=auth(user)).json()
    items = got["items"] if isinstance(got, dict) else got
    assert any("银行处理中" in (n.get("body") or "") for n in items), "回复没送到提单人"


# ------------------------------------------------- SECEV-030 IP 解封
def test_secev030_banned_ip_can_be_unbanned_from_the_console(client):
    """误封一个公司的出口 IP，整栋楼的人都进不来。"""
    admin = make_admin(client, "13800120129")
    from app.core import guard
    from app.core.config import settings

    # 走真实机制把这个 IP 打进封禁：连续认证失败到阈值。
    # 直接往表里插一行「ban」也能让测试变绿，但那就不是在验这条路了。
    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD):
        guard.note_auth_failure("203.0.113.7", "login", "测试")

    board = client.get("/api/v1/admin/security", headers=auth(admin)).json()
    assert any(b["ip"] == "203.0.113.7" for b in board["banned"]), "看板里看不到被封的 IP"
    # 阈值等参数来自服务端配置，界面不写死
    assert board["threshold"] > 0 and board["ban_seconds"] > 0

    r = client.post("/api/v1/admin/security/unban", json={"ip": "203.0.113.7"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text
    board = client.get("/api/v1/admin/security", headers=auth(admin)).json()
    assert not any(b["ip"] == "203.0.113.7" for b in board["banned"]), "解封没生效"
