"""SEC-061e 管理员角色的临时授予（171 号 spec，V198）。

值班、休假顶岗时只能永久加角色：顶岗结束忘了收回，权限就一直在那儿（权限蔓延）。现在超级管理员可以临时给
一个角色（最长 30 天，写理由、进审计、通知本人），到点自动失效；也可以提前收回。
最要紧的一条：临时角色只能加在已有长期角色的人身上，而且全部到期的人是「没有角色」，不会变成超级管理员。
"""
from datetime import timedelta

from app.core.admin_roles import roles_of
from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.admin.models import AdminAudit
from tests.conftest import auth
from tests.test_ticket_assign_reply import _admin, _titles

API = "/api/v1/admin/admins"


def _expire(uid, role):
    with SessionLocal() as db:
        u = db.get(User, uid)
        until = dict(u.admin_role_until)
        until[role] = (utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        u.admin_role_until = until
        db.commit()


def test_temporary_role_works_until_it_expires_then_access_is_gone(client):
    sup = _admin(client, "13800340001", ["super"])
    fin = _admin(client, "13800340002", ["finance"])
    assert client.get("/api/v1/admin/tickets", headers=auth(fin)).status_code == 403
    r = client.post(f"{API}/{fin['id']}/temporary-roles", json={"role": "support", "hours": 48, "reason": "国庆客服值班"}, headers=auth(sup))
    assert r.status_code == 200, r.text
    row = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(row, "AdminRow")
    assert row["roles"] == ["finance", "support"] and row["temporary"][0]["role"] == "support"
    assert client.get("/api/v1/admin/tickets", headers=auth(fin)).status_code == 200, "临时角色生效"
    assert any("临时授予「客服」" in t for t in _titles(client, fin))
    with SessionLocal() as db:
        a = db.query(AdminAudit).filter(AdminAudit.action == "grant_temporary_role").one()
        assert "国庆客服值班" in a.detail and a.admin_id == sup["id"]
    _expire(fin["id"], "support")
    assert client.get("/api/v1/admin/tickets", headers=auth(fin)).status_code == 403, "到点自动失效"
    me = client.get("/api/v1/users/me", headers=auth(fin)).json()
    assert me["admin_roles"] == ["finance"], "/users/me 给的是生效的角色：界面跟着收起"
    listed = next(x for x in client.get(API, headers=auth(sup)).json()["admins"] if x["user_id"] == fin["id"])
    assert listed["temporary"] == [] and listed["roles"] == ["finance"]


def test_all_roles_expired_means_no_roles_never_super(client):
    """兜底：就算数据里只剩临时角色（例如长期角色被整组改掉之外的路径删掉），全部到期也不能变成超级管理员。"""
    sup = _admin(client, "13800340011", ["super"])
    x = _admin(client, "13800340012", ["ops"])
    with SessionLocal() as db:
        u = db.get(User, x["id"])
        u.admin_roles = ["support"]
        u.admin_role_until = {"support": (utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        db.commit()
        assert roles_of(db.get(User, x["id"])) == set()
    assert client.get("/api/v1/admin/admins", headers=auth(x)).status_code == 403, "绝不能落成超级管理员"
    assert client.get("/api/v1/admin/metrics", headers=auth(x)).status_code == 403
    _ = sup


def test_rules_super_only_no_temp_super_needs_permanent_role_and_hours_cap(client):
    sup = _admin(client, "13800340021", ["super"])
    fin = _admin(client, "13800340022", ["finance"])
    unclassified = _admin(client, "13800340023", [])
    other = _admin(client, "13800340024", ["ops"])
    body = {"role": "support", "hours": 24, "reason": "顶岗"}
    assert client.post(f"{API}/{fin['id']}/temporary-roles", json=body, headers=auth(other)).status_code == 403, "只有超级管理员能给"
    s = client.post(f"{API}/{fin['id']}/temporary-roles", json={**body, "role": "super"}, headers=auth(sup))
    assert s.status_code == 400 and s.json()["detail"]["code"] == "admin_temp_super_forbidden"
    u = client.post(f"{API}/{unclassified['id']}/temporary-roles", json=body, headers=auth(sup))
    assert u.status_code == 409 and u.json()["detail"]["code"] == "admin_temp_needs_permanent"
    p = client.post(f"{API}/{fin['id']}/temporary-roles", json={**body, "role": "finance"}, headers=auth(sup))
    assert p.status_code == 409 and p.json()["detail"]["code"] == "admin_role_already_permanent"
    long_ = client.post(f"{API}/{fin['id']}/temporary-roles", json={**body, "hours": 721}, headers=auth(sup))
    assert long_.status_code == 422


def test_revoke_early_and_set_roles_makes_everything_permanent(client):
    sup = _admin(client, "13800340031", ["super"])
    fin = _admin(client, "13800340032", ["finance"])
    client.post(f"{API}/{fin['id']}/temporary-roles", json={"role": "support", "hours": 24, "reason": "顶岗"}, headers=auth(sup))
    r = client.post(f"{API}/{fin['id']}/temporary-roles/support/revoke", headers=auth(sup)).json()
    assert r["roles"] == ["finance"] and r["temporary"] == []
    assert client.get("/api/v1/admin/tickets", headers=auth(fin)).status_code == 403
    no = client.post(f"{API}/{fin['id']}/temporary-roles/finance/revoke", headers=auth(sup))
    assert no.status_code == 409 and no.json()["detail"]["code"] == "admin_role_not_temporary"
    client.post(f"{API}/{fin['id']}/temporary-roles", json={"role": "ops", "hours": 24, "reason": "活动周"}, headers=auth(sup))
    whole = client.put(f"{API}/{fin['id']}/roles", json={"roles": ["finance", "ops"]}, headers=auth(sup)).json()
    assert whole["temporary"] == [], "整组设置的都是长期角色"
