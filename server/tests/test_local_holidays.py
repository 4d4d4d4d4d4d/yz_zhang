"""ESCA-073 地区性假日（305 号 spec，V332）。

V315 只能按国务院的通知导入全国的放假与调休。民族自治地方的节日（如新疆、宁夏的古尔邦节）只在当地放假：
全国日历里录了，别的地区的客服也被当成不在岗；不录，当地的客服又被当成在岗、工单派过去没人接。
现在主管给客服设「所在地区」，地区性假日只对这个地区的客服起作用。公司自定的全员假期照旧录在全国日历里。
"""
from datetime import date, datetime

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.support import escalation
from app.modules.support.models import SupportAgentScope
from app.modules.workbench.service import local
from tests.conftest import auth
from tests.test_support_scopes import API
from tests.test_ticket_assign_reply import _admin

LOC = f"{API}/admin/support/local-holidays"
SCHED = f"{API}/admin/support/my-schedule"


def test_a_local_holiday_only_takes_the_agents_of_that_region_off():
    week = [{"weekday": d, "start": "00:00", "end": "24:00"} for d in range(7)]
    xj = SupportAgentScope(user_id=1, categories=[], schedule=week, region="新疆")
    bj = SupportAgentScope(user_id=2, categories=[], schedule=week, region="北京")
    none = SupportAgentScope(user_id=3, categories=[], schedule=week)
    thu = datetime(2026, 10, 22, 2, 0)                                   # 北京时间周四 10:00
    hol = {(date(2026, 10, 22), "新疆"): ("off", None)}
    assert escalation.off_duty(xj, thu, hol) is True, "当地放假，整天不在岗"
    assert escalation.off_duty(bj, thu, hol) is False, "别的地区照常"
    assert escalation.off_duty(none, thu, hol) is False, "没设地区的照常"
    assert escalation.off_duty(xj, datetime(2026, 10, 23, 2, 0), hol) is False, "只管那一天"
    sat = datetime(2026, 10, 24, 2, 0)
    both = {date(2026, 10, 24): ("workday", 4), (date(2026, 10, 24), "新疆"): ("off", None)}
    assert escalation.off_duty(xj, sat, both) is True, "全国调休上班、当地放假：当地的人放假"
    assert escalation.off_duty(bj, sat, both) is False
    unscheduled = SupportAgentScope(user_id=4, categories=[], schedule=[], region="新疆")
    assert escalation.off_duty(unscheduled, thu, hol) is False, "没设排班的不受日历影响（与全国日历一样）"


def test_supervisor_sets_regions_and_records_local_holidays(client):
    boss = _admin(client, "13800373001", ["super"])
    a = _admin(client, "13800373002", ["support"])
    b = _admin(client, "13800373003", ["support"])
    today = local(utcnow()).date()
    for x in (a, b):
        client.put(SCHED, json={"windows": [{"weekday": today.weekday(), "start": "00:00", "end": "24:00"}]}, headers=auth(x))

    r = client.post(LOC, json={"day": today.isoformat(), "region": "新疆", "label": "古尔邦节"}, headers=auth(boss))
    assert r.status_code == 201 and r.json()["agents"] == 0, "还没给谁设新疆：0 位，主管一眼看出来"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "SupportLocalHoliday")
    assert client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()["on_duty"] is True

    s = client.put(f"{API}/admin/support/agents/{a['id']}/region", json={"region": " 新疆 "}, headers=auth(boss))
    assert s.status_code == 200 and s.json() == {"user_id": a["id"], "region": "新疆"}
    assert client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()["on_duty"] is False, "当地今天放假"
    assert client.get(f"{API}/admin/support/my-categories", headers=auth(b)).json()["on_duty"] is True, "别的客服照常"
    rows = {x["user_id"]: x for x in client.get(f"{API}/admin/support/agents", headers=auth(boss)).json()}
    assert rows[a["id"]]["region"] == "新疆" and rows[a["id"]]["on_duty"] is False
    assert "region" not in rows[b["id"]], "没设地区的不出这个字段"
    with SessionLocal() as db:
        assert a["id"] in escalation.paused_agents(db) and b["id"] not in escalation.paused_agents(db)
    listed = client.get(LOC, headers=auth(b)).json()
    assert [(h["region"], h["label"], h["agents"]) for h in listed] == [("新疆", "古尔邦节", 1)], "客服都能看"

    other = client.post(LOC, json={"day": today.isoformat(), "region": "宁夏", "label": "古尔邦节"}, headers=auth(boss))
    assert other.status_code == 201, "同一天别的地区也能录"
    dup = client.post(LOC, json={"day": today.isoformat(), "region": "新疆"}, headers=auth(boss))
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "holiday_exists" and "新疆" in dup.json()["detail"]["message"]
    blank = client.post(LOC, json={"day": today.isoformat(), "region": "  "}, headers=auth(boss))
    assert blank.status_code == 400 and blank.json()["detail"]["code"] == "holiday_region_required"
    assert client.post(LOC, json={"day": "2026-10-11", "region": "新疆"}, headers=auth(a)).status_code == 403, "只有主管能录"
    assert client.put(f"{API}/admin/support/agents/{b['id']}/region", json={"region": "新疆"},
                      headers=auth(a)).status_code == 403, "只有主管能设地区"

    assert client.delete(f"{LOC}/{r.json()['id']}", headers=auth(boss)).json()["deleted"] is True
    assert client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()["on_duty"] is True, "删掉后恢复"
    assert client.delete(f"{LOC}/999999", headers=auth(boss)).status_code == 404
    client.post(LOC, json={"day": today.isoformat(), "region": "新疆"}, headers=auth(boss))
    clear = client.put(f"{API}/admin/support/agents/{a['id']}/region", json={"region": ""}, headers=auth(boss))
    assert clear.json()["region"] is None
    assert client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()["on_duty"] is True, "不分地区后照常"
    user = client.put(f"{API}/admin/support/agents/999999/region", json={"region": "新疆"}, headers=auth(boss))
    assert user.status_code == 400 and user.json()["detail"]["code"] == "assignee_not_support"
