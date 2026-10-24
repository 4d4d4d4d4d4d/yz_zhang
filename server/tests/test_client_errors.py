"""APP-094 页面渲染出错的上报（184 号 spec，V212）。

两端的错误边界（183 号）接住一页 / 一屏的渲染错误后报一条：只有平台、页面、错误类型。运营在后台看哪一页常坏。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.analytics import service
from app.modules.analytics.models import AnalyticsEvent
from tests.conftest import auth, make_admin

API = "/api/v1"


def _report(client, headers=None, **kw):
    body = {"platform": "web", "page": "/wallet", "kind": "TypeError", **kw}
    return client.post(f"{API}/client-errors", json=body, headers=headers or {})


def test_reports_are_aggregated_for_ops_with_people_counted_once(client, requester, worker):
    assert _report(client, auth(requester)).json() == {"ok": True, "recorded": True}
    assert _report(client, auth(requester)).json()["recorded"] is False, "同一人同一页同类错误一分钟内只记一次"
    assert _report(client, auth(worker)).json()["recorded"] is True
    assert _report(client).json()["recorded"] is True, "没登录也收（登录页也可能坏）"
    _report(client, auth(worker), platform="app", page="tab-cooperate", kind="RangeError")
    with SessionLocal() as db:   # 一分钟后同一个人又坏了一次：次数加一，人数不加
        for row in db.query(AnalyticsEvent).filter(AnalyticsEvent.name.like("render_failed:%")):
            row.created_at = utcnow() - timedelta(minutes=2)
        db.commit()
    assert _report(client, auth(requester)).json()["recorded"] is True
    ops = make_admin(client, "13900030001", "运营")
    rows = client.get(f"{API}/admin/client-errors", headers=auth(ops)).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(rows[0], "ClientErrorRow")
    assert rows[0] == {**rows[0], "platform": "web", "page": "/wallet", "kind": "TypeError", "count": 4, "people": 2}
    assert {(r["platform"], r["page"], r["kind"]) for r in rows} == {("web", "/wallet", "TypeError"), ("app", "tab-cooperate", "RangeError")}


def test_nothing_but_platform_page_and_kind_is_kept(client, requester):
    r = _report(client, auth(requester), page="/people/13800000001", kind="TypeError: x.map of 13800000001")
    assert r.status_code == 201
    with SessionLocal() as db:
        row = db.query(AnalyticsEvent).filter(AnalyticsEvent.name.like("render_failed:%")).one()
        assert (row.name, row.ref_type) == ("render_failed:web:Error", "/people/:id"), "数字换成 :id；不像错误类型的归成 Error，不存原文"
    _report(client, auth(requester), page="<script>alert(1)</script>")
    with SessionLocal() as db:
        assert db.query(AnalyticsEvent).filter(AnalyticsEvent.ref_type == "other").count() == 1, "不像页面名的归成 other"
    assert _report(client, auth(requester), platform="ios").status_code == 422
    assert _report(client, auth(requester), message="secret").status_code == 422, "不收错误内容"


def test_anonymous_reports_are_capped_per_minute(client, monkeypatch):
    monkeypatch.setattr(service, "RENDER_ANON_PER_MINUTE", 2)
    got = [_report(client, page=f"/p{c}").json()["recorded"] for c in "abcd"]
    assert got == [True, True, False, False]
    with SessionLocal() as db:   # 一分钟前的不算
        for row in db.query(AnalyticsEvent).filter(AnalyticsEvent.name.like("render_failed:%")):
            row.created_at = utcnow() - timedelta(minutes=2)
        db.commit()
    assert _report(client, page="/pz").json()["recorded"] is True


def test_only_ops_sees_the_summary_and_old_reports_drop_off(client, requester):
    _report(client, auth(requester))
    assert client.get(f"{API}/admin/client-errors", headers=auth(requester)).status_code == 403
    with SessionLocal() as db:
        for row in db.query(AnalyticsEvent).filter(AnalyticsEvent.name.like("render_failed:%")):
            row.created_at = utcnow() - timedelta(days=8)
        db.commit()
    ops = make_admin(client, "13900030002", "运营")
    assert client.get(f"{API}/admin/client-errors", headers=auth(ops)).json() == []
    assert len(client.get(f"{API}/admin/client-errors?days=30", headers=auth(ops)).json()) == 1
