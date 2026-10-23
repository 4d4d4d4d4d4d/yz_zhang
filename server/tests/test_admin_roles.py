"""SEC-061b 管理员分级（141 号 spec）。

此前管理员只有一个 `is_admin` 位：客服能批提现、运营能裁纠纷、谁都能撤销别人的资质。
V139 补的是「写明理由 + 审计」——事后可查；这一批补的是**事前按职责拦**。

闸门：
1. 每一个管理员接口都声明了角色（`require_role`），并且和下面这张表一致——改了谁能做什么，表就得跟着改，评审时看得见；
2. 角色真的拦得住（财务做不了合规的事，客服批不了提现……）；
3. 没分过角色的管理员按超级管理员对待（兼容此前全部管理员），并在「管理员与角色」里标成未分级；
4. 只有超级管理员能分配角色、至少留一位超级管理员、每次分配进审计。
"""
import pytest
from fastapi.routing import APIRoute

from app.core.admin_roles import ANY, ROLES
from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.admin.models import AdminAudit
from tests.conftest import auth, make_admin, register

API = "/api/v1"

# 谁能做什么。ANY = 任何管理员（只读的总览）。改这张表就是改权限：评审时要说清为什么
ROUTE_ROLES = {
    "GET /admin/admins": ('super',),
    "GET /admin/agents": ('ops',),
    "GET /admin/aml/activities": ('compliance',),
    "GET /admin/aml/stats": ('compliance',),
    "GET /admin/audit-log": ('compliance',),
    "GET /admin/audit-log/export": ('compliance',),
    "GET /admin/audit-log/verify": ('compliance',),
    "GET /admin/platform-finance/periods": ('finance',),
    "GET /admin/platform-finance/settle-requests": ('finance',),
    "POST /admin/platform-finance/settle-requests/{request_id}/approve": ('finance',),
    "POST /admin/platform-finance/settle-requests/{request_id}/reject": ('finance',),
    "GET /admin/platform-finance/periods/export": ('finance',),
    "POST /admin/platform-finance/lock": ('finance',),          # FIN-063（223 号 spec）
    "GET /admin/tickets/{ticket_id}": ('support',),             # ESCA-058（221 号 spec）
    "GET /admin/support/my-categories": ('support',),           # ESCA-061（234 号 spec）
    "PUT /admin/support/my-categories": ('support',),
    "POST /admin/support/my-pause": ('support',),
    "PUT /admin/support/my-schedule": ('support',),
    "GET /admin/api-quota-requests": ('ops',),
    "GET /admin/platform-finance/gmv-tax": ('finance',),        # FIN-062（242 号 spec）
    "GET /admin/platform-finance/gmv-tax/export": ('finance',),  # FIN-066（249 号 spec）                  # API-057（241 号 spec）
    "POST /admin/api-quota-requests/{request_id}/approve": ('ops',),
    "POST /admin/api-quota-requests/{request_id}/reject": ('ops',),               # ESCA-065（240 号 spec）
    "DELETE /admin/support/my-pause": ('support',),
    "GET /admin/support/agents": ('super',),
    "GET /admin/announcements/{announcement_id}/read-curve": ('ops',),          # NTF-072（261 号 spec）
    "GET /admin/announcements/{announcement_id}/read-by-category": ('ops',),   # NTF-071（252 号 spec）                    # ESCA-066（248 号 spec）
    "DELETE /admin/support/agents/{user_id}/pause": ('super',),
    "POST /admin/support/agents/{user_id}/pause": ('super',),   # ESCA-067（256 号 spec）
    "GET /admin/api-accounts/quotas": ('ops',),                 # API-056（235 号 spec）
    "PUT /admin/api-accounts/{user_id}/quota": ('ops',),
    "DELETE /admin/api-accounts/{user_id}/quota": ('ops',),
    "GET /admin/campaigns": ('ops',),
    "GET /admin/certifications": ('compliance',),
    "GET /admin/certifications/pending": ('compliance',),
    "GET /admin/coupons": ('ops', 'finance'),
    "GET /admin/funnels": ('ops',),
    "GET /admin/client-errors": ('ops',),   # APP-094 哪一页常坏（184 号 spec）
    "GET /admin/knowledge/overview": ('ops',),
    "GET /admin/knowledge/thresholds/{category}/pairs": ('ops',),
    "GET /admin/knowledge/undecided": ('ops',),
    "GET /admin/knowledge/units": ('ops',),
    "GET /admin/market-health": ('ops',),
    "GET /admin/matching-config": ('ops',),
    "GET /admin/metrics": ANY,
    "GET /admin/north-star": ANY,
    "GET /admin/packs": ('ops',),
    "GET /admin/packs/radar": ('ops',),
    "POST /admin/packs/radar/draft-knowledge": ('ops',),
    # LAW-060 / SCN-114（163 号 spec）：法律知识归合规
    "GET /admin/legal/faqs": ('compliance',),
    "POST /admin/legal/faqs": ('compliance',),
    "PUT /admin/legal/faqs/{faq_id}": ('compliance',),
    "POST /admin/legal/faqs/radar-draft": ('compliance',),
    "POST /admin/legal/faqs/{faq_id}/submit": ('compliance',),
    "POST /admin/legal/faqs/{faq_id}/approve": ('compliance',),
    "POST /admin/legal/faqs/{faq_id}/reject": ('compliance',),
    "POST /admin/legal/faqs/{faq_id}/retire": ('compliance',),
    "POST /admin/legal/faqs/{faq_id}/renew": ('compliance',),
    "POST /admin/tickets/{ticket_id}/priority": ('support',),
    # SEC-061e（171 号 spec）临时授予与提前收回
    "POST /admin/admins/{user_id}/temporary-roles": ('super',),
    "POST /admin/admins/{user_id}/temporary-roles/{role}/revoke": ('super',),
    "GET /admin/platform-finance": ('finance',),
    "GET /admin/queues": ANY,
    "GET /admin/reports": ('support', 'compliance'),
    "GET /admin/roles": ANY,
    "GET /admin/sandbox/models": ('ops',),
    "GET /admin/security": ('compliance',),
    "GET /admin/settlements/verify": ('finance',),
    "GET /admin/skill-concepts": ('ops',),
    "GET /admin/teams/pending": ('compliance',),
    "GET /admin/tickets": ('support',),
    "GET /admin/uploads/pending": ('compliance',),
    "GET /admin/users": ('support', 'compliance'),
    "GET /admin/users/{user_id}/ban-impact": ('support', 'compliance'),
    "GET /admin/vendors": ANY,
    "GET /events/dead-letters": ('ops',),
    "GET /finance/tax-ledger": ('finance',),
    "GET /wallet/withdraw-requests": ('finance',),
    "PATCH /admin/agents/{agent_user_id}": ('ops',),
    "PATCH /admin/categories/{category_id}": ('ops',),
    "PATCH /admin/cities/{city_id}": ('ops',),
    "PATCH /admin/knowledge/clusters/{cluster_id}": ('ops',),
    "PATCH /admin/knowledge/units/{unit_id}": ('ops',),
    "PATCH /admin/sandbox/models/{model_id}": ('ops',),
    "POST /admin/agents": ('ops',),
    "POST /admin/aml/activities/{activity_id}/review": ('compliance',),
    "POST /admin/announcements": ('ops',),
    "POST /admin/announcements/preview": ('ops',),
    "GET /admin/announcements": ('ops',),
    "POST /admin/announcements/{announcement_id}/cancel": ('ops',),
    "POST /admin/announcements/{announcement_id}/revoke": ('ops',),
    "POST /admin/campaigns": ('ops',),
    "POST /admin/categories": ('ops',),
    "POST /admin/certifications/{application_id}/decide": ('compliance',),
    "POST /admin/certifications/{application_id}/revoke": ('compliance',),
    "POST /admin/cities": ('ops',),
    "POST /admin/coupons": ('ops',),
    "POST /admin/coupons/{coupon_id}/pause": ('ops',),
    "POST /admin/knowledge/cards/{card_id}/assign": ('ops',),
    "POST /admin/knowledge/clusters/{cluster_id}/merge": ('ops',),
    "POST /admin/knowledge/clusters/{cluster_id}/units": ('ops',),
    "POST /admin/knowledge/tasks/{task_id}/retract": ('ops',),
    "POST /admin/knowledge/thresholds/{category}/calibrate": ('ops',),
    "POST /admin/packs": ('ops',),
    "POST /admin/packs/import-seeds": ('ops',),
    "POST /admin/packs/validate": ('ops',),
    "POST /admin/packs/{pack_id}/approve": ('ops',),
    "POST /admin/packs/{pack_id}/reject": ('ops',),
    "POST /admin/packs/{pack_id}/retire": ('ops',),
    "POST /admin/packs/{pack_id}/submit": ('ops',),
    "POST /admin/platform-finance/settle": ('finance',),
    "POST /admin/reports/{report_id}/resolve": ('support', 'compliance'),
    "POST /admin/sandbox/models": ('ops',),
    "POST /admin/sandbox/models/{model_id}/publish": ('ops',),
    "POST /admin/sandbox/models/{model_id}/retire": ('ops',),
    "POST /admin/security/unban": ('compliance',),
    "POST /admin/skill-concepts": ('ops',),
    "POST /admin/skill-concepts/{concept_id}/retire": ('ops',),
    "POST /admin/subsidy-pool/fund": ('finance',),
    "POST /admin/teams/{team_id}/verify": ('compliance',),
    "POST /admin/tickets/{ticket_id}/resolve": ('support',),
    "POST /admin/tickets/{ticket_id}/claim": ('support',),
    "POST /admin/tickets/{ticket_id}/reply": ('support',),
    "POST /admin/tickets/{ticket_id}/assign": ('super',),
    "POST /admin/uploads/{name}/resolve": ('compliance',),
    "POST /admin/users/{user_id}/ban": ('compliance',),
    "POST /admin/users/{user_id}/unban": ('compliance',),
    "POST /disputes/{dispute_id}/appeal-verdict": ('arbiter',),
    "POST /disputes/{dispute_id}/verdict": ('arbiter',),
    "POST /wallet/withdraw-requests/{request_id}/approve": ('finance',),
    "POST /wallet/withdraw-requests/{request_id}/reject": ('finance',),
    "PUT /admin/admins/{user_id}/roles": ('super',),
    "PUT /admin/matching-config": ('ops',),
    "PUT /admin/packs/{pack_id}": ('ops',),
}


