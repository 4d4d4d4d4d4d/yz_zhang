"""ESCA-051 客服工单超时自动升级（150 号 spec）。

V101 起超时的工单只出现在「人审队列积压」那条汇总里——发给全体管理员，谁都收到等于谁都没被点名。
这里核对：到时限叫醒接手的客服（没人接手叫醒全体客服），到升级线叫醒主管并告诉提单人；
每一级只叫一次；认领不重置计时；结了单的不升级。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.admin.models import AdminAudit
from app.modules.support.models import Ticket
from tests.conftest import JOB_HEADERS, auth, make_admin, register

API = "/api/v1"
JOB = f"{API}/admin/jobs/escalate-tickets"


def _admin(client, phone, roles):
    a = make_admin(client, phone, f"管理员{phone[-2:]}")
    with SessionLocal() as db:
        db.get(User, a["id"]).admin_roles = roles
        db.commit()
    return a


def _ticket(client, phone, subject="提现三天没到账"):
    u = register(client, phone, "提问的人")
    tid = client.post(f"{API}/support/tickets", json={"subject": subject, "body": "急"}, headers=auth(u)).json()["id"]
    return u, tid


def _age(tid, hours):
    with SessionLocal() as db:
        db.get(Ticket, tid).created_at = utcnow() - timedelta(hours=hours)
        db.commit()


def _titles(client, user):
    rows = client.get(f"{API}/notifications?limit=100", headers=auth(user)).json()
    items = rows["items"] if isinstance(rows, dict) else rows
    return [n["title"] for n in items]


def _level(tid):
    with SessionLocal() as db:
        return db.get(Ticket, tid).escalation_level


def test_level1_wakes_all_support_staff_when_nobody_claimed(client):
    s1 = _admin(client, "13800250001", ["support"])
    s2 = _admin(client, "13800250002", ["support"])
    boss = _admin(client, "13800250003", ["super"])
    fin = _admin(client, "13800250004", ["finance"])
    _u, tid = _ticket(client, "13800250010")
    _age(tid, 23)
    assert client.post(JOB, headers=JOB_HEADERS).json()["level1"] == []   # 还没到时限
    _age(tid, 25)
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert r["level1"] == [tid] and r["level2"] == [] and _level(tid) == 1
    for a in (s1, s2):
        assert "工单超时：请尽快处理" in _titles(client, a)
    for a in (boss, fin):
        assert "工单超时：请尽快处理" not in _titles(client, a), "第 1 级只叫客服，不该把全体管理员都叫起来"
    # 每级只叫一次
    assert client.post(JOB, headers=JOB_HEADERS).json()["level1"] == []
    assert _titles(client, s1).count("工单超时：请尽快处理") == 1


def test_level1_wakes_only_the_assignee_once_claimed(client):
    s1 = _admin(client, "13800250011", ["support"])
    s2 = _admin(client, "13800250012", ["support"])
    _u, tid = _ticket(client, "13800250013")
    c = client.post(f"{API}/admin/tickets/{tid}/claim", headers=auth(s1))
    assert c.status_code == 200 and c.json()["assignee_id"] == s1["id"] and c.json()["previous_assignee_id"] is None
    _age(tid, 25)   # 认领不重置计时：仍按提单时间算
    client.post(JOB, headers=JOB_HEADERS)
    assert "工单超时：请尽快处理" in _titles(client, s1)
    assert "工单超时：请尽快处理" not in _titles(client, s2)


def test_level2_wakes_the_supervisor_and_tells_the_submitter(client):
    s1 = _admin(client, "13800250021", ["support"])
    boss = _admin(client, "13800250022", ["super"])
    u, tid = _ticket(client, "13800250023")
    _age(tid, 25)
    client.post(JOB, headers=JOB_HEADERS)
    assert "工单升级：需要主管介入" not in _titles(client, boss)
    _age(tid, 49)
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert r["level2"] == [tid] and r["level1"] == [] and _level(tid) == 2
    assert "工单升级：需要主管介入" in _titles(client, boss)
    assert "工单升级：需要主管介入" not in _titles(client, s1)
    assert "你的工单已升级给主管" in _titles(client, u)
    client.post(JOB, headers=JOB_HEADERS)
    assert _titles(client, boss).count("工单升级：需要主管介入") == 1
    assert _titles(client, u).count("你的工单已升级给主管") == 1


def test_skipping_a_level_still_wakes_both(client):
    """调度停了两天：一次跑到第 2 级，客服和主管都该知道。"""
    s1 = _admin(client, "13800250031", ["support"])
    boss = _admin(client, "13800250032", ["super"])
    _u, tid = _ticket(client, "13800250033")
    _age(tid, 60)
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert r["level1"] == [tid] and r["level2"] == [tid] and _level(tid) == 2
    assert "工单超时：请尽快处理" in _titles(client, s1)
    assert "工单升级：需要主管介入" in _titles(client, boss)


def test_resolved_tickets_are_not_escalated(client):
    s1 = _admin(client, "13800250041", ["support"])
    _u, tid = _ticket(client, "13800250042")
    assert client.post(f"{API}/admin/tickets/{tid}/resolve", json={"reply": "已到账"}, headers=auth(s1)).status_code == 200
    _age(tid, 60)
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert r["level1"] == [] and r["level2"] == [] and _level(tid) == 0


def test_queue_shows_assignee_wait_and_level_and_sorts_by_urgency(client):
    s1 = _admin(client, "13800250051", ["support"])
    _u, old = _ticket(client, "13800250052", "老的")
    _u2, mid = _ticket(client, "13800250053", "中的")
    _u3, new = _ticket(client, "13800250054", "新的")
    _age(old, 30)
    _age(mid, 50)
    client.post(JOB, headers=JOB_HEADERS)
    client.post(f"{API}/admin/tickets/{new}/claim", headers=auth(s1))
    h = auth(s1)
    rows = client.get(f"{API}/admin/tickets", headers=h).json()
    assert [r["id"] for r in rows] == [old, mid, new], "默认排序不变"
    by = {r["id"]: r for r in rows}
    assert by[old]["escalation_level"] == 1 and by[old]["overdue_hours"] == 6 and by[old]["sla_hours"] == 24
    assert by[mid]["escalation_level"] == 2 and by[mid]["escalation_label"] == "已升级给主管"
    assert by[new]["assignee_nickname"] == "管理员51" and by[new]["overdue_hours"] == 0
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(rows[0], "AdminTicketRow")
    urgent = client.get(f"{API}/admin/tickets", params={"sort": "urgent"}, headers=h).json()
    assert [r["id"] for r in urgent] == [mid, old, new]
    assert [r["id"] for r in client.get(f"{API}/admin/tickets", params={"escalated_only": True}, headers=h).json()] == [old, mid]
    assert [r["id"] for r in client.get(f"{API}/admin/tickets", params={"mine": True}, headers=h).json()] == [new]


def test_claim_is_audited_and_can_take_over(client):
    s1 = _admin(client, "13800250061", ["support"])
    s2 = _admin(client, "13800250062", ["support"])
    fin = _admin(client, "13800250063", ["finance"])
    _u, tid = _ticket(client, "13800250064")
    url = f"{API}/admin/tickets/{tid}/claim"
    assert client.post(url, headers=auth(fin)).status_code == 403
    client.post(url, headers=auth(s1))
    r = client.post(url, headers=auth(s2)).json()
    assert r["assignee_id"] == s2["id"] and r["previous_assignee_id"] == s1["id"]
    with SessionLocal() as db:
        rows = db.query(AdminAudit).filter(AdminAudit.action == "ticket_claim").order_by(AdminAudit.id).all()
        assert [x.admin_id for x in rows] == [s1["id"], s2["id"]]
        assert f"#{s1['id']}" in rows[1].detail
    client.post(f"{API}/admin/tickets/{tid}/resolve", json={"reply": "好了"}, headers=auth(s2))
    assert client.post(url, headers=auth(s1)).status_code == 404   # 结了单的不能再认领


def test_submitter_sees_claimed_and_escalation_without_admin_identity(client):
    s1 = _admin(client, "13800250071", ["support"])
    u, tid = _ticket(client, "13800250072")
    mine = client.get(f"{API}/support/tickets", headers=auth(u)).json()[0]
    assert mine["claimed"] is False and mine["escalation_level"] == 0
    client.post(f"{API}/admin/tickets/{tid}/claim", headers=auth(s1))
    _age(tid, 49)
    client.post(JOB, headers=JOB_HEADERS)
    mine = client.get(f"{API}/support/tickets", headers=auth(u)).json()[0]
    assert mine["claimed"] is True and mine["escalation_level"] == 2 and mine["waited_hours"] == 49
    assert "assignee_id" not in mine and "assignee_nickname" not in mine, "提单人不该看到是哪位管理员"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(mine, "MyTicket")


def test_due_level_is_zero_once_resolved():
    """升级判断本身也认状态：别处（比如以后的详情页）调它时，结了单的不该算超时。"""
    from app.modules.support.escalation import due_level

    old = utcnow() - timedelta(hours=100)
    assert due_level(Ticket(status="open", created_at=old)) == 2
    assert due_level(Ticket(status="resolved", created_at=old)) == 0
    assert due_level(Ticket(status="open", created_at=utcnow())) == 0


def test_urgent_sort_puts_higher_level_first_even_if_newer(client):
    """级别比等待时长优先：主管已介入的那张即使更新，也排在只叫醒了客服的前面。"""
    s1 = _admin(client, "13800250081", ["support"])
    _u, older = _ticket(client, "13800250082", "等得久但只到第 1 级")
    _u2, newer = _ticket(client, "13800250083", "较新但已到第 2 级")
    _age(older, 40)
    _age(newer, 30)
    with SessionLocal() as db:
        db.get(Ticket, older).escalation_level = 1
        db.get(Ticket, newer).escalation_level = 2
        db.commit()
    ids = [r["id"] for r in client.get(f"{API}/admin/tickets", params={"sort": "urgent"}, headers=auth(s1)).json()]
    assert ids == [newer, older]
