"""TEAM-056 团队预算池按每月几号重置（370 号 spec，V397）。

原来池子只能按自然月重置：财务按 25 号结账的企业，池子的「本月已用」和账期对不上。
现在 owner 可以把账期设成每月 1~28 号；1 号（默认）与原来一字不变。
"""
from datetime import datetime, timedelta

import pytest

from app.core.db import SessionLocal
from app.modules.team import service
from app.modules.team.models import SpendRequest, Team
from tests.conftest import auth
from tests.test_client_shape_alignment import _assert_shape
from tests.test_team_budget import add_member, make_team, spend


def _team(day):
    return Team(user_id=0, name="t", owner_id=0, budget_cycle_day=day)


@pytest.mark.parametrize("now,day,start,reset", [
    (datetime(2026, 11, 20, 9), 15, datetime(2026, 11, 15), datetime(2026, 12, 15)),
    (datetime(2026, 11, 10, 9), 15, datetime(2026, 10, 15), datetime(2026, 11, 15)),
    (datetime(2026, 11, 15, 0), 15, datetime(2026, 11, 15), datetime(2026, 12, 15)),   # 当天 00:00 就是新一期
    (datetime(2026, 1, 3, 9), 25, datetime(2025, 12, 25), datetime(2026, 1, 25)),       # 跨年
    (datetime(2026, 3, 1, 9), 28, datetime(2026, 2, 28), datetime(2026, 3, 28)),        # 2 月只有 28 天
    (datetime(2026, 11, 20, 9), 1, datetime(2026, 11, 1), datetime(2026, 12, 1)),       # 1 号 = 原来的自然月
    (datetime(2026, 12, 20, 9), 1, datetime(2026, 12, 1), datetime(2027, 1, 1)),
])
def test_cycle_start_and_reset(now, day, start, reset):
    t = _team(day)
    assert service.cycle_start(t, now) == start
    assert service.cycle_resets_at(t, now) == reset
    if day == 1:
        assert service.cycle_start(t, now) == service.month_start(now), "1 号与原来的自然月一字不变"


def test_owner_sets_cycle_day_and_spending_counts_from_the_cycle_start(client):
    # 账期日取「今天 +1」：本期起点落在上个月，才分得出「按账期算」和「按自然月算」（月底 28 号以后分不出，只验其余）
    from app.modules.account.models import utcnow

    today = utcnow().day
    day = min(today + 1, 28)
    owner, team_id = make_team(client, "13800063901")
    member = add_member(client, owner, team_id, "13800063902", limit=100000)
    detail = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert detail["budget_cycle_day"] == 1, "默认按自然月"
    _assert_shape(detail, "TeamDetail")
    # 只有 owner 能改；越界 422；不传账期只改金额（老客户端照旧）
    assert client.post(f"/api/v1/teams/{team_id}/budget", json={"monthly_budget_cents": 50000, "budget_cycle_day": 15},
                       headers=auth(member)).status_code == 403
    for bad in (0, 29, 31):
        assert client.post(f"/api/v1/teams/{team_id}/budget", json={"monthly_budget_cents": 50000, "budget_cycle_day": bad},
                           headers=auth(owner)).status_code == 422
    r = client.post(f"/api/v1/teams/{team_id}/budget", json={"monthly_budget_cents": 50000, "budget_cycle_day": day},
                    headers=auth(owner))
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_shape(body, "TeamBudgetResult")
    assert body["budget_cycle_day"] == day and body["budget_cycle_resets_at"]
    r = client.post(f"/api/v1/teams/{team_id}/budget", json={"monthly_budget_cents": 60000}, headers=auth(owner))
    assert r.json()["budget_cycle_day"] == day and r.json()["monthly_budget_cents"] == 60000
    # 花一笔，然后把它挪到这一期起点之前：不再算进本期，池子腾出来
    assert spend(client, member, team_id, 40000).json()["status"] == "executed"
    detail = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert detail["month_spent_cents"] == 40000 and detail["my_month_spent_cents"] == 0
    over = spend(client, member, team_id, 30000).json()
    assert over["status"] != "executed", ("池子还剩 200 元，300 元超了", over)
    with SessionLocal() as db:   # 被池子挡下的那笔不留着，免得干扰后面「本期已用」的数
        db.query(SpendRequest).filter(SpendRequest.team_id == team_id, SpendRequest.status != "executed").delete()
        db.commit()
    with SessionLocal() as db:
        team = db.get(Team, team_id)
        start = service.cycle_start(team)
        row = db.query(SpendRequest).filter(SpendRequest.team_id == team_id, SpendRequest.status == "executed").one()
        if start < service.month_start():
            # 在本期里、但在本自然月之前：按账期仍算本期已用
            row.created_at = start + timedelta(hours=1)
            db.commit()
            got = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
            assert got["month_spent_cents"] == 40000, "按账期算：上个月 %d 号以后花的仍是本期" % day
            mine = client.get(f"/api/v1/teams/{team_id}", headers=auth(member)).json()
            assert mine["my_month_spent_cents"] == 40000, "成员自己的额度也按账期算"
        row.created_at = start - timedelta(minutes=1)
        db.commit()
    detail = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert detail["month_spent_cents"] == 0
    assert detail["budget_cycle_starts_at"] < detail["budget_cycle_resets_at"]
    assert spend(client, member, team_id, 30000).json()["status"] == "executed"


def test_pool_warning_is_once_per_cycle_not_per_calendar_month(client):
    from app.modules.account.models import utcnow

    owner, team_id = make_team(client, "13800063903")
    day = min(utcnow().day + 1, 28)   # 本期起点落在上个月：「一期一次」与「一个自然月一次」才分得开
    client.post(f"/api/v1/teams/{team_id}/budget", json={"monthly_budget_cents": 10000, "budget_cycle_day": day},
                headers=auth(owner))
    with SessionLocal() as db:
        team = db.get(Team, team_id)
        db.add(SpendRequest(team_id=team_id, requester_id=owner["id"], amount_cents=9500, purpose="x", status="executed"))
        db.flush()
        assert service.warn_pool(db, team) is True
        assert team.pool_warned_month == service.cycle_start(team).strftime("%Y-%m")
        assert service.warn_pool(db, team) is False, "同一期只提醒一次"
        db.rollback()