def _walk(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        inner = getattr(r, "original_router", None) or getattr(r, "app", None)
        sub = getattr(inner, "routes", None)
        if sub and inner is not r:
            yield from _walk(sub)


def _calls(d):
    for x in d.dependencies:
        yield x.call
        yield from _calls(x)


def test_every_admin_endpoint_declares_its_roles_and_matches_the_table():
    from app.main import app

    found, undeclared = {}, []
    for r in _walk(app.routes):
        cs = list(_calls(r.dependant))
        roles = [c._roles for c in cs if hasattr(c, "_roles")]
        is_admin_route = any(getattr(c, "__name__", "") == "require_admin" for c in cs)
        for m in sorted(r.methods):
            key = f"{m} {r.path.removeprefix('/api/v1')}"
            if is_admin_route and not roles:
                undeclared.append(key)
            if roles:
                found[key] = "ANY" if tuple(roles[0]) == ANY else tuple(roles[0])
    assert not undeclared, f"这些管理员接口没声明角色（用 require_role）：{undeclared}"
    expected = {k: ("ANY" if v == ANY else v) for k, v in ROUTE_ROLES.items()}
    assert found == expected, {k: (found.get(k), expected.get(k)) for k in set(found) | set(expected)
                               if found.get(k) != expected.get(k)}


def test_money_and_verdicts_are_not_open_to_everyone():
    """红线：动钱的、裁决的、看证件与私聊的，都不是「任何管理员」。"""
    for key in ("POST /wallet/withdraw-requests/{request_id}/approve", "POST /admin/platform-finance/settle",
                "POST /admin/subsidy-pool/fund", "POST /disputes/{dispute_id}/verdict",
                "POST /admin/certifications/{application_id}/decide", "PUT /admin/admins/{user_id}/roles",
                "POST /admin/admins/{user_id}/temporary-roles"):
        assert ROUTE_ROLES[key] != ANY and "support" not in ROUTE_ROLES[key] and "ops" not in ROUTE_ROLES[key], key


# ------------------------------------------------------------------ 行为
def _admin(client, phone, roles=None):
    a = make_admin(client, phone, f"管理员{phone[-2:]}")
    if roles is not None:
        with SessionLocal() as db:
            db.get(User, a["id"]).admin_roles = roles
            db.commit()
    return a


def test_roles_actually_block(client):
    fin = _admin(client, "13800210001", ["finance"])
    sup = _admin(client, "13800210002", ["support"])
    h_fin, h_sup = auth(fin), auth(sup)
    assert client.get(f"{API}/wallet/withdraw-requests", headers=h_fin).status_code == 200
    r = client.get(f"{API}/wallet/withdraw-requests", headers=h_sup)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_role_required"
    assert "财务" in r.json()["detail"]["message"] and "客服" in r.json()["detail"]["message"], "说清要什么角色、你是什么角色"
    assert client.get(f"{API}/admin/tickets", headers=h_sup).status_code == 200
    assert client.get(f"{API}/admin/certifications/pending", headers=h_fin).json()["detail"]["code"] == "admin_role_required"
    # 只读总览任何管理员都能看
    assert client.get(f"{API}/admin/queues", headers=h_sup).status_code == 200
    # 不是管理员照旧是 admin_required
    user = register(client, "13800210003", "普通人")
    assert client.get(f"{API}/admin/tickets", headers=auth(user)).json()["detail"]["code"] == "admin_required"


def test_unclassified_admins_keep_full_access_and_are_flagged(client):
    legacy = _admin(client, "13800210004")
    h = auth(legacy)
    assert client.get(f"{API}/wallet/withdraw-requests", headers=h).status_code == 200
    assert client.get(f"{API}/admin/certifications/pending", headers=h).status_code == 200
    me = client.get(f"{API}/users/me", headers=h).json()
    assert me["admin_roles"] == ["super"]
    lst = client.get(f"{API}/admin/admins", headers=h).json()
    assert lst["unclassified"] == 1 and lst["admins"][0]["unclassified"] is True
    plain = register(client, "13800210005", "普通人")
    assert client.get(f"{API}/users/me", headers=auth(plain)).json()["admin_roles"] == []


def test_only_super_assigns_roles_keeps_one_super_and_audits(client):
    boss = _admin(client, "13800210006", ["super"])
    ops = _admin(client, "13800210007", ["ops"])
    url = f"{API}/admin/admins/{ops['id']}/roles"
    r = client.put(url, json={"roles": ["ops", "finance"]}, headers=auth(ops))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_role_required", "不能给自己加角色"
    r = client.put(url, json={"roles": ["ops", "finance"]}, headers=auth(boss))
    assert r.status_code == 200 and r.json()["roles"] == ["finance", "ops"]
    assert client.get(f"{API}/wallet/withdraw-requests", headers=auth(ops)).status_code == 200
    bad = client.put(url, json={"roles": ["janitor"]}, headers=auth(boss))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "admin_role_unknown"
    last = client.put(f"{API}/admin/admins/{boss['id']}/roles", json={"roles": ["finance"]}, headers=auth(boss))
    assert last.status_code == 409 and last.json()["detail"]["code"] == "admin_last_super"
    plain = register(client, "13800210008", "普通人")
    nf = client.put(f"{API}/admin/admins/{plain['id']}/roles", json={"roles": ["ops"]}, headers=auth(boss))
    assert nf.status_code == 404 and nf.json()["detail"]["code"] == "admin_target_not_admin"
    with SessionLocal() as db:
        audits = [a.detail for a in db.query(AdminAudit).filter(AdminAudit.action == "set_admin_roles")]
    assert audits == ["['ops'] -> ['finance', 'ops']"]
    # 有另一位超级管理员时，可以把自己降下来
    client.put(url, json={"roles": ["super"]}, headers=auth(boss))
    assert client.put(f"{API}/admin/admins/{boss['id']}/roles", json={"roles": ["finance"]}, headers=auth(boss)).status_code == 200


def test_role_catalog_lists_every_role_and_mine(client):
    sup = _admin(client, "13800210009", ["support", "arbiter"])
    r = client.get(f"{API}/admin/roles", headers=auth(sup)).json()
    assert [x["key"] for x in r["roles"]] == list(ROLES) and r["mine"] == ["arbiter", "support"]


def test_private_chats_and_identity_images_need_arbiter_or_compliance(client):
    from tests.test_authz_matrix import _chat
    from app.modules.files.models import UploadedFile

    _a, _b, cid = _chat(client)
    fin = _admin(client, "13800210010", ["finance"])
    arb = _admin(client, "13800210011", ["arbiter"])
    url = f"{API}/conversations/{cid}/messages"
    why = {"reason": "纠纷举证 #3：核对双方约定"}
    r = client.get(url, params=why, headers=auth(fin))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_role_required"
    assert client.get(url, params=why, headers=auth(arb)).status_code == 200
    owner = register(client, "13800210012", "持证人")
    with SessionLocal() as db:
        db.add(UploadedFile(name="secret-id-roles", owner_id=owner["id"], sha256="x", content_type="image/png",
                            size_bytes=1, moderation_status="pass", moderation_labels=[], sensitive=True))
        db.commit()
    f = client.get(f"{API}/files/secret-id-roles/secure", params={"reason": "法定调取 2026-002"}, headers=auth(fin))
    assert f.status_code == 403 and f.json()["detail"]["code"] == "admin_role_required"
    ok = client.get(f"{API}/files/secret-id-roles/secure", params={"reason": "法定调取 2026-002"}, headers=auth(arb))
    assert ok.status_code in (200, 404)


def test_manual_reconcile_is_finance(client):
    ops = _admin(client, "13800210013", ["ops"])
    fin = _admin(client, "13800210014", ["finance"])
    r = client.post(f"{API}/admin/jobs/reconcile", headers=auth(ops))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_role_required"
    assert client.post(f"{API}/admin/jobs/reconcile", headers=auth(fin)).status_code == 200


def test_erasing_an_admin_clears_roles(client):
    from app.modules.account.deletion import erase_personal_data

    a = _admin(client, "13800210015", ["finance"])
    with SessionLocal() as db:
        u = db.get(User, a["id"])
        erase_personal_data(db, u)
        db.commit()
        u = db.get(User, a["id"])
        assert u.is_admin is False and u.admin_roles == []


@pytest.mark.parametrize("bad", [(), ("janitor",)])
def test_require_role_refuses_unknown_roles_at_import_time(bad):
    from app.core.admin_roles import require_role

    with pytest.raises(ValueError):
        require_role(*bad)


def test_responses_match_sdk_types(client):
    from tests.test_client_shape_alignment import _assert_shape

    boss = _admin(client, "13800210016", ["super"])
    catalog = client.get(f"{API}/admin/roles", headers=auth(boss)).json()
    _assert_shape(catalog, "AdminRoleCatalog")
    first_role = catalog["roles"][0]
    _assert_shape(first_role, "AdminRoleDef")
    lst = client.get(f"{API}/admin/admins", headers=auth(boss)).json()
    _assert_shape(lst, "AdminList")
    row = lst["admins"][0]
    _assert_shape(row, "AdminRow")
