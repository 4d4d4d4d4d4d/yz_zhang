"""V3 批次：ACC-005/006 会话与注销 / TASK-007 多人任务 / AI-DEC-001/002/025
OPS-004 类目 / MATCH-008 权重 / NTF-003 / CS-013 / DSP-008 / CRED-003 / GEO-021/023/024"""
import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def make_admin(client, phone="13100000000"):
    admin = register(client, phone, "运营")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


# ---------- 会话管理与注销（ACC-005/006） ----------
def test_acc005_session_revoke_invalidates_token(client):
    user = register(client, "13100000001")
    sessions = client.get("/api/v1/auth/sessions", headers=auth(user)).json()
    assert len(sessions) == 1
    # 第二台设备登录
    r = client.post("/api/v1/auth/login", json={"phone": "13100000001", "password": "pass123456"},
                    headers={"User-Agent": "iPhone"})
    other_token = r.json()["token"]
    sessions = client.get("/api/v1/auth/sessions", headers=auth(user)).json()
    assert len(sessions) == 2
    # 踢出第二台设备 → 其 token 失效
    target = [s for s in sessions if "iPhone" in s["device"]][0]
    client.post(f"/api/v1/auth/sessions/{target['id']}/revoke", headers=auth(user))
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {other_token}"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "session_revoked"
    # 本机会话仍有效
    assert client.get("/api/v1/users/me", headers=auth(user)).status_code == 200


