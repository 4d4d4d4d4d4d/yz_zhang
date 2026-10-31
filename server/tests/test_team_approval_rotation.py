"""TEAM-064 团队审批通知的轮流指派（236 号 spec，V263）。

以前每笔超额申请都同时通知所有所有者与管理员：谁都收到 = 谁都不负责，常见的结果是都以为别人会批。
现在所有者可以改成「轮流指派一人」：轮到的人收到通知、第一轮催办也只叫他；再没批就叫全部，
不让申请卡在一个人身上。任何审批人照样能批。默认不变（发给所有人）。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.team import service
from app.modules.team.models import SpendRequest
from tests.conftest import auth
from tests.test_team_accounts import add_member, make_user
from tests.test_team_approval_notice import _request, _team_with_staff, notices

API = "/api/v1"


def test_default_is_unchanged_and_only_owner_switches_mode(client):
    owner, admin, staff, team_id = _team_with_staff(client, ("13300640001", "13300640002", "13300640003"))
    assert client.get(f"{API}/teams/{team_id}", headers=auth(owner)).json()["approval_mode"] == "all"
    _request(client, team_id, staff)
    assert len(notices(owner["id"], "支出待审批")) == 1 and len(notices(admin["id"], "支出待审批")) == 1
    assert client.patch(f"{API}/teams/{team_id}/approval-mode", json={"mode": "rotate"}, headers=auth(admin)).status_code == 403
    assert client.patch(f"{API}/teams/{team_id}/approval-mode", json={"mode": "random"}, headers=auth(owner)).status_code == 422
    r = client.patch(f"{API}/teams/{team_id}/approval-mode", json={"mode": "rotate"}, headers=auth(owner))
    assert r.status_code == 200 and r.json() == {"team_id": team_id, "approval_mode": "rotate"}


def test_rotation_takes_turns_and_reminders_widen_after_first_round(client):
    owner, admin, staff, team_id = _team_with_staff(client, ("13300640011", "13300640012", "13300640013"))
    client.patch(f"{API}/teams/{team_id}/approval-mode", json={"mode": "rotate"}, headers=auth(owner))
    first, second, third = (_request(client, team_id, staff) for _ in range(3))
    order = sorted([owner["id"], admin["id"]])
    with SessionLocal() as db:
        got = [db.get(SpendRequest, x["id"]).assignee_id for x in (first, second, third)]
    assert got == [order[0], order[1], order[0]], "按编号轮流，到底了从头开始"
    assert len(notices(order[0], "支出待审批")) == 2 and len(notices(order[1], "支出待审批")) == 1
    assert "轮到你审批" in notices(order[0], "支出待审批")[0].body
    rows = {x["id"]: x for x in client.get(f"{API}/teams/{team_id}/spends", headers=auth(owner)).json()}
    assert rows[first["id"]]["assignee_id"] == order[0]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(rows[first["id"]], "SpendRequestView")
    # 别的审批人照样能批
    other = order[1]
    who = owner if other == owner["id"] else admin
    assert client.post(f"{API}/teams/{team_id}/spends/{first['id']}/decide", json={"approve": True}, headers=auth(who)).status_code == 200
    # 催办：第一轮只叫轮到的人，第二轮叫全部并写明轮到谁还没处理
    with SessionLocal() as db:
        for x in (second, third):
            db.get(SpendRequest, x["id"]).created_at = utcnow() - timedelta(hours=30)
        db.commit()
    with SessionLocal() as db:
        service.remind_pending_spends(db)
        db.commit()
    assert len(notices(order[1], "支出待审批催办")) == 1 and len(notices(order[0], "支出待审批催办")) == 1, "各催各自轮到的那笔"
    with SessionLocal() as db:
        for x in (second, third):
            db.get(SpendRequest, x["id"]).reminded_at = utcnow() - timedelta(hours=30)
        db.commit()
    with SessionLocal() as db:
        service.remind_pending_spends(db)
        db.commit()
    later = notices(order[0], "支出待审批催办")
    assert len(later) == 3, "第二轮两笔都叫到了每个审批人"
    assert any("还没处理，请其他管理员帮忙看一下" in n.body for n in later)


def test_rotation_skips_the_requester_and_left_members(client):
    owner, admin, staff, team_id = _team_with_staff(client, ("13300640021", "13300640022", "13300640023"))
    lead = make_user(client, "13300640024", "副主管")
    add_member(client, team_id, owner, lead, role="admin", limit=0)
    client.patch(f"{API}/teams/{team_id}/approval-mode", json={"mode": "rotate"}, headers=auth(owner))
    # 管理员自己发起的超额申请：轮不到他自己
    r = client.post(f"{API}/teams/{team_id}/spends", json={"amount_cents": 900000, "purpose": "大额"}, headers=auth(admin)).json()
    with SessionLocal() as db:
        assert db.get(SpendRequest, r["id"]).assignee_id in (owner["id"], lead["id"])
    client.delete(f"{API}/teams/{team_id}/members/{lead['id']}", headers=auth(owner))
    for _ in range(3):
        x = _request(client, team_id, staff)
        with SessionLocal() as db:
            assert db.get(SpendRequest, x["id"]).assignee_id in (owner["id"], admin["id"]), "离开的人不再轮到"


def test_reminder_goes_to_everyone_when_the_assignee_has_left(client):
    owner, admin, staff, team_id = _team_with_staff(client, ("13300640031", "13300640032", "13300640033"))
    client.patch(f"{API}/teams/{team_id}/approval-mode", json={"mode": "rotate"}, headers=auth(owner))
    req = _request(client, team_id, staff)
    with SessionLocal() as db:
        r = db.get(SpendRequest, req["id"])
        r.assignee_id = admin["id"]
        r.created_at = utcnow() - timedelta(hours=30)
        db.commit()
    # 主管离开团队后，他自己的申请被关掉，而这笔员工的申请还挂在他名下
    with SessionLocal() as db:
        from app.modules.team.models import TeamMember

        db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == admin["id"]).update({"active": False})
        db.commit()
    with SessionLocal() as db:
        service.remind_pending_spends(db)
        db.commit()
    assert len(notices(owner["id"], "支出待审批催办")) == 1, "轮到的人不在了：第一轮就叫还在的审批人"
    assert notices(admin["id"], "支出待审批催办") == []
