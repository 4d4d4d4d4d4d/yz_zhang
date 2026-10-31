"""IM-003/020/021/022 好友与群聊（43 号 spec）。

需求回顾查出的降级实现之一：原始 spec 写了「加好友（双向同意）」「通讯录与
备注」「合作过的人」「群聊」，实现里只有圈层自带群聊，没有好友体系。

这里最要紧的一条是 **双向同意**。它不是礼貌，是反骚扰的地基——
单向加好友等于给任何人开了一条无需对方许可的私聊通道，
而这个平台上陌生人之间本来就有真金白银的往来。
"""
from app.core.config import settings

from .conftest import auth, register, topup
from .test_task_flow import match_and_fund, publish_task


def friend_request(client, frm, to_id, remark=""):
    return client.post("/api/v1/friends/requests",
                       json={"user_id": to_id, "remark": remark}, headers=auth(frm))


def decide(client, who, req_id, accept=True):
    return client.post(f"/api/v1/friends/requests/{req_id}/decide?accept={str(accept).lower()}",
                       headers=auth(who))


# ---------- IM-020 双向同意 ----------
def test_im020_a_friend_request_does_not_make_you_friends(client):
    """发了请求 ≠ 成为好友。这条是整个反骚扰设计的支点。"""
    a = register(client, "13977700001", "甲")
    b = register(client, "13977700002", "乙")
    r = friend_request(client, a, b["id"])
    assert r.status_code == 201 and r.json()["status"] == "pending"

    assert client.get("/api/v1/friends", headers=auth(a)).json() == []
    assert client.get("/api/v1/friends", headers=auth(b)).json() == []

    pending = client.get("/api/v1/friends/requests", headers=auth(b)).json()
    assert [p["from_user_id"] for p in pending] == [a["id"]]

    assert decide(client, b, r.json()["id"], True).status_code == 200
    assert [f["user_id"] for f in client.get("/api/v1/friends", headers=auth(a)).json()] == [b["id"]]
    assert [f["user_id"] for f in client.get("/api/v1/friends", headers=auth(b)).json()] == [a["id"]]


def test_im020_only_the_addressee_can_decide(client):
    a = register(client, "13977700003", "甲")
    b = register(client, "13977700004", "乙")
    c = register(client, "13977700005", "路人")
    rid = friend_request(client, a, b["id"]).json()["id"]
    assert decide(client, a, rid, True).status_code == 403   # 自己批自己
    assert decide(client, c, rid, True).status_code == 403


def test_im020_blocking_beats_friend_request(client):
    """ACC-033 拉黑优先——否则拉黑就成了一个可以被绕过的摆设。"""
    a = register(client, "13977700006", "甲")
    b = register(client, "13977700007", "乙")
    assert client.post(f"/api/v1/users/{a['id']}/block", headers=auth(b)).status_code in (200, 201)
    r = friend_request(client, a, b["id"])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "blocked"


def test_im020_mutual_requests_become_friends_instead_of_deadlocking(client):
    """两个人各发一次请求，不能变成互相等待——谁都点不到「接受」。"""
    a = register(client, "13977700008", "甲")
    b = register(client, "13977700009", "乙")
    friend_request(client, a, b["id"])
    r = friend_request(client, b, a["id"])
    assert r.status_code == 201 and r.json()["status"] == "accepted", r.text


def test_cannot_friend_yourself(client):
    a = register(client, "13977700010", "自己")
    assert friend_request(client, a, a["id"]).status_code == 400


# ---------- IM-021 备注各看各的 ----------
def test_im021_remarks_are_per_side(client):
    a = register(client, "13977700011", "甲")
    b = register(client, "13977700012", "乙")
    rid = friend_request(client, a, b["id"]).json()["id"]
    decide(client, b, rid, True)

    client.patch(f"/api/v1/friends/{b['id']}", json={"remark": "水电王师傅"}, headers=auth(a))
    client.patch(f"/api/v1/friends/{a['id']}", json={"remark": "小区张阿姨"}, headers=auth(b))

    assert client.get("/api/v1/friends", headers=auth(a)).json()[0]["remark"] == "水电王师傅"
    assert client.get("/api/v1/friends", headers=auth(b)).json()[0]["remark"] == "小区张阿姨"


# ---------- IM-022 合作过的人是查出来的 ----------
def test_im022_worked_with_is_derived_not_stored(client, requester, worker):
    """存一张「合作过」表就要在每次闭环/取消/注销时同步维护，漏一处就永远错着。"""
    assert client.get("/api/v1/friends/worked-with", headers=auth(requester)).json() == []
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    got = client.get("/api/v1/friends/worked-with", headers=auth(requester)).json()
    assert [g["user_id"] for g in got] == [worker["id"]]
    assert got[0]["times"] == 1
    # 对方那边同样看得到
    assert [g["user_id"] for g in
            client.get("/api/v1/friends/worked-with", headers=auth(worker)).json()] == [requester["id"]]


