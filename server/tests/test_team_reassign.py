"""TEAM-073 所有者手动改派某笔申请（243 号 spec，V270）。

236 号让审批可以轮流指派一人，但轮到的人请假了、或这笔明显该财务主管看时，所有者没办法换人：
只能等第一轮催办过去、再叫全部。现在所有者可以把一笔待批申请改派给指定的审批人：通知新旧两位，
之后第一轮催办叫新的那位；任何审批人照样能批。
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


def test_owner_reassigns_and_both_sides_are_told_and_reminder_follows(client):
    owner, admin, staff, team_id = _team_with_staff(client, ("13300643001", "13300643002", "13300643003"))
    admin2 = make_user(client, "13300643004", "财务主管")
    add_member(client, team_id, owner, admin2, role="admin", limit=50000)
    client.patch(f"{API}/teams/{team_id}/approval-mode", json={"mode": "rotate"}, headers=auth(owner))
    req = _request(client, team_id, staff)
    with SessionLocal() as db:
        first = db.get(SpendRequest, req["id"]).assignee_id
    assert first == min(owner["id"], admin["id"], admin2["id"])
    r = client.post(f"{API}/teams/{team_id}/spends/{req['id']}/assign", json={"assignee_id": admin2["id"]}, headers=auth(owner))
    assert r.status_code == 200, r.text
    assert r.json() == {"id": req["id"], "assignee_id": admin2["id"], "assignee_nickname": "财务主管", "previous_assignee_id": first}
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "TeamSpendReassigned")
    assert len(notices(admin2["id"], "支出待审批（改派给你）")) == 1
    if first != owner["id"]:
        assert "改派给 财务主管" in notices(first, "支出申请已改派")[0].body
    assert notices(owner["id"], "支出申请已改派") == [], "自己改派不用通知自己"
    rows = {x["id"]: x for x in client.get(f"{API}/teams/{team_id}/spends", headers=auth(owner)).json()}
    assert rows[req["id"]]["assignee_id"] == admin2["id"]
    again = client.post(f"{API}/teams/{team_id}/spends/{req['id']}/assign", json={"assignee_id": admin2["id"]}, headers=auth(owner))
    assert again.status_code == 200 and len(notices(admin2["id"], "支出待审批（改派给你）")) == 1, "改派给同一个人不重复通知"
    with SessionLocal() as db:
        db.get(SpendRequest, req["id"]).created_at = utcnow() - timedelta(hours=30)
        db.commit()
    with SessionLocal() as db:
        service.remind_pending_spends(db)
        db.commit()
    assert len(notices(admin2["id"], "支出待审批催办")) == 1 and notices(admin["id"], "支出待审批催办") == [], "第一轮催办叫改派后的人"
    # 任何审批人照样能批
    assert client.post(f"{API}/teams/{team_id}/spends/{req['id']}/decide", json={"approve": True}, headers=auth(admin)).status_code == 200
    late = client.post(f"{API}/teams/{team_id}/spends/{req['id']}/assign", json={"assignee_id": admin["id"]}, headers=auth(owner))
    assert late.status_code == 409 and late.json()["detail"]["code"] == "already_decided"


def test_only_owner_and_only_to_an_approver(client):
    owner, admin, staff, team_id = _team_with_staff(client, ("13300643011", "13300643012", "13300643013"))
    req = _request(client, team_id, staff)
    url = f"{API}/teams/{team_id}/spends/{req['id']}/assign"
    assert client.post(url, json={"assignee_id": owner["id"]}, headers=auth(admin)).status_code == 403, "管理员不能改派"
    bad = client.post(url, json={"assignee_id": staff["id"]}, headers=auth(owner))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "team_assignee_not_approver", "发起人 / 普通成员不行"
    outsider = make_user(client, "13300643014", "外人")
    assert client.post(url, json={"assignee_id": outsider["id"]}, headers=auth(owner)).json()["detail"]["code"] == "team_assignee_not_approver"
    ok = client.post(url, json={"assignee_id": admin["id"]}, headers=auth(owner))
    assert ok.status_code == 200 and ok.json()["previous_assignee_id"] is None, "默认模式没人被指派，也能指定一位"
    mine = _request(client, team_id, admin)                     # 管理员自己发起（超过他 500 元的额度）
    own = client.post(f"{API}/teams/{team_id}/spends/{mine['id']}/assign", json={"assignee_id": admin["id"]}, headers=auth(owner))
    assert own.json()["detail"]["code"] == "team_assignee_not_approver", "不能改派给发起人自己（自己批自己不算审批）"
    other_owner = make_user(client, "13300643015", "别的团队老板")
    assert client.post(f"{API}/teams/{team_id}/spends/{req['id']}/assign", json={"assignee_id": admin["id"]},
                       headers=auth(other_owner)).status_code == 403
    assert client.post(f"{API}/teams/{team_id}/spends/999999/assign", json={"assignee_id": admin["id"]},
                       headers=auth(owner)).status_code == 404
