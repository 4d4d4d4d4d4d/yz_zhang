"""TEAM-075 管理员降级或离开时名下待批的指派交回轮转（254 号 spec，V281）。

236 / 243 / 250 号让一笔申请可以指派给某位管理员。但他被降为成员、或被移出团队之后，申请仍然挂在他名下：
他批不了，第一轮催办也只叫他——员工的钱就卡住了。现在这种时候指派交回轮转：轮流模式轮给下一位并通知，
默认模式清掉指派（谁都能批）。
"""
from app.core.db import SessionLocal
from app.modules.team.models import SpendRequest
from tests.conftest import auth
from tests.test_team_accounts import add_member, make_user
from tests.test_team_approval_notice import _request, _team_with_staff, notices

API = "/api/v1"


def _assignee(rid: int):
    with SessionLocal() as db:
        return db.get(SpendRequest, rid).assignee_id


def test_demoted_admin_hands_back_in_rotate_mode_and_next_one_is_told(client):
    owner, admin, staff, team_id = _team_with_staff(client, ("13300645001", "13300645002", "13300645003"))
    admin2 = make_user(client, "13300645004", "财务主管")
    add_member(client, team_id, owner, admin2, role="admin", limit=50000)
    client.patch(f"{API}/teams/{team_id}/approval-mode", json={"mode": "rotate"}, headers=auth(owner))
    req = _request(client, team_id, staff)
    client.post(f"{API}/teams/{team_id}/spends/{req['id']}/assign", json={"assignee_id": admin["id"]}, headers=auth(owner))
    done = _request(client, team_id, staff)
    client.post(f"{API}/teams/{team_id}/spends/{done['id']}/assign", json={"assignee_id": admin["id"]}, headers=auth(owner))
    client.post(f"{API}/teams/{team_id}/spends/{done['id']}/decide", json={"approve": True}, headers=auth(owner))
    r = client.patch(f"{API}/teams/{team_id}/members/{admin['id']}", json={"role": "member"}, headers=auth(owner))
    assert r.status_code == 200 and r.json()["role"] == "member", "响应与以前一样"
    now = _assignee(req["id"])
    assert now in (owner["id"], admin2["id"]) and now != admin["id"], "交回轮转：轮给下一位能批的人"
    assert len(notices(now, "支出待审批（原指派人已不能审批）")) == 1
    assert _assignee(done["id"]) == admin["id"], "已处理的不动"


def test_removed_admin_in_default_mode_clears_assignment(client):
    owner, admin, staff, team_id = _team_with_staff(client, ("13300645011", "13300645012", "13300645013"))
    req = _request(client, team_id, staff)
    client.post(f"{API}/teams/{team_id}/spends/{req['id']}/assign", json={"assignee_id": admin["id"]}, headers=auth(owner))
    assert _assignee(req["id"]) == admin["id"]
    r = client.delete(f"{API}/teams/{team_id}/members/{admin['id']}", headers=auth(owner))
    assert r.status_code == 200
    assert _assignee(req["id"]) is None, "默认模式：清掉指派，谁都能批"
    assert notices(owner["id"], "支出待审批（原指派人已不能审批）") == []
    # 只改额度（还是管理员）：不动指派
    owner2, admin3, staff2, team2 = _team_with_staff(client, ("13300645021", "13300645022", "13300645023"))
    req2 = _request(client, team2, staff2)
    client.post(f"{API}/teams/{team2}/spends/{req2['id']}/assign", json={"assignee_id": admin3["id"]}, headers=auth(owner2))
    client.patch(f"{API}/teams/{team2}/members/{admin3['id']}", json={"spend_limit_cents": 80000}, headers=auth(owner2))
    assert _assignee(req2["id"]) == admin3["id"]