# ---------- IM-003 群聊 ----------
def test_im003_group_create_invite_and_post(client):
    a = register(client, "13977700020", "群主")
    b = register(client, "13977700021", "成员")
    c = register(client, "13977700022", "后来的")
    g = client.post("/api/v1/conversations/groups",
                    json={"name": "保洁师傅圈", "member_ids": [b["id"]]}, headers=auth(a))
    assert g.status_code == 201, g.text
    gid = g.json()["id"]

    # 成员能发言
    assert client.post(f"/api/v1/conversations/{gid}/messages",
                       json={"content": "大家好"}, headers=auth(b)).status_code == 201
    # 非成员发不了——群成员资格就是 participants，发消息鉴权自动覆盖
    assert client.post(f"/api/v1/conversations/{gid}/messages",
                       json={"content": "我混进来了"}, headers=auth(c)).status_code in (403, 404)

    client.post(f"/api/v1/conversations/{gid}/members",
                json={"user_ids": [c["id"]]}, headers=auth(b))
    assert client.post(f"/api/v1/conversations/{gid}/messages",
                       json={"content": "现在可以了"}, headers=auth(c)).status_code == 201


def test_im003_member_limit_is_configurable(client, monkeypatch):
    """原始 spec 写的是「上限可配」——写死数字意味着不同规模只能改代码。"""
    monkeypatch.setattr(settings, "GROUP_MEMBER_LIMIT", 2)
    a = register(client, "13977700023", "群主")
    b = register(client, "13977700024", "二号")
    c = register(client, "13977700025", "三号")
    r = client.post("/api/v1/conversations/groups",
                    json={"name": "小群", "member_ids": [b["id"], c["id"]]}, headers=auth(a))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "group_too_large"


def test_im003_only_owner_removes_members_and_cannot_remove_self(client):
    a = register(client, "13977700026", "群主")
    b = register(client, "13977700027", "成员")
    gid = client.post("/api/v1/conversations/groups",
                      json={"name": "群", "member_ids": [b["id"]]}, headers=auth(a)).json()["id"]

    assert client.delete(f"/api/v1/conversations/{gid}/members/{a['id']}",
                         headers=auth(b)).status_code == 403     # 非群主
    r = client.delete(f"/api/v1/conversations/{gid}/members/{a['id']}", headers=auth(a))
    assert r.status_code == 400, "群主把自己移出会让群主位空悬"
    assert client.delete(f"/api/v1/conversations/{gid}/members/{b['id']}",
                         headers=auth(a)).status_code == 200


def test_im003_owner_cannot_mute_themselves_out_of_their_own_group(client):
    a = register(client, "13977700028", "群主")
    gid = client.post("/api/v1/conversations/groups",
                      json={"name": "群", "member_ids": []}, headers=auth(a)).json()["id"]
    r = client.patch(f"/api/v1/conversations/{gid}",
                     json={"announcement": "群规：禁止站外交易", "muted": [a["id"]]},
                     headers=auth(a))
    assert r.status_code == 200
    assert r.json()["muted"] == []
    assert r.json()["announcement"] == "群规：禁止站外交易"


def test_im003_muting_actually_stops_the_message(client):
    """只把名单存进 muted 而不在发消息处读它，就是「建好了没接上」——
    群主以为禁言了，被禁言的人照发不误。"""
    a = register(client, "13977700030", "群主")
    b = register(client, "13977700031", "话多的人")
    gid = client.post("/api/v1/conversations/groups",
                      json={"name": "群", "member_ids": [b["id"]]}, headers=auth(a)).json()["id"]
    assert client.post(f"/api/v1/conversations/{gid}/messages",
                       json={"content": "禁言前"}, headers=auth(b)).status_code == 201

    client.patch(f"/api/v1/conversations/{gid}", json={"muted": [b["id"]]}, headers=auth(a))
    r = client.post(f"/api/v1/conversations/{gid}/messages",
                    json={"content": "禁言后"}, headers=auth(b))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "muted_in_group"

    # 解除后恢复
    client.patch(f"/api/v1/conversations/{gid}", json={"muted": []}, headers=auth(a))
    assert client.post(f"/api/v1/conversations/{gid}/messages",
                       json={"content": "解除后"}, headers=auth(b)).status_code == 201
