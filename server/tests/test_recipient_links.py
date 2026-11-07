"""SCN-122 服务对象自己看进度：替别人发单时的免登录只读链接（356 号 spec，V383）。

子女替爸妈发单后，爸妈最常问「人几点来、来了没有」。发单人生成一条链接发给服务对象，对方不用登录就能看；
令牌只返回一次、只存哈希、一单同时一条、到期失效、可作废；页面不给电话、地址、价钱、照片与位置。
"""
import sqlalchemy as sa

from app.core import ratelimit
from app.core.db import SessionLocal, engine
from app.modules.task import recipient_links
from app.modules.task.models import RecipientLink
from tests.conftest import JOB_HEADERS, auth, register, topup, verify_user
from tests.test_on_behalf import ON_BEHALF, _post
from tests.test_task_flow import match_and_fund

API = "/api/v1"
FORBIDDEN_KEYS = {"onsite_contact", "address_exact", "address_hint", "budget_cents", "lat", "lng", "phone", "images",
                  "description", "contract_id", "executor_id", "creator_id"}


def _link(client, u, task_id, **body):
    return client.post(f"{API}/tasks/{task_id}/recipient-link", json=body or None, headers=auth(u))


def _view(client, token):
    return client.get(f"{API}/recipient-progress/{token}")


