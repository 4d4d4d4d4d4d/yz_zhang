"""SCN-156 作品展示授权（278 号 spec，V305）。

整理收纳、装修、设计……接单的人想把做过的单（前后对比照、成品）放进空间当作品，可那是客户家、客户的东西。
现在：发单人在任务详情里授权「允许展示这一单」，接单人才能在空间里关联这一单；撤回后它就不再公开。
"""
from tests.conftest import auth, register, topup
from tests.test_task_flow import match_and_fund, publish_task

API = "/api/v1"


def _done(client, requester, worker):
    topup(client, requester, 50000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    assert client.post(f"{API}/tasks/{task['id']}/deliver", headers=auth(worker)).status_code == 200
    assert client.post(f"{API}/tasks/{task['id']}/accept-delivery", headers=auth(requester)).status_code == 200
    return task["id"]


def _save(client, user, items, published=True):
    rev = client.get(f"{API}/spaces/me", headers=auth(user)).json()["revision"]
    return client.put(f"{API}/spaces/me", json={"revision": rev, "published": published, "headline": "整理收纳",
                                                "items": items}, headers=auth(user))


def test_consent_gates_linking_and_withdrawal_hides_it(client, requester, worker):
    tid = _done(client, requester, worker)
    item = {"title": "衣橱整理前后", "kind": "work", "summary": "两个柜子", "task_id": tid}
    r = _save(client, worker, [item])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "showcase_consent_required"
    assert f"#{tid}" in r.json()["detail"]["message"]
    assert client.post(f"{API}/tasks/{tid}/showcase-consent", headers=auth(worker)).status_code == 403, "接单人不能自己授权"
    g = client.post(f"{API}/tasks/{tid}/showcase-consent", headers=auth(requester))
    assert g.status_code == 200 and g.json()["showcase_consent_at"]
    detail = client.get(f"{API}/tasks/{tid}", headers=auth(worker)).json()
    assert detail["showcase_consent_at"], "成交双方看得到授权"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(detail, "Task")
    outsider = register(client, "13800370002", "外人")
    seen = client.get(f"{API}/tasks/{tid}", headers=auth(outsider))
    assert seen.status_code == 200 and "showcase_consent_at" not in seen.json(), "外人看不到"
    plain = {"title": "没关联任务的作品", "kind": "work"}
    assert _save(client, worker, [item, plain]).status_code == 200
    stored = client.get(f"{API}/spaces/me", headers=auth(worker)).json()["items"]
    assert stored[0]["task_id"] == tid and "task_id" not in stored[1], "没关联的不带 task_id（与以前存的一样）"
    pub = client.get(f"{API}/spaces/{worker['id']}").json()
    assert [i["title"] for i in pub["items"]] == ["衣橱整理前后", "没关联任务的作品"]
    disc = client.get(f"{API}/spaces", params={"q": "整理收纳"}).json()["items"]
    assert [i["title"] for i in next(d for d in disc if d["user_id"] == worker["id"])["preview"]] == ["衣橱整理前后", "没关联任务的作品"]

    assert client.delete(f"{API}/tasks/{tid}/showcase-consent", headers=auth(requester)).json()["showcase_consent_at"] is None
    pub = client.get(f"{API}/spaces/{worker['id']}").json()
    assert [i["title"] for i in pub["items"]] == ["没关联任务的作品"] and pub["items_count"] == 1, "撤回后不再公开"
    disc = client.get(f"{API}/spaces", params={"q": "整理收纳"}).json()["items"]
    assert [i["title"] for i in next(d for d in disc if d["user_id"] == worker["id"])["preview"]] == ["没关联任务的作品"]
    assert len(client.get(f"{API}/spaces/me", headers=auth(worker)).json()["items"]) == 2, "自己的编辑页还在，可以删或等对方重新授权"


def test_only_completed_tasks_and_only_the_executor(client, requester, worker):
    topup(client, requester, 50000)
    open_task = publish_task(client, requester)
    r = client.post(f"{API}/tasks/{open_task['id']}/showcase-consent", headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "showcase_task_not_completed"
    doing = publish_task(client, requester)
    match_and_fund(client, requester, worker, doing)
    r = client.post(f"{API}/tasks/{doing['id']}/showcase-consent", headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "showcase_task_not_completed", "做着的单还不能授权"
    tid = _done(client, requester, worker)
    client.post(f"{API}/tasks/{tid}/showcase-consent", headers=auth(requester))
    other = register(client, "13800370001", "别人")
    r = _save(client, other, [{"title": "冒用别人的单", "kind": "work", "task_id": tid}])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "showcase_consent_required", "不是你接的单不能关联"
