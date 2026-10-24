"""SEC-061d 后台按角色显示板块（165 号 spec，V188）。

界面上「谁能看到哪个板块」写在共享 SDK `packages/core/src/adminSections.ts`；服务端「谁能调哪个接口」写在 `require_role`
（闸门 test_admin_roles.py 的 ROUTE_ROLES 逐个核对）。两份必须一致：每个板块记着它加载数据用的那个接口（probe），
它的 roles 必须**恰好等于**服务端给那个接口的角色——界面多放一个角色，他点开就是 403；少放一个，他有权限却找不到入口。
"""
import re
from pathlib import Path

from app.core.admin_roles import ROLES
from tests.test_admin_roles import ROUTE_ROLES

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / "packages/core/src/adminSections.ts"
ADMIN_PAGE = ROOT / "web/src/pages/Admin.tsx"
LINE = re.compile(r"^\s{2}(\w+): \{ label: '([^']+)', probe: '(\w+ [^']+)', roles: (ALL_ADMIN_ROLES|\[[^\]]*\]) \},$", re.M)


def _sections() -> dict[str, tuple[str, set[str]]]:
    src = SDK.read_text(encoding="utf-8")
    block = src[src.index("export const ADMIN_SECTIONS"):src.index("} satisfies")]
    out = {}
    for key, _label, probe, roles in LINE.findall(block):
        out[key] = (probe, set(ROLES) if roles == "ALL_ADMIN_ROLES" else set(re.findall(r"'(\w+)'", roles)))
    entries = len(re.findall(r"^\s{2}\w+: \{", block, re.M))
    assert out and len(out) == entries, "adminSections.ts 的写法变了、扫描器没认全：先修扫描器（别让闸门空转）"
    return out


def test_every_section_shows_exactly_the_roles_the_server_allows_on_its_probe():
    """ROUTE_ROLES 由 test_admin_roles 与运行中的路由逐个核对过，这里直接用它。"""
    bad = []
    for key, (probe, roles) in _sections().items():
        assert probe in ROUTE_ROLES, f"板块 {key} 的 probe「{probe}」不是一个声明了角色的管理员接口"
        server = set(ROUTE_ROLES[probe])
        if roles != server:
            bad.append(f"{key}：界面给 {sorted(roles)}，服务端 {probe} 给 {sorted(server)}")
    assert not bad, "界面上谁看得到板块，与服务端谁调得了接口不一致：\n  " + "\n  ".join(bad)


def test_every_section_is_actually_gated_on_the_admin_page_and_every_gate_has_a_section():
    page = ADMIN_PAGE.read_text(encoding="utf-8")
    used = set(re.findall(r"see\('(\w+)'\)", page)) | set(re.findall(r"canSeeAdminSection\(me, '(\w+)'\)", page))
    keys = set(_sections())
    assert keys <= used, f"这些板块登记了却没在后台页面上按角色收起：{sorted(keys - used)}"
    assert used <= keys, f"后台页面用了没登记的板块：{sorted(used - keys)}"



# ---------------------------------------------------------------- SEC-061h（295 号 spec，V322）按钮级
def _actions() -> dict[str, tuple[str, set[str]]]:
    src = SDK.read_text(encoding="utf-8")
    start = src.index("export const ADMIN_ACTIONS")
    block = src[start:src.index("} satisfies", start)]
    out = {key: (probe, set(re.findall(r"'(\w+)'", roles))) for key, _label, probe, roles in LINE.findall(block)}
    entries = len(re.findall(r"^\s{2}\w+: \{", block, re.M))
    assert out and len(out) == entries, "ADMIN_ACTIONS 的写法变了、扫描器没认全：先修扫描器"
    return out


def test_every_action_shows_exactly_the_roles_the_server_allows_on_its_endpoint():
    bad = []
    for key, (probe, roles) in _actions().items():
        assert probe in ROUTE_ROLES, f"按钮 {key} 的 probe「{probe}」不是一个声明了角色的管理员接口"
        if roles != set(ROUTE_ROLES[probe]):
            bad.append(f"{key}：界面给 {sorted(roles)}，服务端 {probe} 给 {sorted(ROUTE_ROLES[probe])}")
    assert not bad, "按钮谁按得到，与服务端谁调得了接口不一致：\n  " + "\n  ".join(bad)


def test_every_action_is_actually_gated_on_the_admin_page():
    page = ADMIN_PAGE.read_text(encoding="utf-8")
    used = set(re.findall(r"canDoAdminAction\(me, '(\w+)'\)", page))
    keys = set(_actions())
    assert keys <= used, f"这些按钮登记了却没在后台页面上按角色收起：{sorted(keys - used)}"
    assert used <= keys, f"后台页面用了没登记的按钮：{sorted(used - keys)}"


def test_banning_from_a_report_needs_compliance_like_banning_directly(client):
    from tests.conftest import auth, register
    from tests.test_ticket_assign_reply import _admin

    sup = _admin(client, "13800400001", ["support"])
    comp = _admin(client, "13800400002", ["compliance"])
    bad = register(client, "13800400003", "被举报的人")
    reporter = register(client, "13800400004", "举报的人")

    def report():
        r = client.post("/api/v1/reports", json={"target_type": "user", "target_id": bad["id"], "reason": "骚扰"},
                        headers=auth(reporter))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    rid = report()
    r = client.post(f"/api/v1/admin/reports/{rid}/resolve", json={"action": "ban_user"}, headers=auth(sup))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_role_required"
    assert "合规" in r.json()["detail"]["message"] and "驳回或下架" in r.json()["detail"]["message"]
    assert client.get("/api/v1/users/me", headers=auth(bad)).status_code == 200, "没被封"
    still = client.get("/api/v1/admin/reports", headers=auth(sup)).json()
    assert any(x["id"] == rid for x in still), "举报仍在队列里，没被标成已处理"
    ok = client.post(f"/api/v1/admin/reports/{rid}/resolve", json={"action": "dismiss"}, headers=auth(sup))
    assert ok.status_code == 200, "客服照旧能驳回"
    rid2 = report()
    assert client.post(f"/api/v1/admin/reports/{rid2}/resolve", json={"action": "ban_user"},
                       headers=auth(comp)).status_code == 200, "合规能从举报里封禁"