def _keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | set().union(*(_keys(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(_keys(v) for v in obj)) if obj else set()
    return set()


def test_recipient_sees_who_is_coming_without_logging_in_and_nothing_private(client, requester, worker):
    topup(client, requester, 40000)
    t = _post(client, requester, **ON_BEHALF).json()
    r = _link(client, requester, t["id"])
    assert r.status_code == 201, r.text
    link = r.json()
    assert link["state"] == "active" and link["path"] == f"/r/{link['token']}" and len(link["token"]) >= 32
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(link, "RecipientLinkCreated")
    with SessionLocal() as db:
        row = db.query(RecipientLink).filter(RecipientLink.task_id == t["id"]).one()
        assert row.token_hash != link["token"] and link["token"] not in row.token_hash, "库里只存哈希"
    before = _view(client, link["token"])
    assert before.status_code == 200, before.text
    v = before.json()
    assert v["recipient_label"] == "我妈" and v["phase"] == "waiting" and v["helpers"] == []
    assert "找人" in v["phase_text"]
    match_and_fund(client, requester, worker, t)
    v = _view(client, link["token"]).json()
    assert v["phase"] in ("assigned", "working") and len(v["helpers"]) == 1
    assert v["helpers"][0]["name"] and "verified" in v["helpers"][0]
    assert not (_keys(v) & FORBIDDEN_KEYS), _keys(v) & FORBIDDEN_KEYS
    assert "13900001111" not in str(v) and "王阿姨" not in str(v), "到场联系方式不给链接页"
    # 发单人看得到被打开过几次
    s = client.get(f"{API}/tasks/{t['id']}/recipient-link", headers=auth(requester)).json()
    assert s["state"] == "active" and s["view_count"] == 2 and s["last_viewed_at"] and "token" not in s
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(s, "RecipientLinkStatus")
    _assert_shape(v, "RecipientProgress")


def test_arrivals_and_visit_reports_show_up(client, requester, worker):
    topup(client, requester, 40000)
    t = _post(client, requester, visits_planned=2, **ON_BEHALF).json()
    token = _link(client, requester, t["id"]).json()["token"]
    match_and_fund(client, requester, worker, t)
    with SessionLocal() as db:
        from app.modules.task.models import Task

        task = db.get(Task, t["id"])
        assert task.status == "in_progress", task.status
    r = client.post(f"{API}/tasks/{t['id']}/visits", json={"note": "第一次"}, headers=auth(worker))
    assert r.status_code == 201, r.text
    v = _view(client, token).json()
    assert v["phase"] == "working" and v["visits_planned"] == 2 and v["visits_reported"] == 1 and v["last_arrival_at"]
    # 别人（发单人自己写的进度、不是接单人）不算到达
    with SessionLocal() as db:
        from app.modules.task.models import ProgressLog

        db.add(ProgressLog(task_id=t["id"], user_id=requester["id"], kind="visit"))
        db.commit()
    assert _view(client, token).json()["visits_reported"] == 1


def test_only_the_poster_of_an_on_behalf_open_task_can_make_one(client, requester, worker):
    plain = _post(client, requester).json()
    r = _link(client, requester, plain["id"])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "recipient_link_not_on_behalf"
    t = _post(client, requester, **ON_BEHALF).json()
    for method in ("post", "get", "delete"):
        r = getattr(client, method)(f"{API}/tasks/{t['id']}/recipient-link", headers=auth(worker))
        assert r.status_code == 403 and r.json()["detail"]["code"] == "recipient_link_not_owner", (method, r.text)
    assert client.post(f"{API}/tasks/{t['id']}/cancel", headers=auth(requester)).status_code == 200
    r = _link(client, requester, t["id"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "recipient_link_task_closed"
    assert client.get(f"{API}/tasks/999999/recipient-link", headers=auth(requester)).status_code == 404


def test_regenerating_revokes_the_old_link_and_revoke_closes_it(client, requester):
    t = _post(client, requester, **ON_BEHALF).json()
    old = _link(client, requester, t["id"]).json()["token"]
    new = _link(client, requester, t["id"]).json()["token"]
    assert old != new
    r = _view(client, old)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "recipient_link_invalid"
    assert _view(client, new).status_code == 200
    d = client.delete(f"{API}/tasks/{t['id']}/recipient-link", headers=auth(requester)).json()
    assert d["revoked"] == 1 and d["state"] == "revoked"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(d, "RecipientLinkRevoked")
    assert _view(client, new).json()["detail"]["code"] == "recipient_link_invalid"
    assert _view(client, "not-a-real-token").json()["detail"]["code"] == "recipient_link_invalid"


def test_links_expire(client, requester):
    t = _post(client, requester, **ON_BEHALF).json()
    link = _link(client, requester, t["id"], days=1).json()
    assert _view(client, link["token"]).status_code == 200
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE recipient_links SET expires_at = datetime('now', '-1 minutes') WHERE task_id = :id"),
                     {"id": t["id"]})
    r = _view(client, link["token"])
    assert r.status_code == 404 and r.json()["detail"]["code"] == "recipient_link_expired"
    assert "过期" in r.json()["detail"]["message"]
    assert client.get(f"{API}/tasks/{t['id']}/recipient-link", headers=auth(requester)).json()["state"] == "expired"
    too_long = _link(client, requester, t["id"], days=recipient_links.MAX_DAYS + 1)
    assert too_long.status_code == 422


def test_views_are_rate_limited_per_visitor(client, requester, monkeypatch):
    monkeypatch.setattr(recipient_links, "VIEWS_PER_MINUTE", 2)
    ratelimit.reset()
    t = _post(client, requester, **ON_BEHALF).json()
    token = _link(client, requester, t["id"]).json()["token"]
    assert _view(client, token).status_code == 200 and _view(client, token).status_code == 200
    r = _view(client, token)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "rate_limited"
    ratelimit.reset()


def test_slots_of_a_multi_person_order_show_each_helper(client, requester):
    t = _post(client, requester, people_needed=2, **ON_BEHALF).json()
    token = _link(client, requester, t["id"]).json()["token"]
    v = _view(client, token).json()
    assert v["phase"] == "waiting" and v["helpers"] == []
    from app.modules.task.models import Task

    slots = [Task(status="matched"), Task(status="completed")]
    assert recipient_links._phase(Task(status="published"), slots) == "assigned"
    assert recipient_links._phase(Task(status="published"), [Task(status="completed"), Task(status="cancelled")]) == "done"
    assert recipient_links._phase(Task(status="published"), [Task(status="cancelled")]) == "cancelled"
    assert recipient_links._phase(Task(status="published"), [Task(status="in_progress"), Task(status="published")]) == "working"
    assert recipient_links._phase(Task(status="published"), [Task(status="published")]) == "waiting"


def test_export_deletion_and_purge(client):
    me = register(client, "13800003831", "女儿")
    verify_user(client, me, "张三")
    t = _post(client, me, **ON_BEHALF).json()
    token = _link(client, me, t["id"]).json()["token"]
    out = client.get(f"{API}/users/me/export", headers=auth(me)).json()
    assert out["recipient_links"][0]["state"] == "active" and token not in str(out), "导出不带令牌"
    # 过期满 30 天的记录被定时任务删掉
    other = _post(client, me, **ON_BEHALF).json()
    _link(client, me, other["id"])
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE recipient_links SET expires_at = datetime('now', '-31 days') WHERE task_id = :id"),
                     {"id": other["id"]})
    r = client.post(f"{API}/tasks/jobs/purge-locations", headers=JOB_HEADERS).json()
    assert r["purged_recipient_links"] == 1
    assert _view(client, token).status_code == 200, "没过期的不删"
    client.post(f"{API}/tasks/{t['id']}/cancel", headers=auth(me))
    client.post(f"{API}/tasks/{other['id']}/cancel", headers=auth(me))
    assert client.post(f"{API}/users/me/deactivate", headers=auth(me)).status_code == 200
    with SessionLocal() as db:
        assert db.query(RecipientLink).filter(RecipientLink.created_by.isnot(None), RecipientLink.task_id == t["id"]).count() == 0
    assert _view(client, token).status_code == 404, "注销后链接立刻打不开"
