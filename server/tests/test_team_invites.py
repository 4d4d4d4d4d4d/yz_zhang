"""TEAM-066 团队邀请链接（147 号 spec）。

此前加人只能由所有者填对方的用户编号：对方得先把编号报过来，而编号藏在个人空间地址里。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.team.models import TeamInvite
from tests.conftest import auth, register
from tests.test_team_accounts import make_team, make_user

API = "/api/v1"


def _link(client, owner, team_id, **body):
    r = client.post(f"{API}/teams/{team_id}/invite-links", json=body, headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()


def test_owner_creates_link_invitee_previews_and_joins_with_the_preset_limit(client):
    owner = make_user(client, "13800260001", "老板")
    team_id = make_team(client, owner, "某某工作室")
    link = _link(client, owner, team_id, spend_limit_cents=30000)
    assert link["path"] == f"/teams/join/{link['token']}" and link["state"] == "active" and "唯一一次" in link["warning"]
    with SessionLocal() as db:
        assert db.query(TeamInvite).one().token_hash != link["token"], "库里只存哈希"
    guest = register(client, "13800260002", "小林")
    p = client.get(f"{API}/team-invites/{link['token']}", headers=auth(guest)).json()
    assert (p["team_name"], p["inviter_nickname"], p["role"], p["spend_limit_cents"], p["already_member"]) == \
        ("某某工作室", "老板", "member", 30000, False)
    r = client.post(f"{API}/team-invites/{link['token']}/accept", headers=auth(guest))
    assert r.status_code == 200 and r.json()["spend_limit_cents"] == 30000 and r.json()["role"] == "member"
    members = {m["user_id"]: m for m in client.get(f"{API}/teams/{team_id}", headers=auth(owner)).json()["members"]}
    assert members[guest["id"]]["role"] == "member" and members[guest["id"]]["spend_limit_cents"] == 30000
    # 一次性的链接用完就失效
    other = register(client, "13800260003", "路人")
    r = client.get(f"{API}/team-invites/{link['token']}", headers=auth(other))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "team_invite_invalid"
    assert client.get(f"{API}/teams/{team_id}/invite-links", headers=auth(owner)).json()[0]["state"] == "used_up"


def test_multi_use_expiry_revoke_and_already_member(client):
    owner = make_user(client, "13800260004", "老板")
    team_id = make_team(client, owner)
    link = _link(client, owner, team_id, max_uses=2)
    a, b, c = (register(client, f"1380026001{i}", f"人{i}") for i in range(3))
    for u in (a, b):
        assert client.post(f"{API}/team-invites/{link['token']}/accept", headers=auth(u)).status_code == 200
    assert client.post(f"{API}/team-invites/{link['token']}/accept", headers=auth(c)).json()["detail"]["code"] == "team_invite_invalid"
    again = _link(client, owner, team_id, max_uses=5)
    r = client.post(f"{API}/team-invites/{again['token']}/accept", headers=auth(a))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_member"
    assert client.get(f"{API}/team-invites/{again['token']}", headers=auth(a)).json()["already_member"] is True
    client.post(f"{API}/teams/{team_id}/invite-links/{again['id']}/revoke", headers=auth(owner))
    assert client.post(f"{API}/team-invites/{again['token']}/accept", headers=auth(c)).json()["detail"]["code"] == "team_invite_invalid"
    exp = _link(client, owner, team_id)
    with SessionLocal() as db:
        db.get(TeamInvite, exp["id"]).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.post(f"{API}/team-invites/{exp['token']}/accept", headers=auth(c)).json()["detail"]["code"] == "team_invite_invalid"
    states = {x["id"]: x["state"] for x in client.get(f"{API}/teams/{team_id}/invite-links", headers=auth(owner)).json()}
    assert states[again["id"]] == "revoked" and states[exp["id"]] == "expired"


def test_only_owner_manages_links(client):
    owner = make_user(client, "13800260020", "老板")
    team_id = make_team(client, owner)
    staff = make_user(client, "13800260021", "员工")
    link = _link(client, owner, team_id, max_uses=3)
    client.post(f"{API}/team-invites/{link['token']}/accept", headers=auth(staff))
    for method, path in (("post", f"/teams/{team_id}/invite-links"), ("get", f"/teams/{team_id}/invite-links"),
                         ("post", f"/teams/{team_id}/invite-links/{link['id']}/revoke")):
        r = getattr(client, method)(f"{API}{path}", headers=auth(staff), **({"json": {}} if method == "post" else {}))
        assert r.status_code == 403, (path, r.text)
    other_owner = make_user(client, "13800260022", "别家老板")
    make_team(client, other_owner, "别家")
    r = client.post(f"{API}/teams/{team_id}/invite-links/{link['id']}/revoke", headers=auth(other_owner))
    assert r.status_code == 403, "别的团队的所有者作废不了这条"


def test_limits_on_active_links(client, monkeypatch):
    from app.modules.team import invites

    monkeypatch.setattr(invites, "MAX_ACTIVE_LINKS", 2)
    owner = make_user(client, "13800260030", "老板")
    team_id = make_team(client, owner)
    _link(client, owner, team_id)
    _link(client, owner, team_id)
    r = client.post(f"{API}/teams/{team_id}/invite-links", json={}, headers=auth(owner))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "team_invite_limit"
    assert client.post(f"{API}/teams/{team_id}/invite-links", json={"days": 31}, headers=auth(owner)).status_code == 422


def test_shape(client):
    from tests.test_client_shape_alignment import _assert_shape

    owner = make_user(client, "13800260040", "老板")
    team_id = make_team(client, owner)
    link = _link(client, owner, team_id)
    _assert_shape(link, "TeamInviteCreated")
    rows = client.get(f"{API}/teams/{team_id}/invite-links", headers=auth(owner)).json()
    first = rows[0]
    _assert_shape(first, "TeamInviteLink")
    guest = register(client, "13800260041", "客人")
    preview = client.get(f"{API}/team-invites/{link['token']}", headers=auth(guest)).json()
    _assert_shape(preview, "TeamInvitePreview")