def test_acc006_deactivate_blocked_then_succeeds(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    # 有未结算合约 → 阻断
    r = client.post("/api/v1/users/me/deactivate", headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "active_contract"
    # 闭环 + 清空余额后可注销
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    wallet = client.get("/api/v1/wallet", headers=auth(requester)).json()
    client.post("/api/v1/wallet/withdraw", json={"amount_cents": wallet["available_cents"]},
                headers=auth(requester))
    r = client.post("/api/v1/users/me/deactivate", headers=auth(requester))
    assert r.status_code == 200 and r.json()["deleted"] is True
    # 注销后登录态与密码登录均失效
    assert client.get("/api/v1/users/me", headers=auth(requester)).status_code == 403
    r = client.post("/api/v1/auth/login", json={"phone": "13800000001", "password": "pass123456"})
    assert r.status_code == 400
    # 公开页脱敏
    prof = client.get(f"/api/v1/users/{requester['id']}").json()
    assert prof["nickname"] == "已注销用户"


# ---------- 多人任务（TASK-007） ----------
def test_task007_multi_person_slots(client, requester, worker):
    topup(client, requester, 100000)
    r = client.post("/api/v1/tasks", json={
        "title": "开业地推", "category": "活动策划", "budget_cents": 30000,
        "is_remote": True, "people_needed": 3,
    }, headers=auth(requester))
    assert r.status_code == 201, r.text
    parent = r.json()
    slots = parent["slots"]
    assert len(slots) == 3 and all(s["status"] == "published" for s in slots)
    assert sum(s["budget_cents"] for s in slots) == 30000
    # 母任务不在广场（容器），名额在
    square_ids = [t["id"] for t in client.get("/api/v1/tasks").json()]
    assert parent["id"] not in square_ids and slots[0]["id"] in square_ids
    # 走完一个名额闭环
    match_and_fund(client, requester, worker, slots[0])
    client.post(f"/api/v1/tasks/{slots[0]['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{slots[0]['id']}/accept-delivery", headers=auth(requester))
    tree = client.get(f"/api/v1/tasks/{parent['id']}/tree", headers=auth(requester)).json()
    assert tree["progress_pct"] > 0 and tree["all_children_completed"] is False


def test_task007_parent_autocompletes_when_all_slots_done(client, requester, worker):
    topup(client, requester, 100000)
    second = register(client, "13100000002", "第二人")
    verify_user(client, second, "钱七")
    r = client.post("/api/v1/tasks", json={
        "title": "双人搬运", "category": "跑腿", "budget_cents": 20000,
        "is_remote": True, "people_needed": 2,
    }, headers=auth(requester))
    parent, slots = r.json(), r.json()["slots"]
    for slot, executor in zip(slots, (worker, second)):
        match_and_fund(client, requester, executor, slot)
        client.post(f"/api/v1/tasks/{slot['id']}/deliver", headers=auth(executor))
        client.post(f"/api/v1/tasks/{slot['id']}/accept-delivery", headers=auth(requester))
    # 全部名额闭环 → 母任务自动结项 + 通知
    detail = client.get(f"/api/v1/tasks/{parent['id']}", headers=auth(requester)).json()
    assert detail["status"] == "completed"
    notes = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any("母任务已全部完成" == n["title"] for n in notes)
    # AI-DEC-025 结项报告
    report = client.get(f"/api/v1/tasks/{parent['id']}/final-report", headers=auth(requester)).json()
    assert report["children_completed"] == 2 and report["total_cost_cents"] == 20000
    assert "20000" not in report["summary"]  # summary 以元为单位
    assert "200.00" in report["summary"]


# ---------- AI 澄清与可行性（AI-DEC-001/002） ----------
def test_aidec001_clarify_asks_missing_fields(client, requester):
    r = client.post("/api/v1/ai/clarify", json={"title": "帮我搞一下"}, headers=auth(requester))
    body = r.json()
    assert body["ready"] is False
    fields = [q["field"] for q in body["questions"]]
    assert "category" in fields and "budget_cents" in fields and "is_remote" in fields


def test_aidec002_feasibility_from_knowledge_base(client, requester, worker):
    # 先造一条 30000 分的保洁闭环数据
    topup(client, requester, 60000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    # 预算过低 → 预警
    r = client.post("/api/v1/ai/clarify", json={
        "title": "大扫除", "category": "保洁", "budget_cents": 5000,
        "is_remote": False, "city": "上海", "description": "两室一厅",
    }, headers=auth(requester))
    body = r.json()
    assert body["ready"] is True
    assert body["feasibility"]["level"] == "low_budget"


# ---------- 类目管理（OPS-004） ----------
def test_ops004_category_lifecycle(client, requester):
    admin = make_admin(client)
    cats = client.get("/api/v1/categories").json()
    assert any(c["name"] == "法律咨询" and c["required_cert"] == "律师" for c in cats)
    # 停用类目后发布被拒
    cat_id = [c["id"] for c in cats if c["name"] == "二手交易"][0]
    client.patch(f"/api/v1/admin/categories/{cat_id}", params={"active": False}, headers=auth(admin))
    r = client.post("/api/v1/tasks", json={
        "title": "卖旧手机", "category": "二手交易", "budget_cents": 1000, "is_remote": True,
    }, headers=auth(requester))
    assert r.status_code == 400 and "停用" in r.json()["detail"]["message"]
    # 新建类目即可用
    client.post("/api/v1/admin/categories", json={"name": "宠物照看"}, headers=auth(admin))
    r = client.post("/api/v1/tasks", json={
        "title": "喂猫三天", "category": "宠物照看", "budget_cents": 6000, "is_remote": True,
    }, headers=auth(requester))
    assert r.status_code == 201


# ---------- 匹配权重可配（MATCH-008） ----------
def test_match008_weights_configurable(client, requester, worker):
    admin = make_admin(client, "13100000003")
    # 非法权重被拒
    r = client.put("/api/v1/admin/matching-config",
                   json={"skill": 0.9, "credit": 0.9, "distance": 0, "rating": 0},
                   headers=auth(admin))
    assert r.status_code == 400
    # 全压信用分
    r = client.put("/api/v1/admin/matching-config",
                   json={"skill": 0.0, "credit": 1.0, "distance": 0.0, "rating": 0.0},
                   headers=auth(admin))
    assert r.status_code == 200
    # 高信用无技能者 排到 低信用有技能者 前面
    client.patch("/api/v1/users/me", json={"skills": ["保洁"]}, headers=auth(worker))
    rich = register(client, "13100000004", "高信用者")
    verify_user(client, rich, "孙八")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET credit_score = 190 WHERE id = :id"), {"id": rich["id"]})
    task = publish_task(client, requester)
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(requester)).json()
    assert recs[0]["user_id"] == rich["id"]


# ---------- 通知偏好（NTF-003） ----------
def test_ntf003_pref_mutes_task_but_not_funds(client, requester, worker):
    client.put("/api/v1/notifications/prefs", params={"category": "task", "enabled": False},
               headers=auth(worker))
    # funds 不可关闭
    r = client.put("/api/v1/notifications/prefs", params={"category": "funds", "enabled": False},
                   headers=auth(worker))
    assert r.status_code == 400
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    titles = [n["title"] for n in client.get("/api/v1/notifications", headers=auth(worker)).json()]
    assert "报名被采纳" not in titles  # task 类被屏蔽
    assert "资金已托管" in titles  # funds 类必达


# ---------- 工单（CS-013） ----------
def test_cs013_ticket_from_escalation_and_resolution(client, requester):
    admin = make_admin(client, "13100000005")
    r = client.post("/api/v1/support/ask", json={"question": "怎么把头像换成动图"}, headers=auth(requester))
    ticket_id = r.json()["ticket_id"]
    assert r.json()["escalate_to_human"] is True and ticket_id
    queue = client.get("/api/v1/admin/tickets", headers=auth(admin)).json()
    assert any(t["id"] == ticket_id for t in queue)
    client.post(f"/api/v1/admin/tickets/{ticket_id}/resolve",
                json={"reply": "暂不支持动图头像"}, headers=auth(admin))
    mine = client.get("/api/v1/support/tickets", headers=auth(requester)).json()
    assert mine[0]["status"] == "resolved" and "动图" in mine[0]["reply"]
    titles = [n["title"] for n in client.get("/api/v1/notifications", headers=auth(requester)).json()]
    assert "工单已处理" in titles


# ---------- 申诉复核（DSP-008） ----------
def test_dsp008_appeal_corrective_settlement(client, requester, worker):
    admin = make_admin(client, "13100000006")
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    dispute = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                          json={"reason": "只完成一半"}, headers=auth(requester)).json()
    # 原裁决：执行者 30%（6000-佣金）
    client.post(f"/api/v1/disputes/{dispute['id']}/verdict",
                json={"executor_share_bps": 3000, "reason": "规则4.2"}, headers=auth(admin))
    # 执行者申诉
    r = client.post(f"/api/v1/disputes/{dispute['id']}/appeal", headers=auth(worker))
    assert r.status_code == 200
    # 只能申诉一次
    r = client.post(f"/api/v1/disputes/{dispute['id']}/appeal", headers=auth(worker))
    assert r.status_code == 409
    # 复核改为 60% → 差额 30% (6000) 从发布者划转给执行者
    before = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    r = client.post(f"/api/v1/disputes/{dispute['id']}/appeal-verdict",
                    json={"executor_share_bps": 6000, "reason": "部分履约认定过低"}, headers=auth(admin))
    assert r.json()["corrective_delta_cents"] == 6000
    after = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert after - before == 6000


# ---------- 信用等级权益（CRED-003） ----------
def test_cred003_level_discounts_fee(client, requester, worker):
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET credit_score = 150 WHERE id = :id"), {"id": worker["id"]})
    me = client.get("/api/v1/users/me", headers=auth(worker)).json()
    assert me["credit_level"] == "S"
    task = publish_task(client, requester)
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    app_id = r.json()["id"]
    contract_id = client.post(f"/api/v1/applications/{app_id}/accept",
                              headers=auth(requester)).json()["contract_id"]
    contract = client.get(f"/api/v1/contracts/{contract_id}", headers=auth(requester)).json()
    assert contract["fee_bps"] == 600  # S 级费率 6%


# ---------- GEO 安全件（GEO-021/023/024） ----------
def test_geo021_trip_share_lifecycle(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    # 未开启共享 → 不可见
    r = client.get(f"/api/v1/tasks/{task['id']}/trip", headers=auth(requester))
    assert r.status_code == 403
    client.post(f"/api/v1/tasks/{task['id']}/trip-share", params={"enabled": True}, headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/checkin",
                json={"lat": 31.2305, "lng": 121.4738}, headers=auth(worker))
    trip = client.get(f"/api/v1/tasks/{task['id']}/trip", headers=auth(requester)).json()
    assert abs(trip["lat"] - 31.2305) < 1e-6
    # 任务结束后共享失效
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    r = client.get(f"/api/v1/tasks/{task['id']}/trip", headers=auth(requester))
    assert r.status_code == 403


def test_geo023_sos_notifies_counterparty(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/sos",
                    json={"lat": 31.23, "lng": 121.47}, headers=auth(worker))
    assert r.status_code == 201 and "110" in r.json()["guidance"]
    titles = [n["title"] for n in client.get("/api/v1/notifications", headers=auth(requester)).json()]
    assert "对方发出紧急求助" in titles


def test_geo024_location_purge_job(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/checkin",
                json={"lat": 31.2305, "lng": 121.4738}, headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    # 完成时间拨回 31 天前
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE tasks SET completed_at = datetime('now', '-31 days') WHERE id = :id"),
                     {"id": task["id"]})
    r = client.post("/api/v1/tasks/jobs/purge-locations")
    assert r.json()["purged_logs"] == 1
    logs = client.get(f"/api/v1/tasks/{task['id']}/progress", headers=auth(worker)).json()
    assert all("打卡" in log["content"] or log["kind"] != "checkin" for log in logs)  # 记录仍在
    with engine.begin() as conn:
        remaining = conn.execute(sa.text(
            "SELECT COUNT(*) FROM progress_logs WHERE task_id = :id AND lat IS NOT NULL"
        ), {"id": task["id"]}).scalar()
    assert remaining == 0  # 精确坐标已清除
