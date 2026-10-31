"""SCN-172 发单、私聊、提工单时写下想伤害自己的话：只给写的人一条心理援助热线（299 号 spec，V326）。

不拦、不告诉对方、不上报；一天最多一条站内信。私聊的响应多一句 `support`，两端显示在输入框下面。
"""
from app.core.crisis import CRISIS_ANSWER, NUDGE_TITLE
from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from tests.conftest import auth
from tests.test_multiday_slots import _post

API = "/api/v1"


def _nudges():
    with SessionLocal() as db:
        return [n.user_id for n in db.query(Notification).filter(Notification.title == NUDGE_TITLE)]


def test_chat_shows_the_hotline_only_to_the_sender_once_a_day(client, requester, worker):
    conv = client.post(f"{API}/conversations/direct", json={"user_id": worker["id"]}, headers=auth(requester)).json()
    url = f"{API}/conversations/{conv['id']}/messages"
    plain = client.post(url, json={"content": "明天几点到？"}, headers=auth(requester)).json()
    assert "support" not in plain, "普通消息响应与以前一样"
    r = client.post(url, json={"content": "最近真的不想活了"}, headers=auth(requester))
    assert r.status_code == 201 and r.json()["support"] == CRISIS_ANSWER, "消息照常发出，发送的人看到热线"
    assert _nudges() == [requester["id"]], "只给发送的人，不告诉对方"
    again = client.post(url, json={"content": "还是想死"}, headers=auth(requester)).json()
    assert again["support"] == CRISIS_ANSWER and _nudges() == [requester["id"]], "一天只发一条站内信"
    other = client.post(url, json={"content": "我其实也不想活了"}, headers=auth(worker)).json()
    assert other["support"] == CRISIS_ANSWER
    assert sorted(_nudges()) == sorted([requester["id"], worker["id"]]), "一天一条是按人算的，别人发过不影响我"
    msgs = client.get(url, headers=auth(worker)).json()
    assert any(m["content"] == "最近真的不想活了" for m in msgs), "不拦消息"


def test_task_posts_and_tickets_also_nudge_the_writer(client, requester):
    t = _post(client, requester, title="想找人陪我散散步", description="最近有点活不下去的感觉，想有人陪着走走")
    assert t.status_code in (200, 201), t.text
    assert _nudges() == [requester["id"]]
    with SessionLocal() as db:
        db.query(Notification).filter(Notification.title == NUDGE_TITLE).delete()
        db.commit()
    r = client.post(f"{API}/support/tickets", json={"subject": "账号问题", "body": "处理不好我就不想活了"}, headers=auth(requester))
    assert r.status_code == 201, r.text
    assert _nudges() == [requester["id"]]
    ok = _post(client, requester, title="上门保洁", description="两室一厅")
    assert ok.status_code in (200, 201) and _nudges() == [requester["id"]], "普通内容不发"
