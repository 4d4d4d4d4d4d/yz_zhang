"""FIN-064 已锁月份的更正说明（265 号 spec，V292）。

锁账（223 号）之后报表一分不变；可要是锁的时候快照本身就错了（例如一笔该算补贴的记成了其他调整），
以前只能在当期记一笔调整，看那个月报表的人不知道它错过、为什么错。现在一位财务写更正说明，
另一位财务批准后，说明挂在那个月的报表与导出上——已出的数仍然不变。
"""
from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from tests.conftest import auth
from tests.test_finance_lock import URL, _months, _seed
from tests.test_ticket_assign_reply import _admin

API = "/api/v1"
C = f"{API}/admin/platform-finance/corrections"


def _locked(client):
    a = _admin(client, "13800360001", ["finance"])
    b = _admin(client, "13800360002", ["finance"])
    _seed()
    assert client.post(f"{API}/admin/platform-finance/lock", json={"through": "2025-02"}, headers=auth(a)).status_code == 200
    return a, b


def test_write_then_second_finance_approves_and_it_shows_on_the_report_and_export(client):
    a, b = _locked(client)
    before = _months(client, auth(a))
    assert all("corrections" not in r for r in before["periods"]), "没有更正时响应与以前一样"
    r = client.post(C, json={"period": "2025-02", "note": "2 月 20 日那笔 3 元应记补贴支出，误记为结算划出",
                             "amount_delta_cents": -300}, headers=auth(a))
    assert r.status_code == 200 and r.json()["status"] == "awaiting_second"
    cid = r.json()["id"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "FinanceCorrectionRow")
    assert "corrections" not in _months(client, auth(a))["periods"][1], "没批准之前不出现在报表上"
    same = client.post(f"{C}/{cid}/approve", headers=auth(a))
    assert same.status_code == 400 and same.json()["detail"]["code"] == "correction_same_approver"
    assert [x["id"] for x in client.get(C, headers=auth(b)).json()] == [cid]
    ok = client.post(f"{C}/{cid}/approve", headers=auth(b))
    assert ok.status_code == 200 and (ok.json()["status"], ok.json()["decided_by"]) == ("approved", b["id"])
    assert client.post(f"{C}/{cid}/approve", headers=auth(b)).json()["detail"]["code"] == "correction_already_decided"
    after = _months(client, auth(a))
    feb = after["periods"][1]
    assert [(x["note"][:8], x["amount_delta_cents"], x["approved_by"]) for x in feb["corrections"]] == [("2 月 20 日", -300, b["id"])]
    _assert_shape(feb, "PlatformFinancePeriod")
    assert {k: v for k, v in feb.items() if k != "corrections"} == before["periods"][1], "已出的数一分不变"
    assert "corrections" not in after["periods"][0]
    q = client.get(URL, params={"granularity": "quarter", "start": "2025-01", "end": "2025-06"}, headers=auth(a)).json()
    assert [x["period"] for x in q["periods"][0]["corrections"]] == ["2025-02"], "季度挂上它三个月里的更正"
    assert "corrections" not in q["periods"][1], "二季度不挂一季度的更正"
    csv = client.get(f"{URL}/export", params={"start": "2025-01", "end": "2025-03"}, headers=auth(a)).json()["csv"]
    lines = csv.splitlines()
    assert lines[0].endswith("本期含补记以前期间（元）,自检"), "表头不变：按列读的不受影响"
    assert lines[4] == "" and lines[5].startswith("更正说明（已批准，不改上表数字）,月份,差额（元）")
    assert lines[6].startswith(",2025-02,-3.00,2 月 20 日那笔 3 元应记补贴支出") and f"#{b['id']}" in lines[6]
    assert len(lines) == 7
    with SessionLocal() as db:
        acts = [x.action for x in db.query(AdminAudit).filter(AdminAudit.target_type == "finance_correction")]
    assert acts == ["finance_correction_request", "finance_correction_approve"]


def test_rules_unlocked_month_short_note_reject_and_roles(client):
    a, b = _locked(client)
    r = client.post(C, json={"period": "2025-03", "note": "三月的数有误需要说明"}, headers=auth(a))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "correction_period_not_closed"
    assert "当期记一笔调整" in r.json()["detail"]["message"]
    r = client.post(C, json={"period": "2025-01", "note": "有误"}, headers=auth(a))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "correction_note_required"
    assert client.post(C, json={"period": "2025-1", "note": "格式不对的月份"}, headers=auth(a)).status_code == 422
    cid = client.post(C, json={"period": "2025-01", "note": "一月佣金笔数应为 2 笔"}, headers=auth(a)).json()["id"]
    bad = client.post(f"{C}/{cid}/reject", json={"reason": ""}, headers=auth(b))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "reason_required"
    rj = client.post(f"{C}/{cid}/reject", json={"reason": "核对过，笔数没错"}, headers=auth(b)).json()
    assert (rj["status"], rj["decision_reason"]) == ("rejected", "核对过，笔数没错")
    assert all("corrections" not in x for x in _months(client, auth(a))["periods"]), "驳回的不出现"
    c2 = client.post(C, json={"period": "2025-01", "note": "写错了先撤回再写"}, headers=auth(a)).json()["id"]
    assert client.post(f"{C}/{c2}/reject", json={}, headers=auth(a)).json()["decision_reason"] == "写的人撤回"
    assert [x["id"] for x in client.get(C, params={"status": "rejected"}, headers=auth(a)).json()] == [c2, cid]
    assert client.post(f"{C}/999999/approve", headers=auth(b)).status_code == 404
    sup = _admin(client, "13800360003", ["support"])
    assert client.get(C, headers=auth(sup)).status_code == 403
    assert client.post(C, json={"period": "2025-01", "note": "客服不能写更正说明"}, headers=auth(sup)).status_code == 403


