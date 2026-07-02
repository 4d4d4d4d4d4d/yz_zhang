"""09 IM / 10 客服 / 11 纠纷 / 12 通知"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import CLEAN_TASK, match_and_fund, publish_task


def _funded_task(client, requester, worker, budget=20000):
    topup(client, requester, budget * 2)
    task = publish_task(client, requester, budget_cents=budget)
    match_and_fund(client, requester, worker, task)
    return task


# ---------- IM ----------
def test_im002_task_conversation_auto_created(client, requester, worker):
    task = _funded_task(client, requester, worker)
    convs = client.get("/api/v1/conversations", headers=auth(worker)).json()
    task_convs = [c for c in convs if c["kind"] == "task" and c["task_id"] == task["id"]]
    assert len(task_convs) == 1
    assert set(task_convs[0]["participants"]) == {requester["id"], worker["id"]}


def test_im006_risky_message_flagged(client, requester, worker):
    task = _funded_task(client, requester, worker)
    conv = client.get("/api/v1/conversations", headers=auth(worker)).json()[0]
    r = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "加我微信 13812345678 私下交易便宜点"},
        headers=auth(worker),
    )
    assert r.json()["risk_flagged"] is True and "资金保障" in r.json()["warning"]
    r = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "明天上午九点到"},
        headers=auth(worker),
    )
    assert r.json()["risk_flagged"] is False


def test_im005_stranger_message_limit(client, requester, worker):
    r = client.post(
        "/api/v1/conversations/direct", json={"user_id": worker["id"]}, headers=auth(requester)
    )
    conv_id = r.json()["id"]
    for i in range(5):
        r = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": f"你好 {i}"},
            headers=auth(requester),
        )
        assert r.status_code == 201
    # 第 6 条被限制
    r = client.post(
        f"/api/v1/conversations/{conv_id}/messages", json={"content": "在吗"}, headers=auth(requester)
    )
    assert r.status_code == 400
    # 对方回复后解除
    client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "在"}, headers=auth(worker))
    r = client.post(
        f"/api/v1/conversations/{conv_id}/messages", json={"content": "太好了"}, headers=auth(requester)
    )
    assert r.status_code == 201


def test_im_outsider_cannot_read(client, requester, worker):
    _funded_task(client, requester, worker)
    conv = client.get("/api/v1/conversations", headers=auth(worker)).json()[0]
    outsider = register(client, "13500000001")
    r = client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=auth(outsider))
    assert r.status_code == 403


# ---------- 纠纷 ----------
def _open_dispute(client, requester, worker):
    task = _funded_task(client, requester, worker)
    conv = client.get("/api/v1/conversations", headers=auth(worker)).json()[0]
    client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "活干了一半"},
        headers=auth(worker),
    )
    r = client.post(
        f"/api/v1/tasks/{task['id']}/disputes",
        json={"reason": "只打扫了客厅，卧室没有做"},
        headers=auth(requester),
    )
    assert r.status_code == 201, r.text
    return task, r.json()


def test_dsp001_003_open_freezes_and_collects_evidence(client, requester, worker):
    task, dispute = _open_dispute(client, requester, worker)
    # 任务进入纠纷态
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()["status"] == "disputed"
    # 证据链自动归集（DSP-003）
    assert dispute["evidence"]["message_count"] == 1
    assert "合约" in dispute["evidence"]["contract_terms"] or dispute["evidence"]["contract_terms"]
    # 冻结后不能放款：合约 frozen
    contract = client.get(f"/api/v1/contracts/{dispute['contract_id']}", headers=auth(requester)).json()
    assert contract["frozen"] is True
    # 双方收到通知（NTF/DSP 联动）
    notes = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any("纠纷" in n["title"] for n in notes)


def test_dsp004_settlement_by_counterparty_only(client, requester, worker):
    _task, dispute = _open_dispute(client, requester, worker)
    # 发布者提议五五分
    r = client.post(
        f"/api/v1/disputes/{dispute['id']}/settlement",
        json={"executor_share_bps": 5000},
        headers=auth(requester),
    )
    assert r.status_code == 200
    # 提议方不能自己接受
    r = client.post(f"/api/v1/disputes/{dispute['id']}/settlement/accept", headers=auth(requester))
    assert r.status_code == 403
    # 对方接受 → 自动执行分账
    r = client.post(f"/api/v1/disputes/{dispute['id']}/settlement/accept", headers=auth(worker))
    assert r.status_code == 200 and r.json()["status"] == "settled"
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["available_cents"] == 10000 - 10000 * 800 // 10000  # 50% - 佣金
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 0 and wr["available_cents"] == 30000  # 40000充值-20000托管+10000退回


def test_dsp006_007_verdict_executes_and_penalizes_loser(client, requester, worker):
    _task, dispute = _open_dispute(client, requester, worker)
    arbiter = register(client, "13500000009", "仲裁员")
    # 非管理员不能裁决
    r = client.post(
        f"/api/v1/disputes/{dispute['id']}/verdict",
        json={"executor_share_bps": 3000, "reason": "规则 4.2"},
        headers=auth(arbiter),
    )
    assert r.status_code == 403
    # 提升为仲裁员（模拟后台 RBAC）
    import sqlalchemy as sa

    from app.core.db import engine

    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": arbiter["id"]})
    r = client.post(
        f"/api/v1/disputes/{dispute['id']}/verdict",
        json={"executor_share_bps": 3000, "reason": "依据《平台争议处理规则》4.2：部分履约按比例结算"},
        headers=auth(arbiter),
    )
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    # 执行者拿 30%（败诉方）且信用被扣（CRED-004）
    prof = client.get(f"/api/v1/users/{worker['id']}").json()
    assert prof["credit_score"] == 90
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["available_cents"] == 6000 - 6000 * 800 // 10000


# ---------- 通知 ----------
def test_ntf001_lifecycle_notifications(client, requester, worker):
    task = _funded_task(client, requester, worker)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    worker_titles = [n["title"] for n in client.get("/api/v1/notifications", headers=auth(worker)).json()]
    assert "报名被采纳" in worker_titles
    assert "资金已托管" in worker_titles
    assert "任务款已到账" in worker_titles
    req_titles = [n["title"] for n in client.get("/api/v1/notifications", headers=auth(requester)).json()]
    assert "待验收提醒" in req_titles
    # 已读
    note = client.get("/api/v1/notifications", headers=auth(worker)).json()[0]
    client.post(f"/api/v1/notifications/{note['id']}/read", headers=auth(worker))
    unread = client.get("/api/v1/notifications", params={"unread_only": True}, headers=auth(worker)).json()
    assert all(n["id"] != note["id"] for n in unread)


# ---------- 智能客服 ----------
def test_cs002_faq_answer_with_source(client, requester):
    r = client.post("/api/v1/support/ask", json={"question": "平台佣金费率是多少"}, headers=auth(requester))
    body = r.json()
    assert "8%" in body["answer"] and body["escalate_to_human"] is False


def test_cs003_account_context_for_money_questions(client, requester):
    topup(client, requester, 12345)
    r = client.post("/api/v1/support/ask", json={"question": "我的余额怎么还没到账"}, headers=auth(requester))
    assert r.json()["account_context"]["available_cents"] == 12345


def test_cs006_unknown_question_escalates(client, requester):
    r = client.post("/api/v1/support/ask", json={"question": "宇宙的尽头是什么"}, headers=auth(requester))
    assert r.json()["escalate_to_human"] is True  # 不编造答案
