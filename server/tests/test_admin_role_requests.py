"""SEC-061i 临时角色的申请与审批（315 号 spec，V342）。

以前临时角色只能由超级管理员直接给：要的人没有地方申请，给的人也没有一条「谁、为什么要」的记录。现在本人申请、写理由，
另一位超级管理员批准后才生效（与直接授予同一套规则、同一条审计），驳回要写理由；不能批自己的申请。
"""
from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.admin.models import AdminAudit
from app.modules.notification.models import Notification
from tests.conftest import auth
from tests.test_ticket_assign_reply import _admin

API = "/api/v1"
RQ = f"{API}/admin/role-requests"


def test_request_then_another_super_approves_and_the_role_works(client):
    boss1 = _admin(client, "13800342001", ["super"])
    boss2 = _admin(client, "13800342002", ["super"])
    agent = _admin(client, "13800342003", ["support"])
    colleague = _admin(client, "13800342004", ["support"])
    theirs = client.post(RQ, json={"role": "ops", "hours": 8, "reason": "同事自己的申请"}, headers=auth(colleague)).json()
    r = client.post(RQ, json={"role": "finance", "hours": 24, "reason": "月底帮财务对账"}, headers=auth(agent))
    assert r.status_code == 201 and r.json()["status"] == "pending", r.text
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "AdminRoleRequest")
    rid = r.json()["id"]
    assert client.get(f"{API}/admin/platform-finance", headers=auth(agent)).status_code == 403, "批之前不生效"
    with SessionLocal() as db:
        told = {n.user_id for n in db.query(Notification).filter(Notification.title.like("%申请临时「财务」角色%"))}
    assert told == {boss1["id"], boss2["id"]}, "通知每一位超级管理员，不通知别的管理员"
    dup = client.post(RQ, json={"role": "finance", "hours": 8, "reason": "再申请一次"}, headers=auth(agent))
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "role_request_pending"

    mine = client.get(RQ, headers=auth(agent)).json()
    assert [x["id"] for x in mine] == [rid], "其他管理员只看到自己的"
    assert theirs["id"] in {x["id"] for x in client.get(RQ, headers=auth(boss2)).json()}
    ok = client.post(f"{RQ}/{rid}/approve", headers=auth(boss1))
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["decided_by"] == boss1["id"]
    _assert_shape(ok.json(), "AdminRoleRequest")
    assert client.get(f"{API}/admin/platform-finance", headers=auth(agent)).status_code == 200, "批了就生效"
    with SessionLocal() as db:
        u = db.get(User, agent["id"])
        assert "finance" in (u.admin_role_until or {}), "是临时角色，到点失效"
        audit = db.query(AdminAudit).filter(AdminAudit.action == "grant_temporary_role",
                                            AdminAudit.target_id == agent["id"]).one()
        assert audit.admin_id == boss1["id"] and f"申请 #{rid}" in audit.detail and "月底帮财务对账" in audit.detail
    again = client.post(f"{RQ}/{rid}/approve", headers=auth(boss2))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "role_request_decided"


def test_rules_reject_self_approval_and_who_can_do_what(client):
    boss1 = _admin(client, "13800342011", ["super"])
    boss2 = _admin(client, "13800342012", ["super"])
    agent = _admin(client, "13800342013", ["support"])
    for role, code in (("super", "admin_temp_super_forbidden"), ("support", "admin_role_already_permanent"),
                       ("nobody", "admin_role_unknown")):
        r = client.post(RQ, json={"role": role, "hours": 8, "reason": "试一下"}, headers=auth(agent))
        assert r.status_code in (400, 409) and r.json()["detail"]["code"] == code, role
    assert client.post(RQ, json={"role": "ops", "hours": 721, "reason": "太久"}, headers=auth(agent)).status_code == 422

    own = client.post(RQ, json={"role": "finance", "hours": 8, "reason": "顶岗"}, headers=auth(boss1)).json()
    r = client.post(f"{RQ}/{own['id']}/approve", headers=auth(boss1))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "role_request_self", "不能批自己的申请"

    req = client.post(RQ, json={"role": "ops", "hours": 8, "reason": "帮忙上架服务包"}, headers=auth(agent)).json()
    assert client.post(f"{RQ}/{req['id']}/approve", headers=auth(agent)).status_code == 403, "只有超级管理员能批"
    assert client.post(f"{RQ}/{req['id']}/reject", json={"note": "x"}, headers=auth(boss2)).status_code == 422, "驳回要写理由"
    no = client.post(f"{RQ}/{req['id']}/reject", json={"note": "这周运营人手够"}, headers=auth(boss2))
    assert no.status_code == 200 and no.json()["status"] == "rejected" and no.json()["decision_note"] == "这周运营人手够"
    assert client.get(f"{API}/admin/packs", headers=auth(agent)).status_code == 403, "驳回不生效"
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.user_id == agent["id"],
                                             Notification.title == "你的临时角色申请没有通过").count() == 1
    every = {x["id"] for x in client.get(RQ, headers=auth(boss2)).json()}
    assert {own["id"], req["id"]} <= every, "超级管理员看得到全部"
    assert client.post(f"{RQ}/999999/approve", headers=auth(boss2)).status_code == 404


def test_approval_rechecks_the_rules_at_that_moment(client):
    boss = _admin(client, "13800342021", ["super"])
    agent = _admin(client, "13800342022", ["support"])
    req = client.post(RQ, json={"role": "finance", "hours": 8, "reason": "对账"}, headers=auth(agent)).json()
    client.put(f"{API}/admin/admins/{agent['id']}/roles", json={"roles": ["support", "finance"]}, headers=auth(boss))
    r = client.post(f"{RQ}/{req['id']}/approve", headers=auth(boss))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "admin_role_already_permanent", "申请后已经长期给了"
