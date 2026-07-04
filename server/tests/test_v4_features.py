"""V4 批次：RISK-003 反欺诈 / PAY-006 对账 / MATCH-003 频控 / CIR-009/010
IM-009 卡片消息 / ACC-030/013 / KB-003/013 / TASK-003 / GEO-030 / SC-010"""
import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def make_admin(client, phone="13000000000"):
    admin = register(client, phone, "运营")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def close_loop(client, requester, worker, **overrides):
    task = publish_task(client, requester, **overrides)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    return task


# ---------- 反欺诈（RISK-003） ----------
def test_risk003_frequent_pair_flagged_no_credit(client, requester, worker):
    admin = make_admin(client)
    topup(client, requester, 200000)
    for i in range(2):
        close_loop(client, requester, worker, title=f"正常单{i}")
    prof = client.get(f"/api/v1/users/{worker['id']}").json()
    assert prof["tasks_completed"] == 2  # 前两单正常累计
    # 第三单触发刷单嫌疑：资金正常放，但信用不加 + 进人审队列
    close_loop(client, requester, worker, title="第三单")
    prof = client.get(f"/api/v1/users/{worker['id']}").json()
    assert prof["tasks_completed"] == 2  # 不再累计
    queue = client.get("/api/v1/admin/reports", headers=auth(admin)).json()
    assert any("疑似刷单" in r["reason"] for r in queue)


# ---------- 对账（PAY-006） ----------
def test_pay006_reconcile_ok_and_detects_tamper(client, requester, worker):
    admin = make_admin(client)
    topup(client, requester, 100000)
    topup(client, worker, 5000)
    task = publish_task(client, requester, deposit_cents=5000)
    match_and_fund(client, requester, worker, task)  # 托管中 + 保证金冻结中
    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert r["ok"] is True and r["mismatches"] == []
    # 人为篡改某账户余额 → 全局守恒被打破并被发现
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE wallet_accounts SET available_cents = available_cents + 999 WHERE user_id = :id"),
                     {"id": worker["id"]})
    r = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert r["ok"] is False
    assert any(m["invariant"] == "global_conservation" for m in r["mismatches"])


# ---------- 推送频控（MATCH-003） ----------
def test_match003_subscription_daily_cap(client, requester, worker):
    client.post("/api/v1/subscriptions", json={"category": "保洁"}, headers=auth(worker))
    for i in range(7):
        publish_task(client, requester, title=f"保洁单{i}")
    notes = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert sum(1 for n in notes if n["title"] == "订阅类目有新任务") == 5  # 日上限 5


# ---------- 同圈加成与圈层面板（CIR-010/009） ----------
def test_cir010_same_circle_boost_in_recommendation(client, requester, worker):
    # 两个条件相同的候选人，一个与发布者同圈
    rival = register(client, "13000000002", "圈外对手")
    verify_user(client, rival, "周九")
    for u in (worker, rival):
        client.patch("/api/v1/users/me", json={"skills": ["保洁"], "lat": 31.23, "lng": 121.47},
                     headers=auth(u))
    c = client.post("/api/v1/circles", json={"name": "浦东保洁圈", "kind": "skill", "skill_tag": "保洁"},
                    headers=auth(requester)).json()
    client.post(f"/api/v1/circles/{c['id']}/join", headers=auth(worker))
    task = publish_task(client, requester)
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(requester)).json()
    assert recs[0]["user_id"] == worker["id"]
    assert "同圈成员" in recs[0]["reasons"]


def test_cir009_stats_owner_only(client, requester, worker):
    c = client.post("/api/v1/circles", json={"name": "统计圈", "kind": "interest"},
                    headers=auth(requester)).json()
    client.post(f"/api/v1/circles/{c['id']}/join", headers=auth(worker))
    client.post("/api/v1/contents", json={"body": "圈内帖", "circle_id": c["id"], "visibility": "circle"},
                headers=auth(worker))
    stats = client.get(f"/api/v1/circles/{c['id']}/stats", headers=auth(requester)).json()
    assert stats["member_count"] == 2 and stats["posts"] == 1
    r = client.get(f"/api/v1/circles/{c['id']}/stats", headers=auth(worker))
    assert r.status_code == 403  # 普通成员不可见


# ---------- 卡片消息（IM-009） ----------
def test_im009_quote_card_message(client, requester, worker):
    import json

    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    conv = client.get("/api/v1/conversations", headers=auth(worker)).json()[0]
    r = client.post(f"/api/v1/conversations/{conv['id']}/quote-cards",
                    json={"task_id": task["id"], "price_cents": 25000, "note": "含深度清洁"},
                    headers=auth(worker))
    assert r.status_code == 201 and r.json()["kind"] == "quote"
    msgs = client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth(requester)).json()
    card = [m for m in msgs if m["kind"] == "quote"][0]
    payload = json.loads(card["content"])
    assert payload["price_cents"] == 25000
    assert card["risk_flagged"] is False  # 结构化卡片不触发站外风控


