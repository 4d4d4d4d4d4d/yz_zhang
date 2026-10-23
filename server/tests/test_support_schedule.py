"""ESCA-068 按排班表自动暂停 / 恢复接单（260 号 spec，V287）。

240 / 256 号的暂停要人记得点（或主管替人点）；天天如此的上下班还得每天点一次。现在客服可以设排班
（北京时间，每周几的几点到几点在岗）：排班以外自动不在岗——自动分配跳过、超时提醒先叫别人；到点自动在岗。
"""
from datetime import datetime

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.support import escalation
from app.modules.support.models import SupportAgentScope, Ticket
from app.modules.workbench.service import local
from tests.conftest import auth
from tests.test_support_scopes import API, _ticket
from tests.test_ticket_assign_reply import _admin

SCHED = f"{API}/admin/support/my-schedule"


def test_off_duty_follows_the_schedule_in_beijing_time():
    s = SupportAgentScope(user_id=1, categories=["funds"], schedule=[{"weekday": 3, "start": "09:00", "end": "18:00"}])
    thu_0900 = datetime(2026, 10, 22, 1, 0)                       # UTC 01:00 = 北京时间周四 09:00
    assert escalation.off_duty(s, thu_0900) is False
    assert escalation.off_duty(s, datetime(2026, 10, 22, 0, 59)) is True, "08:59 还没上班"
    assert escalation.off_duty(s, datetime(2026, 10, 22, 10, 0)) is True, "18:00 下班（不含）"
    assert escalation.off_duty(s, datetime(2026, 10, 23, 1, 0)) is True, "周五没排班"
    assert escalation.off_duty(SupportAgentScope(user_id=2, categories=[], schedule=[]), thu_0900) is False, "不设排班 = 一直在岗"


def test_schedule_drives_auto_assign_and_can_be_cleared(client):
    now = local(utcnow())
    today, other = now.weekday(), (now.weekday() + 3) % 7
    a = _admin(client, "13800349001", ["support"])
    b = _admin(client, "13800349002", ["support"])
    boss = _admin(client, "13800349003", ["super"])
    for x in (a, b):
        client.put(f"{API}/admin/support/my-categories", json={"categories": ["funds"], "auto_assign": True}, headers=auth(x))
    r = client.put(SCHED, json={"windows": [{"weekday": other, "start": "09:00", "end": "18:00"}]}, headers=auth(a))
    assert r.status_code == 200 and r.json()["on_duty"] is False
    client.put(SCHED, json={"windows": [{"weekday": today, "start": "00:00", "end": "24:00"}]}, headers=auth(b))
    me = client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()
    assert me["on_duty"] is False and me["schedule"] == [{"weekday": other, "start": "09:00", "end": "18:00"}]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(me, "SupportScope")
    t1 = _ticket(client, "13800349004", "funds")
    with SessionLocal() as db:
        t = db.get(Ticket, t1)
        assert t.assignee_id == b["id"], "a 不在排班里：分给在岗的 b"
        t.assignee_id = None                          # 不提交：只看「没人接手时提醒叫谁」
        assert escalation.level1_recipients(db, t) == [b["id"]], "超时提醒先叫在排班里的人"
    rows = {x["user_id"]: x for x in client.get(f"{API}/admin/support/agents", headers=auth(boss)).json()}
    assert (rows[a["id"]]["on_duty"], rows[b["id"]]["on_duty"]) == (False, True)
    assert rows[a["id"]]["paused_until"] is None, "排班以外不是「暂停」，另用 on_duty 说"
    assert client.put(SCHED, json={"windows": []}, headers=auth(a)).json() == {"schedule": [], "on_duty": True}
    assert "schedule" not in client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json(), "取消排班后响应与以前一样"
    t2 = _ticket(client, "13800349005", "funds")
    with SessionLocal() as db:
        assert db.get(Ticket, t2).assignee_id == a["id"], "取消排班：照常按负载分（a 手上 0 个）"


def test_schedule_validation_and_roles(client):
    a = _admin(client, "13800349011", ["support"])
    bad = client.put(SCHED, json={"windows": [{"weekday": 1, "start": "18:00", "end": "09:00"}]}, headers=auth(a))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "support_schedule_bad_window"
    assert client.put(SCHED, json={"windows": [{"weekday": 7, "start": "09:00", "end": "18:00"}]}, headers=auth(a)).status_code == 422
    assert client.put(SCHED, json={"windows": [{"weekday": 1, "start": "9:00", "end": "18:00"}]}, headers=auth(a)).status_code == 422
    fin = _admin(client, "13800349012", ["finance"])
    assert client.put(SCHED, json={"windows": []}, headers=auth(fin)).status_code == 403


def test_esca069_several_segments_a_day_and_no_overlap(client):
    """ESCA-069（263 号 spec）同一天早晚两班；重叠的两段拒收并说清是哪两段。"""
    s = SupportAgentScope(user_id=1, categories=[], schedule=[{"weekday": 3, "start": "08:00", "end": "12:00"},
                                                              {"weekday": 3, "start": "18:00", "end": "22:00"}])
    assert escalation.off_duty(s, datetime(2026, 10, 22, 2, 0)) is False, "周四 10:00 在早班"
    assert escalation.off_duty(s, datetime(2026, 10, 22, 7, 0)) is True, "周四 15:00 两班之间"
    assert escalation.off_duty(s, datetime(2026, 10, 22, 11, 0)) is False, "周四 19:00 在晚班"
    a = _admin(client, "13800349021", ["support"])
    ok = client.put(SCHED, json={"windows": [{"weekday": 3, "start": "18:00", "end": "22:00"},
                                             {"weekday": 3, "start": "08:00", "end": "12:00"},
                                             {"weekday": 4, "start": "12:00", "end": "18:00"},
                                             {"weekday": 4, "start": "08:00", "end": "12:00"}]}, headers=auth(a))
    assert ok.status_code == 200, "首尾相接不算重叠"
    assert [w["start"] for w in ok.json()["schedule"]] == ["08:00", "18:00", "08:00", "12:00"], "按周几、开始时间排好存"
    bad = client.put(SCHED, json={"windows": [{"weekday": 2, "start": "09:00", "end": "13:00"},
                                              {"weekday": 2, "start": "12:00", "end": "18:00"}]}, headers=auth(a))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "support_schedule_overlap"
    assert "09:00–13:00" in bad.json()["detail"]["message"] and "12:00–18:00" in bad.json()["detail"]["message"]
    assert client.put(SCHED, json={"windows": [{"weekday": 2, "start": "09:00", "end": "13:00"},
                                               {"weekday": 3, "start": "12:00", "end": "18:00"}]}, headers=auth(a)).status_code == 200, "不同天不算重叠"
