"""TEAM-056b 团队账期按团队负责人选的时区 0 点起算（392 号 spec，V419）。

原来账期一律按 UTC 起算：东八区的团队，1 号的额度到当地早上 8 点才重置。
现在 owner 可以选一个时区；不选（或选 UTC）与原来一字不变。平台仍不推断、不存个人时区（TZ-065）。
"""
import typing
from datetime import datetime

import pytest

from app.modules.team import service
from app.modules.team.models import Team
from app.modules.team.router import BudgetIn
from tests.conftest import auth
from tests.test_client_shape_alignment import _assert_shape
from tests.test_team_budget import add_member, make_team


def _team(day, tz=None):
    return Team(user_id=0, name="t", owner_id=0, budget_cycle_day=day, budget_tz=tz)


@pytest.mark.parametrize("now,day,tz,start,reset", [
    # 北京时间 12 月 1 日 01:00（= UTC 11-30 17:00）：已经是新的一期，起点是北京时间 12-01 00:00（= UTC 11-30 16:00）
    (datetime(2026, 11, 30, 17), 1, "Asia/Shanghai", datetime(2026, 11, 30, 16), datetime(2026, 12, 31, 16)),
    # 同一时刻不选时区：按 UTC 还在 11 月这一期
    (datetime(2026, 11, 30, 17), 1, None, datetime(2026, 11, 1), datetime(2026, 12, 1)),
    (datetime(2026, 11, 30, 17), 1, "UTC", datetime(2026, 11, 1), datetime(2026, 12, 1)),
    # 北京时间 11-15 07:00（= UTC 11-14 23:00）：15 号的账期已经开始
    (datetime(2026, 11, 14, 23), 15, "Asia/Shanghai", datetime(2026, 11, 14, 16), datetime(2026, 12, 14, 16)),
    # 纽约（冬令时 UTC-5）：当地 11-14 20:00 还没到 15 号
    (datetime(2026, 11, 15, 1), 15, "America/New_York", datetime(2026, 10, 15, 4), datetime(2026, 11, 15, 5)),
    # 跨年：北京时间 2027-01-01 00:30
    (datetime(2026, 12, 31, 16, 30), 1, "Asia/Shanghai", datetime(2026, 12, 31, 16), datetime(2027, 1, 31, 16)),
])
def test_cycle_follows_the_teams_timezone(now, day, tz, start, reset):
    t = _team(day, tz)
    assert service.cycle_start(t, now) == start
    assert service.cycle_resets_at(t, now) == reset


def test_unknown_timezone_in_the_row_falls_back_to_utc():
    """库里出现不在名单里的值（手改、老数据）：按 UTC 算，不报错。"""
    now = datetime(2026, 11, 30, 17)
    assert service.cycle_start(_team(1, "Mars/Olympus"), now) == datetime(2026, 11, 1)


def test_the_api_choices_match_the_service_list():
    """接口允许的时区和服务端认的时区是同一张表：只改一边，选了的时区会被静默当成 UTC。"""
    allowed = set(typing.get_args(typing.get_args(BudgetIn.model_fields["budget_tz"].annotation)[0]))
    assert allowed == set(service.BUDGET_TIMEZONES)


def test_owner_picks_a_timezone_and_the_team_shows_it(client):
    owner, team_id = make_team(client, "13800064101")
    member = add_member(client, owner, team_id, "13800064102", limit=100000)
    url = f"/api/v1/teams/{team_id}/budget"
    detail = client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json()
    assert detail["budget_tz"] == "UTC", "默认与原来一样"
    _assert_shape(detail, "TeamDetail")
    assert client.post(url, json={"monthly_budget_cents": 50000, "budget_tz": "Asia/Shanghai"},
                       headers=auth(member)).status_code == 403
    for bad in ("Mars/Olympus", "Asia/Kolkata", "beijing"):
        assert client.post(url, json={"monthly_budget_cents": 50000, "budget_tz": bad}, headers=auth(owner)).status_code == 422
    r = client.post(url, json={"monthly_budget_cents": 50000, "budget_tz": "Asia/Shanghai"}, headers=auth(owner))
    assert r.status_code == 200, r.text
    _assert_shape(r.json(), "TeamBudgetResult")
    assert r.json()["budget_tz"] == "Asia/Shanghai"
    # 北京时间的 0 点 = UTC 前一天 16:00
    assert r.json()["budget_cycle_starts_at"].endswith("T16:00:00+00:00") or "16:00:00" in r.json()["budget_cycle_starts_at"]
    # 不传时区只改金额：时区不变（老客户端照旧）
    r = client.post(url, json={"monthly_budget_cents": 60000}, headers=auth(owner))
    assert r.json()["budget_tz"] == "Asia/Shanghai"
    # 选回 UTC：与原来一样
    r = client.post(url, json={"monthly_budget_cents": 60000, "budget_tz": "UTC"}, headers=auth(owner))
    assert r.json()["budget_tz"] == "UTC" and "00:00:00" in r.json()["budget_cycle_starts_at"]