def test_fin068_gmv_tax_report_has_its_own_corrections(client):
    """FIN-068（269 号 spec）成交额与代扣税表的更正说明：各挂各的表；V285 之前锁的月份（没锁这张表）不能写。"""
    from app.modules.wallet.models import FinancePeriodLock

    a, b = _locked(client)
    G = f"{API}/admin/platform-finance/gmv-tax"
    before = client.get(G, params={"start": "2025-01", "end": "2025-03"}, headers=auth(a)).json()
    r = client.post(C, json={"period": "2025-02", "report": "gmv_tax", "note": "一笔放款重复计入成交额",
                             "amount_delta_cents": -40000}, headers=auth(a))
    assert r.status_code == 200 and r.json()["report"] == "gmv_tax"
    client.post(f"{C}/{r.json()['id']}/approve", headers=auth(b))
    p = client.post(C, json={"period": "2025-01", "note": "平台收支表的一条更正说明"}, headers=auth(a)).json()
    assert p["report"] == "platform", "不传就是平台收支表（与 V292 一样）"
    client.post(f"{C}/{p['id']}/approve", headers=auth(b))
    gmv = client.get(G, params={"start": "2025-01", "end": "2025-03"}, headers=auth(a)).json()
    feb = next(x for x in gmv["periods"] if x["period"] == "2025-02")
    assert [x["note"] for x in feb["corrections"]] == ["一笔放款重复计入成交额"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(feb, "PlatformGmvTaxRow")
    old = next(x for x in before["periods"] if x["period"] == "2025-02")
    assert {k: v for k, v in feb.items() if k != "corrections"} == old, "成交额表的数一分不变"
    assert all("corrections" not in x for x in gmv["periods"] if x["period"] != "2025-02"), "平台收支表的更正不挂到这张表"
    plat = _months(client, auth(a))["periods"]
    assert [x["note"] for x in plat[0]["corrections"]] == ["平台收支表的一条更正说明"] and "corrections" not in plat[1]
    csv = client.get(f"{G}/export", params={"start": "2025-01", "end": "2025-03"}, headers=auth(a)).json()["csv"]
    tail = csv.splitlines()
    assert tail[-2].startswith("更正说明（已批准，不改上表数字）") and tail[-1].startswith(",2025-02,-400.00,一笔放款重复计入成交额")
    with SessionLocal() as db:
        db.query(FinancePeriodLock).filter(FinancePeriodLock.period == "2025-01").one().gmv_tax = None
        db.commit()
    old_lock = client.post(C, json={"period": "2025-01", "report": "gmv_tax", "note": "早先锁的月份没有这张表的快照"}, headers=auth(a))
    assert old_lock.status_code == 400 and old_lock.json()["detail"]["code"] == "correction_gmv_not_locked"
    assert client.post(C, json={"period": "2025-02", "report": "other", "note": "不认识的表"}, headers=auth(a)).status_code == 422


def test_fin069_large_corrections_need_a_super_admin(client):
    """FIN-069（272 号 spec）差额达到超管确认线（默认 ¥10 万，与大额结算同一条线）要超级管理员批准；正负都算。"""
    from app.core.config import settings

    a, b = _locked(client)
    boss = _admin(client, "13800360009", ["super"])
    line = settings.SUPER_SECOND_APPROVAL_CENTS
    big = client.post(C, json={"period": "2025-02", "note": "一笔大额结算记错了月份", "amount_delta_cents": -line}, headers=auth(a)).json()
    assert big["needs_super_second"] is True
    r = client.post(f"{C}/{big['id']}/approve", headers=auth(b))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "correction_needs_super"
    assert "超级管理员" in r.json()["detail"]["message"]
    assert client.post(f"{C}/{big['id']}/approve", headers=auth(boss)).json()["status"] == "approved"
    small = client.post(C, json={"period": "2025-02", "note": "差一点点的小更正说明", "amount_delta_cents": line - 1}, headers=auth(a)).json()
    assert small["needs_super_second"] is False
    assert client.post(f"{C}/{small['id']}/approve", headers=auth(b)).json()["status"] == "approved", "线以下照旧另一位财务就行"
    by_boss = client.post(C, json={"period": "2025-01", "note": "超级管理员写的更正说明"}, headers=auth(boss)).json()
    r = client.post(f"{C}/{by_boss['id']}/approve", headers=auth(b))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "second_approver_rank", "批准人的级别不能低于写的人"
