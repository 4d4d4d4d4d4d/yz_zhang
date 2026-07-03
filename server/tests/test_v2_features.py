"""V2 批次：CRED-005 保证金 / ACC-022 资质准入 / SC-011 存证链 / ACC-033 黑名单
IM-004 消息撤回 / AI-DEC-022/023 编排韧性"""
import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


# ---------- 保证金（CRED-005） ----------
def test_cred005_deposit_frozen_and_returned_on_completion(client, requester, worker):
    topup(client, requester, 40000)
    topup(client, worker, 5000)
    task = publish_task(client, requester, deposit_cents=5000)
    match_and_fund(client, requester, worker, task)
    # 成交后保证金冻结
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["frozen_cents"] == 5000 and ww["available_cents"] == 0
    # 闭环后退还
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["frozen_cents"] == 0
    assert ww["available_cents"] == 5000 + 20000 - 20000 * 800 // 10000


def test_cred005_deposit_insufficient_blocks_match(client, requester, worker):
    task = publish_task(client, requester, deposit_cents=99999)
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    app_id = r.json()["id"]
    r = client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester))
    assert r.status_code == 400  # 执行者余额不足以缴纳保证金


def test_cred005_deposit_forfeited_on_executor_cancel(client, requester, worker):
    topup(client, requester, 40000)
    topup(client, worker, 5000)
    task = publish_task(client, requester, deposit_cents=5000)
    match_and_fund(client, requester, worker, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(worker))
    assert r.json()["cancelled_by"] == "executor"
    # 保证金罚没给发布者；托管全额退回
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["frozen_cents"] == 0 and ww["available_cents"] == 0
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["available_cents"] == 40000 + 5000
    contract = client.get(f"/api/v1/contracts/by-task/{task['id']}", headers=auth(requester)).json()
    assert contract["deposit_status"] == "forfeited"


# ---------- 资质准入（ACC-022/LAW-003 律师市场） ----------
def test_acc022_restricted_category_requires_certification(client, requester, worker):
    task = publish_task(client, requester, title="合同纠纷咨询", category="法律咨询")
    # 无资质报名被拒
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 400 and "律师" in r.json()["detail"]["message"]
    # 提交律师资质后可报名
    r = client.post(
        "/api/v1/users/me/certifications",
        json={"name": "律师", "license_no": "A20260001"},
        headers=auth(worker),
    )
    assert r.status_code == 201
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 201
    # 资质徽章在公开名片可见（联动 ACC-023）
    me = client.get("/api/v1/users/me", headers=auth(worker)).json()
    assert "律师" in me["certifications"]


# ---------- 存证链（SC-011） ----------
def test_sc011_anchor_chain_records_and_verifies(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    contract_id = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    # 签署/托管/放款均入链
    anchors = client.get(f"/api/v1/anchors/contracts/{contract_id}", headers=auth(requester)).json()
    events = [a["event_type"] for a in anchors]
    assert events == ["contract.signed", "contract.funded", "contract.released"]
    # 链完整性校验通过
    v = client.get("/api/v1/anchors/verify").json()
    assert v["valid"] is True and v["total"] == 3
    # 篡改历史记录 → 校验失败并定位（防篡改核心保证）
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE anchor_entries SET payload = '{}' WHERE seq = 2"))
    v = client.get("/api/v1/anchors/verify").json()
    assert v["valid"] is False and v["broken_at_seq"] == 2


# ---------- 黑名单（ACC-033） ----------
def test_acc033_block_stops_chat_apply_and_recommend(client, requester, worker):
    client.patch("/api/v1/users/me", json={"skills": ["保洁"], "lat": 31.23, "lng": 121.47},
                 headers=auth(worker))
    r = client.post(f"/api/v1/users/{worker['id']}/block", headers=auth(requester))
    assert r.json()["blocked"] is True
    # 私聊被拒（双向）
    r = client.post("/api/v1/conversations/direct", json={"user_id": requester["id"]}, headers=auth(worker))
    assert r.status_code == 403
    # 报名被拒
    task = publish_task(client, requester)
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 403
    # 推荐排除
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(requester)).json()
    assert all(rec["user_id"] != worker["id"] for rec in recs)
    # 解除拉黑恢复
    client.post(f"/api/v1/users/{worker['id']}/block", headers=auth(requester))
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 201


# ---------- 消息撤回（IM-004） ----------
def test_im004_recall_within_window_keeps_audit_copy(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    conv = client.get("/api/v1/conversations", headers=auth(worker)).json()[0]
    msg = client.post(f"/api/v1/conversations/{conv['id']}/messages",
                      json={"content": "发错了"}, headers=auth(worker)).json()
    # 对方不能撤回
    r = client.post(f"/api/v1/messages/{msg['id']}/recall", headers=auth(requester))
    assert r.status_code == 403
    # 发送者撤回成功 → 展示层隐藏
    r = client.post(f"/api/v1/messages/{msg['id']}/recall", headers=auth(worker))
    assert r.status_code == 200
    msgs = client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth(worker)).json()
    assert msgs[0]["content"] == "[消息已撤回]" and msgs[0]["recalled"] is True
    # 审计副本保留（DB 原文未删，管理员可见）
    with engine.begin() as conn:
        raw = conn.execute(sa.text("SELECT content FROM messages WHERE id = :id"), {"id": msg["id"]}).scalar()
    assert raw == "发错了"
    # 超时撤回被拒
    msg2 = client.post(f"/api/v1/conversations/{conv['id']}/messages",
                       json={"content": "旧消息"}, headers=auth(worker)).json()
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE messages SET created_at = datetime('now', '-10 minutes') WHERE id = :id"),
                     {"id": msg2["id"]})
    r = client.post(f"/api/v1/messages/{msg2['id']}/recall", headers=auth(worker))
    assert r.status_code == 403


# ---------- 编排韧性（AI-DEC-022/023） ----------
def test_aidec023_subtask_respawns_after_executor_default(client, requester, worker):
    topup(client, requester, 2000000)
    # 建母任务并分解为两步
    r = client.post("/api/v1/tasks", json={
        "title": "门店翻新", "category": "维修", "task_type": "project",
        "budget_cents": 100000, "is_remote": True, "publish_now": False,
    }, headers=auth(requester))
    parent = r.json()
    dec = client.post(f"/api/v1/tasks/{parent['id']}/decompositions", headers=auth(requester)).json()
    items = [{"title": "第一步", "budget_cents": 100000, "required_skills": [], "depends_on_idx": []}]
    client.patch(f"/api/v1/decompositions/{dec['id']}", json={"items": items}, headers=auth(requester))
    child = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester)).json()["children"][0]
    # 成交后执行者违约取消
    match_and_fund(client, requester, worker, child)
    client.post(f"/api/v1/tasks/{child['id']}/cancel", headers=auth(worker))
    # AI-DEC-023：自动重新发布同款子任务
    tree = client.get(f"/api/v1/tasks/{parent['id']}/tree", headers=auth(requester)).json()
    statuses = sorted(c["status"] for c in tree["children"])
    assert statuses == ["cancelled", "published"]
    # 发布者收到预警通知（AI-DEC-022）
    notes = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any("自动重新招募" in n["title"] for n in notes)


def test_aidec022_deadline_alert_job(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    # 设置已过期的截止时间
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE tasks SET deadline = datetime('now', '-1 day') WHERE id = :id"),
                     {"id": task["id"]})
    r = client.post("/api/v1/tasks/jobs/deadline-alerts")
    assert r.json()["alerted"] == 1
    notes = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any("任务已逾期" == n["title"] for n in notes)
