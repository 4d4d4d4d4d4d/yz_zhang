"""VER-050 发单人点名一位核验人（372 号 spec，V399）。

原来核验单只有平台派：谁有资格谁来接。行业项目里发单人往往有自己信得过的懂行的人。
现在发单人可以点名：只有被点名的人能接；核验费由发单人付；被点名的人免「本类目完成记录」（发单人替他担保），
其余资格（不是 AI、实名、没被封、不是当事人、不是付费方、信用分）一条不少。
"""
from app.modules.notification.models import Notification
from app.core.db import SessionLocal
from tests.conftest import auth, make_admin, register, verify_user
from tests.test_client_shape_alignment import _assert_shape
from tests.test_verification_escalation import escalated_task, make_verifier, runner  # noqa: F401

API = "/api/v1"


def _wallet(client, user):
    return client.get(f"{API}/wallet", headers=auth(user)).json()["available_cents"]


def test_designated_verifier_is_the_only_one_who_can_claim(client, requester, runner):  # noqa: F811
    admin = make_admin(client, "13800039901")
    task, agent_id = escalated_task(client, requester, admin, runner)
    friend = register(client, "13800039902", "老周")
    verify_user(client, friend, name="周工")                 # 实名，但在这个类目没有完成记录
    other = make_verifier(client, "13800039903")             # 平台派单下有资格的人
    before = _wallet(client, requester)
    r = client.post(f"{API}/tasks/{task['id']}/verification", json={"verifier_id": friend["id"]}, headers=auth(requester))
    assert r.status_code == 201, r.text
    order = r.json()
    _assert_shape(order, "VerificationOrderView")
    # 点名了就由发单人付，升级的单也一样（平台付费的单不能由发单人点熟人来领）
    assert order["trigger"] == "designated" and order["payer_id"] == requester["id"]
    assert order["designated_verifier_id"] == friend["id"]
    assert before - _wallet(client, requester) == order["fee_cents"]
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.user_id == friend["id"], Notification.title == "有人点名请你核验").count() == 1
    # 别人：列表里看不到，硬接 403
    assert all(o["id"] != order["id"] for o in client.get(f"{API}/verification-orders", headers=auth(other)).json())
    no = client.post(f"{API}/verification-orders/{order['id']}/claim", headers=auth(other))
    assert no.status_code == 403 and no.json()["detail"]["code"] == "verifier_not_designated"
    # 被点名的人：列表里看得到、能接（免类目完成记录）
    mine = [o for o in client.get(f"{API}/verification-orders", headers=auth(friend)).json() if o["id"] == order["id"]]
    assert mine and mine[0]["claimable"] is True, mine
    ok = client.post(f"{API}/verification-orders/{order['id']}/claim", headers=auth(friend))
    assert ok.status_code == 200 and ok.json()["verifier_id"] == friend["id"], ok.text


def test_designation_keeps_every_other_safety_check(client, requester, runner):  # noqa: F811
    admin = make_admin(client, "13800039904")
    task, agent_id = escalated_task(client, requester, admin, runner)
    url = f"{API}/tasks/{task['id']}/verification"
    unverified = register(client, "13800039905", "没实名")
    for target, why in ((unverified["id"], "实名"), (requester["id"], "当事人"), (agent_id, "AI")):
        r = client.post(url, json={"verifier_id": target}, headers=auth(requester))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "verifier_not_eligible", (why, r.text)
        assert why in r.json()["detail"]["message"] or why == "当事人" and "当事人" in r.json()["detail"]["message"], r.text
    missing = client.post(url, json={"verifier_id": 999999}, headers=auth(requester))
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "verifier_not_found"
    assert client.post(url, json={"verifier_id": 0}, headers=auth(requester)).status_code == 422
    assert client.post(url, json={"verifier_id": 5, "x": 1}, headers=auth(requester)).status_code == 422
    # 没点名的照旧：升级的单平台付、平台派
    plain = client.post(url, headers=auth(requester))
    assert plain.status_code == 201 and plain.json()["trigger"] == "escalation" and plain.json()["designated_verifier_id"] is None


def test_the_single_eligibility_function_also_knows_about_designation(client, requester, runner):  # noqa: F811
    """接单端点与可接列表读同一个 `verifier_block`：别的地方再调它（比如以后的自动派单），点名也不能被绕过。"""
    from app.modules.account.models import User
    from app.modules.task.models import Task
    from app.modules.verify import service
    from app.modules.verify.models import VerificationOrder

    admin = make_admin(client, "13800039906")
    task, _ = escalated_task(client, requester, admin, runner)
    friend = register(client, "13800039907", "老吴")
    verify_user(client, friend, name="吴工")
    other = make_verifier(client, "13800039908")
    oid = client.post(f"{API}/tasks/{task['id']}/verification", json={"verifier_id": friend["id"]}, headers=auth(requester)).json()["id"]
    with SessionLocal() as db:
        order, t = db.get(VerificationOrder, oid), db.get(Task, task["id"])
        assert service.verifier_block(db, t, order, db.get(User, other["id"])) == "发单人点名了别的核验人"
        assert service.verifier_block(db, t, order, db.get(User, friend["id"])) == ""
