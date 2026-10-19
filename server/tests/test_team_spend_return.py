"""TEAM-070 已划给成员没用完的钱退回团队（226 号 spec，V253）。

团队支出执行时钱划进成员个人钱包，之后与他自己的钱混在一起；没用完的以前没有任何路回到团队，
人离开团队时更是没人提。现在发起人可以按实际剩下的退回（最多退到拨款额，资金操作带幂等键），
所有者在支出列表里看得到退了多少；离开团队时通知里写明还有多少没退。
"""
from app.core.db import SessionLocal
from app.modules.team.models import SpendRequest
from app.modules.wallet.models import LedgerEntry
from tests.conftest import auth
from tests.test_team_accounts import add_member, fund_team, make_team, make_user
from tests.test_ticket_assign_reply import _titles

API = "/api/v1"


def _setup(client, base):
    owner = make_user(client, f"133007{base}1", "老板")
    staff = make_user(client, f"133007{base}2", "员工")
    team_id = make_team(client, owner)
    fund_team(team_id, 100000)
    add_member(client, team_id, owner, staff, limit=20000)
    r = client.post(f"{API}/teams/{team_id}/spends", json={"amount_cents": 8000, "purpose": "活动物料"}, headers=auth(staff))
    assert r.status_code == 201 and r.json()["needed_approval"] is False, r.text
    return owner, staff, team_id, r.json()["id"]


def _ret(client, user, team_id, rid, cents, key):
    return client.post(f"{API}/teams/{team_id}/spends/{rid}/return", json={"amount_cents": cents},
                       headers={**auth(user), "Idempotency-Key": key})


def test_requester_returns_unused_money_up_to_the_spend_and_owner_sees_it(client):
    owner, staff, team_id, rid = _setup(client, "01")
    mine = client.get(f"{API}/teams/returnable-spends", headers=auth(staff)).json()
    assert [(x["id"], x["team_name"], x["returnable_cents"]) for x in mine] == [(rid, "某某科技", 8000)]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(mine[0], "ReturnableTeamSpend")
    r = _ret(client, staff, team_id, rid, 3000, "ret-1")
    assert r.status_code == 200, r.text
    assert (r.json()["returned_cents"], r.json()["returnable_cents"]) == (3000, 5000)
    _assert_shape(r.json(), "TeamSpendReturned")
    again = _ret(client, staff, team_id, rid, 3000, "ret-1")
    assert again.json() == r.json(), "同一个键重试回放，不会退两次"
    assert _ret(client, staff, team_id, rid, 2000, "ret-1").json()["detail"]["code"] == "idempotency_key_conflict", "同一个键换了金额"
    assert client.get(f"{API}/teams/{team_id}", headers=auth(owner)).json()["balance_cents"] == 100000 - 8000 + 3000
    with SessionLocal() as db:
        kinds = sorted(e.kind for e in db.query(LedgerEntry).filter(LedgerEntry.kind.like("team_return%")))
    assert kinds == ["team_return_in", "team_return_out"]
    row = next(x for x in client.get(f"{API}/teams/{team_id}/spends", headers=auth(owner)).json() if x["id"] == rid)
    assert (row["returned_cents"], row["returnable_cents"]) == (3000, 5000)
    _assert_shape(row, "SpendRequestView")
    assert any("收到退回 ¥30.00" in t for t in _titles(client, owner))
    r = _ret(client, staff, team_id, rid, 5001, "ret-2")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "return_exceeds_spend" and "最多还能退 ¥50.00" in r.json()["detail"]["message"]
    assert _ret(client, staff, team_id, rid, 5000, "ret-3").json()["returnable_cents"] == 0
    assert client.get(f"{API}/teams/returnable-spends", headers=auth(staff)).json() == [], "退完了就不再列出"


def test_only_requester_executed_and_balance_and_key_required(client):
    owner, staff, team_id, rid = _setup(client, "02")
    assert _ret(client, owner, team_id, rid, 100, "k1").status_code == 403
    r = client.post(f"{API}/teams/{team_id}/spends/{rid}/return", json={"amount_cents": 100}, headers=auth(staff))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "idempotency_required"
    with SessionLocal() as db:
        pending = SpendRequest(team_id=team_id, requester_id=staff["id"], amount_cents=5000, purpose="x", status="approved")
        db.add(pending)
        db.commit()
        pid = pending.id
    assert _ret(client, staff, team_id, pid, 100, "k2").json()["detail"]["code"] == "spend_not_executed"
    row = next(x for x in client.get(f"{API}/teams/{team_id}/spends", headers=auth(owner)).json() if x["id"] == pid)
    assert row["returnable_cents"] == 0, "没执行的钱没划出去，没有可退的"
    assert _ret(client, staff, 999999, rid, 100, "k3").status_code == 404
    # 钱已经花出去（这里直接提走）：说清余额不够、为什么
    from app.modules.wallet import service as wallet

    with SessionLocal() as db:
        acct = wallet.get_or_create(db, staff["id"])
        acct.available_cents = 1000
        db.commit()
    r = _ret(client, staff, team_id, rid, 2000, "k4")
    assert r.json()["detail"]["code"] == "return_insufficient_balance" and "¥10.00" in r.json()["detail"]["message"]


def test_removed_member_is_told_how_much_is_unreturned_and_can_still_return(client):
    owner, staff, team_id, rid = _setup(client, "03")
    _ret(client, staff, team_id, rid, 2000, "ret-a")
    out = client.delete(f"{API}/teams/{team_id}/members/{staff['id']}", headers=auth(owner)).json()
    assert out["unreturned_cents"] == 6000
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(out, "TeamMemberRemoved")
    with SessionLocal() as db:
        from app.modules.notification.models import Notification

        body = [n.body for n in db.query(Notification).filter(Notification.user_id == staff["id"]) if "你已离开团队" in n.title][-1]
    assert "还没退回的共 ¥60.00" in body and "钱包页" in body
    assert client.get(f"{API}/teams/{team_id}/spends", headers=auth(staff)).status_code in (403, 404), "离开后进不了团队页"
    assert [x["id"] for x in client.get(f"{API}/teams/returnable-spends", headers=auth(staff)).json()] == [rid]
    assert _ret(client, staff, team_id, rid, 6000, "ret-b").json()["returnable_cents"] == 0, "离开了也能退"
