"""RISK-010~015（399 号 spec，V426）举报：类型、对象核对、不重复、每日上限、处理结果回给举报人、数据导出。"""
from app.core.db import SessionLocal

from .conftest import auth, make_admin, register
from .test_task_flow import publish_task

R = "/api/v1/reports"


def rep(client, user, target_type, target_id, reason="内容不当", **kw):
    return client.post(R, json={"target_type": target_type, "target_id": target_id, "reason": reason, **kw},
                       headers=auth(user))


def code(r):
    return r.json()["detail"]["code"]


def test_risk010_category_reaches_queue_and_defaults_to_other(client):
    a = register(client, "13900426001", "举报人")
    b = register(client, "13900426002", "被举报")
    adm = make_admin(client, "13900426003")
    r = rep(client, a, "user", b["id"], "冒充客服要我转账", category="fraud")
    assert r.status_code == 201, r.text
    assert r.json()["duplicate"] is False
    t = publish_task(client, b)
    assert rep(client, a, "task", t["id"]).status_code == 201   # 老客户端不传类型照旧能用
    q = {x["target_type"]: x for x in client.get("/api/v1/admin/reports", headers=auth(adm)).json()}
    assert q["user"]["category"] == "fraud" and q["user"]["category_label"] == "诈骗或骗钱"
    assert q["task"]["category"] == "other" and q["task"]["category_label"] == "其他"
    assert rep(client, a, "user", b["id"], category="spam").status_code == 422


def test_risk011_target_must_exist(client):
    a = register(client, "13900426011", "举报人")
    for tt in ("task", "content", "user", "message"):
        r = rep(client, a, tt, 987654)
        assert r.status_code == 404, (tt, r.text)
        assert code(r) == "report_target_not_found"


def test_risk011_cannot_report_own_things(client):
    a = register(client, "13900426021", "自己")
    t = publish_task(client, a)
    c = client.post("/api/v1/contents", json={"kind": "post", "body": "我的作品"}, headers=auth(a)).json()
    for tt, tid in (("user", a["id"]), ("task", t["id"]), ("content", c["id"])):
        r = rep(client, a, tt, tid)
        assert r.status_code == 400, (tt, r.text)
        assert code(r) == "report_own_target"
        assert "自己" in r.json()["detail"]["message"]


def test_risk011_only_conversation_members_can_report_a_message(client):
    a = register(client, "13900426031", "甲")
    b = register(client, "13900426032", "乙")
    outsider = register(client, "13900426033", "路人")
    conv = client.post("/api/v1/conversations/direct", json={"user_id": b["id"]}, headers=auth(a)).json()
    m = client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "加我微信转账"},
                    headers=auth(a)).json()
    # 会话外的人拿 id 试不出消息存在
    r = rep(client, outsider, "message", m["id"])
    assert r.status_code == 404 and code(r) == "report_target_not_found"
    assert code(rep(client, a, "message", m["id"])) == "report_own_target"
    assert rep(client, b, "message", m["id"], "引导站外转账", category="fraud").status_code == 201


def test_risk012_pending_duplicate_returns_existing(client):
    a = register(client, "13900426041", "举报人")
    b = register(client, "13900426042", "被举报")
    adm = make_admin(client, "13900426043")
    first = rep(client, a, "user", b["id"]).json()
    again = rep(client, a, "user", b["id"], "再说一次")
    assert again.status_code in (200, 201)
    assert again.json() == {"id": first["id"], "status": "pending", "duplicate": True}
    assert len([x for x in client.get("/api/v1/admin/reports", headers=auth(adm)).json()
                if x["target_id"] == b["id"]]) == 1
    # 处理完以后再举报，是新的一条
    client.post(f"/api/v1/admin/reports/{first['id']}/resolve", json={"action": "dismiss"}, headers=auth(adm))
    third = rep(client, a, "user", b["id"]).json()
    assert third["id"] != first["id"] and third["duplicate"] is False


def test_risk012_daily_limit(client, monkeypatch):
    from app.modules.admin import reports as rpt

    monkeypatch.setattr(rpt, "DAILY_LIMIT", 2)
    a = register(client, "13900426051", "举报人")
    targets = [register(client, f"1390042605{i}", f"对象{i}") for i in (2, 3, 4)]
    assert rep(client, a, "user", targets[0]["id"]).status_code == 201
    assert rep(client, a, "user", targets[1]["id"]).status_code == 201
    r = rep(client, a, "user", targets[2]["id"])
    assert r.status_code == 429 and code(r) == "report_daily_limit"
    assert "明天" in r.json()["detail"]["message"]
    # 重复举报不算新的一次，也不被上限挡住
    assert rep(client, a, "user", targets[0]["id"]).json()["duplicate"] is True


def test_risk013_mine_shows_result_and_reporter_is_notified(client):
    a = register(client, "13900426061", "举报人")
    other = register(client, "13900426062", "别人")
    b = register(client, "13900426063", "被举报")
    adm = make_admin(client, "13900426064")
    t = publish_task(client, b)
    rid = rep(client, a, "task", t["id"], "代写论文", category="illegal").json()["id"]
    rep(client, other, "user", b["id"])
    mine = client.get(f"{R}/mine", headers=auth(a)).json()
    assert [x["id"] for x in mine["items"]] == [rid]           # 只看得到自己的
    row = mine["items"][0]
    assert row["status"] == "pending" and row["result"] == "" and row["resolved_at"] is None
    assert row["category_label"] == "违法违规" and "handled_by" not in row
    assert mine["categories"]["harassment"] == "骚扰或辱骂"

    r = client.post(f"/api/v1/admin/reports/{rid}/resolve", json={"action": "remove_content"}, headers=auth(adm))
    assert r.status_code == 200, r.text
    row = client.get(f"{R}/mine", headers=auth(a)).json()["items"][0]
    assert row["status"] == "resolved" and row["result"] == "已下架违规内容" and row["resolved_at"]
    notes = client.get("/api/v1/notifications", headers=auth(a)).json()
    notes = notes["items"] if isinstance(notes, dict) else notes
    hit = [n for n in notes if n["title"] == "你的举报已处理"]
    assert hit and "已下架违规内容" in hit[0]["body"] and f"#{t['id']}" in hit[0]["body"]


def test_risk013_system_report_resolves_without_reporter(client):
    from app.modules.admin.models import Report

    adm = make_admin(client, "13900426071")
    b = register(client, "13900426072", "被风控")
    with SessionLocal() as db:
        row = Report(reporter_id=0, target_type="user", target_id=b["id"], reason="风控自动生成")
        db.add(row)
        db.commit()
        rid = row.id
    r = client.post(f"/api/v1/admin/reports/{rid}/resolve", json={"action": "dismiss"}, headers=auth(adm))
    assert r.status_code == 200, r.text


def test_risk015_export_includes_reports_only_when_present(client):
    a = register(client, "13900426081", "举报人")
    b = register(client, "13900426082", "被举报")
    assert "reports" not in client.get("/api/v1/users/me/export", headers=auth(a)).json()
    rep(client, a, "user", b["id"], "骚扰", category="harassment")
    ex = client.get("/api/v1/users/me/export", headers=auth(a)).json()
    assert [x["category"] for x in ex["reports"]] == ["harassment"]
    assert "reports" not in client.get("/api/v1/users/me/export", headers=auth(b)).json()
