"""IM-060 会话列表写出「在和谁聊」（V140 真浏览器演示发现：列表上只有「私聊 #2」）。"""
from tests.conftest import auth, register, topup


def test_direct_conversation_is_titled_with_the_other_persons_nickname(client):
    a = register(client, "13900017001", "林发布")
    b = register(client, "13900017002", "陈设计")
    conv = client.post("/api/v1/conversations/direct", json={"user_id": b["id"]}, headers=auth(a)).json()
    mine = client.get("/api/v1/conversations", headers=auth(a)).json()
    theirs = client.get("/api/v1/conversations", headers=auth(b)).json()
    assert [c["title"] for c in mine if c["id"] == conv["id"]] == ["陈设计"]
    assert [c["title"] for c in theirs if c["id"] == conv["id"]] == ["林发布"]


def test_task_conversation_is_titled_with_the_task(client, requester, worker):
    from tests.test_task_flow import match_and_fund, publish_task

    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    rows = client.get("/api/v1/conversations", headers=auth(worker)).json()
    assert any(c["kind"] == "task" and c["title"] == f"任务：{task['title']}" for c in rows)
