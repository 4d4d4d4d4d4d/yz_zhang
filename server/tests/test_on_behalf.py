"""SCN-119 替别人发单（175 号 spec，V202）。

子女替爸妈、主人替家里发单：发单人与服务对象是两个人。以前只能把对方的称呼和电话写进说明里——接单前谁都看得到。
现在：替谁、到场联系谁单独填，**只给成交双方**；发单前必须确认问过本人；结束 30 天后清掉联系方式；注销清掉；机器不能代勾。
"""
import sqlalchemy as sa

from app.core.db import SessionLocal, engine
from app.modules.task.models import Task
from tests.conftest import JOB_HEADERS, auth, register, topup, verify_user
from tests.test_task_flow import CLEAN_TASK, match_and_fund

API = "/api/v1/tasks"
ON_BEHALF = {"on_behalf": True, "recipient_label": "我妈", "onsite_contact": "王阿姨 13900001111", "recipient_consented": True}


def _post(client, u, **kw):
    return client.post(API, json={**CLEAN_TASK, "category": "维修", **kw}, headers=auth(u))


def test_recipient_details_are_only_for_the_two_parties(client, requester, worker):
    t = _post(client, requester, **ON_BEHALF).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(t, "Task")
    assert t["on_behalf"] is True and t["recipient_label"] == "我妈" and t["onsite_contact"] == "王阿姨 13900001111"
    # 接单前：别人只看得到「这是替别人发的」
    outsider = client.get(f"{API}/{t['id']}", headers=auth(worker)).json()
    assert outsider["on_behalf"] is True and outsider["recipient_label"] == "" and outsider["onsite_contact"] == ""
    square = client.get(API, headers=auth(worker)).json()
    rows = square["items"] if isinstance(square, dict) else square
    row = next(r for r in rows if r["id"] == t["id"])
    assert row["onsite_contact"] == "" and row["recipient_label"] == ""
    # 成交后：接单的人看得到找谁、打给谁
    topup(client, requester, 40000)
    match_and_fund(client, requester, worker, t)
    party = client.get(f"{API}/{t['id']}", headers=auth(worker)).json()
    assert party["recipient_label"] == "我妈" and party["onsite_contact"] == "王阿姨 13900001111"
    with SessionLocal() as db:
        assert db.get(Task, t["id"]).recipient_consent_at is not None, "确认问过本人的时间要记下"


def test_must_name_the_recipient_and_confirm_consent(client, requester):
    r = _post(client, requester, **{**ON_BEHALF, "recipient_label": "  "})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "recipient_label_required"
    r = _post(client, requester, **{**ON_BEHALF, "recipient_consented": False})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "recipient_consent_required"
    assert "问过本人" in r.json()["detail"]["message"]
    # 没勾「替别人发」却带了服务对象的信息：拒，免得悄悄带上别人的信息
    r = _post(client, requester, onsite_contact="13900001111")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "recipient_without_on_behalf"
    # 不替别人发：照旧
    r = _post(client, requester)
    assert r.status_code == 201 and r.json()["on_behalf"] is False


def test_slots_carry_the_recipient_so_each_helper_knows_whom_to_find(client, requester):
    t = _post(client, requester, people_needed=2, **ON_BEHALF).json()
    with SessionLocal() as db:
        slots = db.query(Task).filter(Task.parent_id == t["id"]).all()
        assert len(slots) == 2
        assert all(s.on_behalf and s.recipient_label == "我妈" and s.onsite_contact == "王阿姨 13900001111"
                   and s.recipient_consent_at is not None for s in slots)


def test_contact_is_purged_30_days_after_close_but_the_label_stays(client, requester, worker):
    topup(client, requester, 40000)
    t = _post(client, requester, **ON_BEHALF).json()
    match_and_fund(client, requester, worker, t)
    client.post(f"{API}/{t['id']}/deliver", headers=auth(worker))
    client.post(f"{API}/{t['id']}/accept-delivery", headers=auth(requester))
    r = client.post(f"{API}/jobs/purge-locations", headers=JOB_HEADERS).json()
    assert r["purged_contacts"] == 0, "刚结束的不清（还可能要联系、要处理纠纷）"
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE tasks SET completed_at = datetime('now', '-31 days') WHERE id = :id"), {"id": t["id"]})
    r = client.post(f"{API}/jobs/purge-locations", headers=JOB_HEADERS).json()
    assert r["purged_contacts"] == 1 and "purged_logs" in r
    with SessionLocal() as db:
        row = db.get(Task, t["id"])
        assert row.onsite_contact == "" and row.recipient_label == "我妈" and row.on_behalf


def test_export_carries_it_for_the_poster_only_and_deletion_erases_it(client):
    me = register(client, "13800000301", "女儿")
    verify_user(client, me, "张三")
    t = _post(client, me, **ON_BEHALF).json()
    out = client.get("/api/v1/users/me/export", headers=auth(me)).json()
    row = next(x for x in out["tasks"] if x["id"] == t["id"])
    assert row["on_behalf"] is True and row["onsite_contact"] == "王阿姨 13900001111" and row["recipient_consent_at"]
    plain = _post(client, me).json()
    out = client.get("/api/v1/users/me/export", headers=auth(me)).json()
    assert "on_behalf" not in next(x for x in out["tasks"] if x["id"] == plain["id"])
    client.post(f"{API}/{t['id']}/cancel", headers=auth(me))
    client.post(f"{API}/{plain['id']}/cancel", headers=auth(me))
    r = client.post("/api/v1/users/me/deactivate", headers=auth(me))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        row = db.get(Task, t["id"])
        assert row.onsite_contact == "" and row.recipient_label == "（已注销）" and row.on_behalf


def test_machine_api_cannot_tick_consent_for_a_human():
    from app.modules.openapi import machine

    src = open(machine.__file__, encoding="utf-8").read()
    assert "on_behalf_needs_human" in src


def test_openapi_webhooks_never_carry_the_recipient():
    from app.modules.openapi.service import _strip_sensitive

    out = _strip_sensitive({"task_id": 1, "onsite_contact": "139", "recipient_label": "我妈", "status": "published"})
    assert out == {"task_id": 1, "status": "published"}


def test_executor_export_does_not_carry_the_third_party(client, requester, worker):
    """接单人导出自己的数据时，那一单不带服务对象的称呼与联系方式：那是发单人替别人给的，不是接单人的个人信息。"""
    topup(client, requester, 40000)
    t = _post(client, requester, **ON_BEHALF).json()
    match_and_fund(client, requester, worker, t)
    out = client.get("/api/v1/users/me/export", headers=auth(worker)).json()
    row = next(x for x in out["tasks"] if x["id"] == t["id"])
    assert row["role"] == "executor" and "onsite_contact" not in row and "recipient_label" not in row
