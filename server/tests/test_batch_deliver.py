"""SC-015 执行方一次交付多期（296 号 spec，V323）。

三期连着做完了，此前执行方要点三次「交付本期」，发布方收到三条（或零条）消息。现在一次交付点名的几期：
要么全交、要么一期不动；几期共用一份交付说明；通知发布方一次。逐期交付照旧。
"""
from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from tests.conftest import auth
from tests.test_batch_release import URL as RELEASE, _three_stage

URL = "/api/v1/contracts/{cid}/milestones/deliver-batch"


def test_contractor_delivers_several_stages_at_once_with_one_note(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    r = client.post(URL.format(cid=cid), json={"idxs": [2, 1], "note": "设计稿与施工图都在附件里"}, headers=auth(worker))
    assert r.status_code == 200, r.text
    ms = r.json()["milestones"]
    assert [m["status"] for m in ms] == ["delivered", "delivered", "pending"]
    assert ms[0]["delivery_note"] == ms[1]["delivery_note"] == "设计稿与施工图都在附件里"
    assert "delivery_note" not in ms[2], "没交付的期不出这个字段（与以前一样）"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "Contract")
    with SessionLocal() as db:
        got = [n for n in db.query(Notification).filter(Notification.user_id == requester["id"],
                                                         Notification.title == "执行方交付了几期，等你验收")]
    assert len(got) == 1 and "第 1、2 期" in got[0].body and "¥500.00" in got[0].body and "设计稿" in got[0].body
    ok = client.post(RELEASE.format(cid=cid), json={"idxs": [1, 2], "expected_total_cents": 50000}, headers=auth(requester))
    assert ok.status_code == 200, "交付后可以照旧一次放款"


def test_all_or_nothing_and_only_the_contractor(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    assert client.post(f"/api/v1/contracts/{cid}/milestones/1/deliver", headers=auth(worker)).status_code == 200, "逐期交付照旧"
    r = client.post(URL.format(cid=cid), json={"idxs": [1, 2]}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "invalid_milestone_state"
    assert "第 1 期" in r.json()["detail"]["message"]
    c = client.get(f"/api/v1/contracts/{cid}", headers=auth(worker)).json()
    assert [m["status"] for m in c["milestones"]] == ["delivered", "pending", "pending"], "第 2 期没被顺带交掉"
    dup = client.post(URL.format(cid=cid), json={"idxs": [2, 2]}, headers=auth(worker))
    assert dup.status_code == 400 and dup.json()["detail"]["code"] == "duplicate_milestone"
    nope = client.post(URL.format(cid=cid), json={"idxs": [2, 9]}, headers=auth(worker))
    assert nope.status_code == 400 and nope.json()["detail"]["code"] == "milestone_not_found" and "第 9 期" in nope.json()["detail"]["message"]
    them = client.post(URL.format(cid=cid), json={"idxs": [2, 3]}, headers=auth(requester))
    assert them.status_code == 400 and them.json()["detail"]["code"] == "not_party", "发布方不能替执行方交付"
    assert client.post(URL.format(cid=cid), json={"idxs": []}, headers=auth(worker)).status_code == 422
