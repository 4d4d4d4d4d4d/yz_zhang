"""TEAM-054 成员离开团队时的交接（170 号 spec，V197）。

以前移出成员只是把他标成不在职：他发起的、还在审批里的支出申请照样挂着（批下来他能执行，钱就进了一个
已经离开的人的钱包）；他用团队的钱发的任务还在跑，团队里没人知道还有哪些没收尾。
现在移出时：没执行的申请当场关掉；在途任务列成清单交给接手人；离开的人收到「哪些仍要你收尾」。
合约不转：签约的是他本人，换签约主体要双方重新签。
"""
from app.core.db import SessionLocal
from app.modules.task.models import Task
from app.modules.team.models import SpendRequest
from tests.conftest import auth
from tests.test_team_accounts import add_member, fund_team, make_team, make_user
from tests.test_ticket_assign_reply import _titles


def _spend(team_id, user_id, status, task_id=None, amount=5000):
    with SessionLocal() as db:
        r = SpendRequest(team_id=team_id, requester_id=user_id, amount_cents=amount, purpose="活动物料", status=status, task_id=task_id)
        db.add(r)
        db.commit()
        return r.id


def _task(creator_id, status, title="展会搭建"):
    with SessionLocal() as db:
        t = Task(creator_id=creator_id, title=title, description="", category="跑腿", budget_cents=5000, status=status,
                 ip_assignment="assign")
        db.add(t)
        db.commit()
        return t.id


def test_removal_closes_open_requests_lists_in_flight_tasks_and_tells_both_sides(client):
    owner = make_user(client, "13300540001", "老板")
    staff = make_user(client, "13300540002", "员工")
    lead = make_user(client, "13300540003", "主管")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    add_member(client, team_id, owner, staff, limit=10000)
    add_member(client, team_id, owner, lead, role="admin", limit=10000)
    pending = _spend(team_id, staff["id"], "pending")
    approved = _spend(team_id, staff["id"], "approved")
    busy = _task(staff["id"], "in_progress", "展会搭建")
    done = _task(staff["id"], "completed", "上个月的活")
    _spend(team_id, staff["id"], "executed", busy)
    _spend(team_id, staff["id"], "executed", done)
    other_pending = _spend(team_id, lead["id"], "pending")
    r = client.delete(f"/api/v1/teams/{team_id}/members/{staff['id']}?handover_to={lead['id']}", headers=auth(owner))
    assert r.status_code == 200, r.text
    out = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(out, "TeamMemberRemoved")
    assert out["removed"] == staff["id"] and out["handover_to"] == lead["id"]
    assert sorted(out["closed_requests"]) == sorted([pending, approved])
    assert [x["task_id"] for x in out["in_flight_tasks"]] == [busy], "做完的不用交接"
    assert out["in_flight_tasks"][0]["title"] == "展会搭建" and out["in_flight_tasks"][0]["status"] == "in_progress"
    with SessionLocal() as db:
        assert db.get(SpendRequest, pending).status == "expired" and "已移出团队" in db.get(SpendRequest, pending).decision_reason
        assert db.get(SpendRequest, other_pending).status == "pending", "别人的申请不动"
        assert db.get(Task, busy).creator_id == staff["id"], "合约不转：签约主体不能由团队一方悄悄换掉"
    assert any("1 个在途任务交给你跟进" in t for t in _titles(client, lead))
    assert any("你已离开团队" in t for t in _titles(client, staff))
    # 关掉的申请他不能再执行
    ex = client.post(f"/api/v1/teams/{team_id}/spends/{approved}/execute", headers=auth(staff))
    assert ex.status_code in (403, 409)


def test_default_taker_is_the_owner_and_handover_must_be_an_active_member(client):
    owner = make_user(client, "13300540011", "老板")
    staff = make_user(client, "13300540012", "员工")
    outsider = make_user(client, "13300540013", "外人")
    team_id = make_team(client, owner)
    add_member(client, team_id, owner, staff)
    bad = client.delete(f"/api/v1/teams/{team_id}/members/{staff['id']}?handover_to={outsider['id']}", headers=auth(owner))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "handover_not_member"
    self_ = client.delete(f"/api/v1/teams/{team_id}/members/{staff['id']}?handover_to={staff['id']}", headers=auth(owner))
    assert self_.status_code == 400 and self_.json()["detail"]["code"] == "handover_to_self"
    ok = client.delete(f"/api/v1/teams/{team_id}/members/{staff['id']}", headers=auth(owner)).json()
    assert ok["handover_to"] == owner["id"] and ok["in_flight_tasks"] == [] and ok["closed_requests"] == []
    assert any("你已离开团队" in t for t in _titles(client, staff))
