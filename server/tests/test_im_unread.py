"""IM-010 聊天未读位点：会话未读数 + 全局红点 + 标记已读 + 列表排序。

此前 IM 完全没有已读状态：用户无法知道哪个会话有新消息。
"""
from .conftest import auth, topup
from .test_task_flow import match_and_fund, publish_task


def _task_conversation(client, requester, worker, title="聊天单"):
    """托管成功会自动建任务会话（IM-002）。"""
    topup(client, requester, 30000)
    task = publish_task(client, requester, title=title, budget_cents=20000)
    match_and_fund(client, requester, worker, task)
    convs = client.get("/api/v1/conversations", headers=auth(worker)).json()
    return next(c for c in convs if c["task_id"] == task["id"])


def test_unread_counts_and_mark_read(client, requester, worker):
    conv = _task_conversation(client, requester, worker)
    cid = conv["id"]

    # 初始无未读
    assert client.get("/api/v1/conversations/unread-count",
                      headers=auth(worker)).json()["unread"] == 0

    # 发布者发两条 → 执行者有 2 条未读；发布者自己不计未读
    for i in range(2):
        client.post(f"/api/v1/conversations/{cid}/messages",
                    json={"content": f"进度确认{i}"}, headers=auth(requester))
    assert client.get("/api/v1/conversations/unread-count",
                      headers=auth(worker)).json()["unread"] == 2
    assert client.get("/api/v1/conversations/unread-count",
                      headers=auth(requester)).json()["unread"] == 0

    # 会话列表带未读数与最后一条预览
    convs = client.get("/api/v1/conversations", headers=auth(worker)).json()
    mine = next(c for c in convs if c["id"] == cid)
    assert mine["unread_count"] == 2
    assert mine["last_message"]["content"] == "进度确认1"

    # 标记已读 → 归零
    client.post(f"/api/v1/conversations/{cid}/read", headers=auth(worker))
    assert client.get("/api/v1/conversations/unread-count",
                      headers=auth(worker)).json()["unread"] == 0
    # 新消息重新计未读
    client.post(f"/api/v1/conversations/{cid}/messages",
                json={"content": "还有一条"}, headers=auth(requester))
    assert client.get("/api/v1/conversations/unread-count",
                      headers=auth(worker)).json()["unread"] == 1


def test_conversation_list_sorts_unread_first(client, requester, worker):
    c1 = _task_conversation(client, requester, worker, title="会话甲")
    c2 = _task_conversation(client, requester, worker, title="会话乙")
    # 只在较早的会话 c1 里发消息 → 它应排在前面（有未读优先）
    client.post(f"/api/v1/conversations/{c1['id']}/messages",
                json={"content": "看这里"}, headers=auth(requester))
    convs = client.get("/api/v1/conversations", headers=auth(worker)).json()
    assert convs[0]["id"] == c1["id"] and convs[0]["unread_count"] == 1
    assert any(c["id"] == c2["id"] and c["unread_count"] == 0 for c in convs)


def test_mark_read_requires_participant(client, requester, worker):
    from .conftest import register, verify_user

    conv = _task_conversation(client, requester, worker, title="鉴权会话")
    stranger = register(client, "36000000001", "路人")
    verify_user(client, stranger, "路人甲")
    r = client.post(f"/api/v1/conversations/{conv['id']}/read", headers=auth(stranger))
    assert r.status_code == 403
