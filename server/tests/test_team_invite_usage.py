"""TEAM-068 邀请链接的使用记录（228 号 spec，V255）。

一条能用 5 次的链接，以前只显示「已用 3/5」：是谁用的、什么时候进来的，所有者不知道；
链接被转发给了不认识的人也看不出来。现在每条链接列出通过它加入的人，成员带上来源，加入时通知所有者。
"""
from app.core.db import SessionLocal
from tests.conftest import auth, register
from tests.test_team_accounts import add_member, make_team, make_user
from tests.test_team_invites import _link
from tests.test_ticket_assign_reply import _titles

API = "/api/v1"


def test_each_link_lists_who_joined_and_owner_is_told(client):
    owner = make_user(client, "13300680001", "老板")
    team_id = make_team(client, owner)
    link = _link(client, owner, team_id, max_uses=3, spend_limit_cents=5000)
    other = _link(client, owner, team_id)
    a = register(client, "13300680002", "小甲")
    b = register(client, "13300680003", "小乙")
    manual = make_user(client, "13300680004", "手动加的")
    add_member(client, team_id, owner, manual)
    assert client.post(f"{API}/team-invites/{link['token']}/accept", headers=auth(a)).status_code == 200
    assert client.post(f"{API}/team-invites/{link['token']}/accept", headers=auth(b)).status_code == 200
    assert any("小甲 通过邀请链接加入了团队" in t for t in _titles(client, owner))
    rows = {r["id"]: r for r in client.get(f"{API}/teams/{team_id}/invite-links", headers=auth(owner)).json()}
    assert [(j["nickname"], j["active"]) for j in rows[link["id"]]["joined"]] == [("小甲", True), ("小乙", True)]
    assert rows[other["id"]]["joined"] == []
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(rows[link["id"]], "TeamInviteLink")
    _assert_shape(rows[link["id"]]["joined"][0], "TeamInviteJoin")
    members = {m["user_id"]: m for m in client.get(f"{API}/teams/{team_id}", headers=auth(owner)).json()["members"]}
    assert members[a["id"]]["invite_id"] == link["id"] and members[manual["id"]]["invite_id"] is None
    # 移出之后记录还在，写明已离开
    client.delete(f"{API}/teams/{team_id}/members/{a['id']}", headers=auth(owner))
    rows = {r["id"]: r for r in client.get(f"{API}/teams/{team_id}/invite-links", headers=auth(owner)).json()}
    assert [(j["nickname"], j["active"]) for j in rows[link["id"]]["joined"]] == [("小甲", False), ("小乙", True)]