# ---------- 隐私与服务定价（ACC-030/013） ----------
def test_acc030_privacy_hides_profile_details(client, requester, worker):
    client.patch("/api/v1/users/me",
                 json={"bio": "十年保洁经验", "skills": ["保洁"], "service_rate_cents": 8000,
                       "available_times": "工作日晚间/周末全天"},
                 headers=auth(worker))
    prof = client.get(f"/api/v1/users/{worker['id']}").json()
    assert prof["service_rate_cents"] == 8000 and "十年" in prof["bio"]
    # 关闭公开档案 → 仅信任摘要
    client.patch("/api/v1/users/me", json={"privacy": {"profile_public": False}}, headers=auth(worker))
    prof = client.get(f"/api/v1/users/{worker['id']}").json()
    assert "bio" not in prof and "service_rate_cents" not in prof
    assert prof["credit_score"] > 0  # 信任摘要保留


# ---------- 经验帖（KB-003） ----------
def test_kb003_experience_post_from_closed_task(client, requester, worker):
    topup(client, requester, 40000)
    task = close_loop(client, requester, worker)
    # 发布者不能发（仅执行者）
    r = client.post(f"/api/v1/tasks/{task['id']}/experience-post",
                    json={"body": "本次保洁的三个经验总结……"}, headers=auth(requester))
    assert r.status_code == 403
    r = client.post(f"/api/v1/tasks/{task['id']}/experience-post",
                    json={"body": "本次保洁的三个经验总结……"}, headers=auth(worker))
    assert r.status_code == 201
    post = r.json()
    assert post["kind"] == "case" and post["linked_category"] == "保洁"
    assert post["source_task_id"] == task["id"]


# ---------- 任务模板（TASK-003） ----------
def test_task003_template_with_price_reference(client, requester, worker):
    topup(client, requester, 40000)
    close_loop(client, requester, worker, budget_cents=20000)
    r = client.get("/api/v1/task-templates", params={"category": "保洁"}, headers=auth(requester))
    body = r.json()
    assert "checklist" in body and body["price_reference"]["sample_size"] == 1
    r = client.get("/api/v1/task-templates", params={"category": "冷门类目"}, headers=auth(requester))
    assert r.status_code == 404


# ---------- 城市开通（GEO-030） ----------
def test_geo030_city_gate(client, requester):
    admin = make_admin(client, "13000000003")
    # 未开通城市的线下任务被拒
    r = client.post("/api/v1/tasks", json={
        "title": "成都保洁", "category": "保洁", "budget_cents": 10000,
        "city": "成都", "lat": 30.5, "lng": 104.0, "address_hint": "高新区",
    }, headers=auth(requester))
    assert r.status_code == 400 and "尚未开通" in r.json()["detail"]["message"]
    # 线上任务不受城市限制
    r = client.post("/api/v1/tasks", json={
        "title": "远程设计", "category": "设计", "budget_cents": 10000,
        "is_remote": True, "city": "成都",
    }, headers=auth(requester))
    assert r.status_code == 201
    # 开通后可发
    client.post("/api/v1/admin/cities", json={"name": "成都"}, headers=auth(admin))
    r = client.post("/api/v1/tasks", json={
        "title": "成都保洁", "category": "保洁", "budget_cents": 10000,
        "city": "成都", "lat": 30.5, "lng": 104.0, "address_hint": "高新区",
    }, headers=auth(requester))
    assert r.status_code == 201
    cities = client.get("/api/v1/cities").json()
    assert any(c["name"] == "成都" for c in cities)


# ---------- 合约导出（SC-010） ----------
def test_sc010_contract_export_with_ledger_and_anchors(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    contract_id = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    r = client.get(f"/api/v1/contracts/{contract_id}/export", headers=auth(worker))
    body = r.json()
    assert "服务合约" in body["text"] and "结算凭证" in body["text"] and "存证记录" in body["text"]
    assert body["ledger_count"] >= 2  # 托管 + 放款
    assert body["anchor_head"]
    # 非当事人不可导出
    outsider = register(client, "13000000004")
    r = client.get(f"/api/v1/contracts/{contract_id}/export", headers=auth(outsider))
    assert r.status_code == 403


# ---------- 估价新鲜度（KB-013） ----------
def test_kb013_stale_prices_excluded(client, requester, worker):
    topup(client, requester, 40000)
    close_loop(client, requester, worker, budget_cents=20000)
    ref = client.get("/api/v1/knowledge/price-reference", params={"category": "保洁"}).json()
    assert ref["sample_size"] == 1
    # 数据拨到 200 天前 → 过期淘汰
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE knowledge_cards SET created_at = datetime('now', '-200 days')"))
    ref = client.get("/api/v1/knowledge/price-reference", params={"category": "保洁"}).json()
    assert ref["sample_size"] == 0
