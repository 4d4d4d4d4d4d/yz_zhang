"""XAPP 跨 App 助手平台侧（161 号 spec）。

执行器（这里用测试充当模拟执行器）按协议拿下一步、回报结果；平台守住：授权白名单、红线步交还给人、
逐步确认、叫停、失败两次交还、云端看屏幕默认关闭、结果脱敏、撤销即停、记录进导出与注销处置。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.xapp.models import XappGrant, XappRun, XappStep
from tests.conftest import auth, register

API = "/api/v1/xapp"
MAP, CHAT = "com.autonavi.minimap", "com.tencent.mm"


def _grant(client, u, apps=(MAP,), actions=("open", "fill", "tap", "read"), **kw):
    r = client.post(f"{API}/grants", json={"apps": list(apps), "actions": list(actions), "days": 7, **kw}, headers=auth(u))
    assert r.status_code == 201, r.text
    return r.json()


def _step(app=MAP, action="open", intent="打开地图", channel="deeplink", **kw):
    return {"app": app, "action": action, "intent": intent, "channel": channel, **kw}


def _run(client, u, grant_id, steps, mode="red_only"):
    r = client.post(f"{API}/runs", json={"grant_id": grant_id, "goal": "查去客户家的路线并告诉客户", "executor": "mock",
                                         "confirm_mode": mode, "steps": steps}, headers=auth(u))
    return r


def _next(client, u, run_id):
    return client.post(f"{API}/runs/{run_id}/next", headers=auth(u)).json()


def _result(client, u, run_id, step_id, ok=True, summary="完成"):
    return client.post(f"{API}/runs/{run_id}/steps/{step_id}/result", json={"ok": ok, "summary": summary}, headers=auth(u))


def test_grant_rejects_red_line_actions_and_bad_apps(client, requester):
    r = client.post(f"{API}/grants", json={"apps": [MAP], "actions": ["open", "pay"], "days": 7}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "xapp_red_line_not_grantable"
    assert "付款" in r.json()["detail"]["message"]
    bad = client.post(f"{API}/grants", json={"apps": ["地图 App"], "actions": ["open"], "days": 7}, headers=auth(requester))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "xapp_bad_app"
    days = client.post(f"{API}/grants", json={"apps": [MAP], "actions": ["open"], "days": 365}, headers=auth(requester))
    assert days.status_code == 400 and days.json()["detail"]["code"] == "xapp_bad_days"
    cat = client.get(f"{API}/catalog").json()
    assert {x["key"] for x in cat["red_line"]} >= {"pay", "sign", "publish", "send_message"}
    assert cat["channels"] == ["api", "deeplink", "a11y", "vision"]


def test_plan_must_stay_inside_the_grant(client, requester):
    g = _grant(client, requester)
    r = _run(client, requester, g["id"], [_step(app=CHAT)])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "xapp_app_not_granted"
    r = _run(client, requester, g["id"], [_step(action="navigate")])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "xapp_action_not_granted"
    r = _run(client, requester, g["id"], [_step(channel="vision", vision_where="cloud")])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "xapp_cloud_vision_off", "云端看屏幕默认关闭"
    ok = _run(client, requester, g["id"], [_step(channel="vision", vision_where="device")])
    assert ok.status_code == 201
    other = register(client, "13800340001", "别人")
    assert _run(client, other, g["id"], [_step()]).status_code == 404


def test_executor_walks_the_plan_and_red_line_steps_go_back_to_the_person(client, requester):
    g = _grant(client, requester, apps=(MAP, CHAT))
    r = _run(client, requester, g["id"], [
        _step(intent="打开地图搜索客户地址"),
        _step(action="read", intent="读出驾车时间", channel="a11y"),
        _step(app=CHAT, action="send_message", intent="把预计到达时间发给客户", channel="a11y"),
    ])
    assert r.status_code == 201, r.text
    run = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(run, "XappRunDetail")
    s1, s2, s3 = run["steps"]
    assert s3["red_line"] and s3["needs_confirm"] and not s1["needs_confirm"]
    n = _next(client, requester, run["id"])
    assert n["state"] == "execute" and n["step"]["id"] == s1["id"]
    _result(client, requester, run["id"], s1["id"])
    n = _next(client, requester, run["id"])
    assert n["state"] == "execute" and n["step"]["id"] == s2["id"]
    _result(client, requester, run["id"], s2["id"], summary="驾车约 25 分钟")
    n = _next(client, requester, run["id"])
    assert n["state"] == "awaiting_confirm" and n["step"]["id"] == s3["id"], "红线步不确认就不往下走"
    c = client.post(f"{API}/runs/{run['id']}/steps/{s3['id']}/confirm", headers=auth(requester)).json()
    assert c["step"]["status"] == "done_by_user" and c["run_status"] == "done", "红线步由本人亲手做完"
    assert _next(client, requester, run["id"])["state"] == "done"
    with SessionLocal() as db:
        assert db.get(XappStep, s3["id"]).attempts == 0, "执行器从没碰过红线步"


def test_red_line_step_after_confirm_is_a_handoff_not_an_execution(client, requester):
    """先确认、再轮到它：执行器拿到的是 handoff（带人到页面），不是 execute。"""
    g = _grant(client, requester, apps=(CHAT,))
    run = _run(client, requester, g["id"], [_step(app=CHAT, action="pay", intent="付车费", channel="a11y")]).json()
    sid = run["steps"][0]["id"]
    with SessionLocal() as db:
        db.get(XappStep, sid).confirmed_at = utcnow()
        db.commit()
    n = _next(client, requester, run["id"])
    assert n["state"] == "handoff" and n["step"]["action_label"] == "付款"
    r = _result(client, requester, run["id"], sid)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "xapp_step_not_dispatched", "执行器不能替人报完成"


def test_each_mode_waits_for_every_step(client, requester):
    g = _grant(client, requester)
    run = _run(client, requester, g["id"], [_step(), _step(action="tap", intent="点开路线", channel="a11y")], mode="each").json()
    n = _next(client, requester, run["id"])
    assert n["state"] == "awaiting_confirm"
    client.post(f"{API}/runs/{run['id']}/steps/{run['steps'][0]['id']}/confirm", headers=auth(requester))
    assert _next(client, requester, run["id"])["state"] == "execute"


def test_two_failures_hand_the_run_back_and_results_are_scrubbed(client, requester):
    g = _grant(client, requester)
    run = _run(client, requester, g["id"], [_step(action="tap", intent="点「开始导航」", channel="a11y")]).json()
    sid = run["steps"][0]["id"]
    _next(client, requester, run["id"])
    r = _result(client, requester, run["id"], sid, ok=False, summary="找不到按钮，验证码 482913，手机 13812345678")
    assert r.json()["run_status"] == "running"
    # 当场就脱敏（不能等下一次回报把它盖掉才算没泄露）：手机号与长串数字打码
    kept = r.json()["step"]["result"]
    assert "482913" not in kept and "13812345678" not in kept and "138****5678" in kept, kept
    with SessionLocal() as db:
        assert "482913" not in db.get(XappStep, sid).result, "库里存的也必须是脱敏后的"
    _next(client, requester, run["id"])
    r = _result(client, requester, run["id"], sid, ok=False, summary="还是找不到按钮").json()
    assert r["run_status"] == "needs_human" and r["step"]["status"] == "failed", "失败两次交还给人，不盲点"
    assert _next(client, requester, run["id"])["state"] == "needs_human"
    with SessionLocal() as db:
        detail = db.get(XappRun, run["id"]).stop_reason
        assert "第 1 步连续失败" in detail
    first = client.get(f"{API}/runs/{run['id']}", headers=auth(requester)).json()
    assert "482913" not in str(first) and "13812345678" not in str(first)


def test_stop_and_revoke_stop_everything(client, requester):
    g = _grant(client, requester)
    run = _run(client, requester, g["id"], [_step(), _step(action="read", intent="读", channel="a11y")]).json()
    s = client.post(f"{API}/runs/{run['id']}/stop", json={"reason": "我自己来"}, headers=auth(requester)).json()
    assert s["status"] == "stopped" and s["stop_reason"] == "我自己来"
    assert _next(client, requester, run["id"])["state"] == "stopped", "叫停后不再派发"
    run2 = _run(client, requester, g["id"], [_step()]).json()
    rv = client.delete(f"{API}/grants/{g['id']}", headers=auth(requester)).json()
    assert rv["runs_stopped"] == 1 and rv["active"] is False
    # 撤销当场就停（不是等执行器下次来拿才发现）：查记录就已经是「已叫停 · 授权已撤销」
    now = client.get(f"{API}/runs/{run2['id']}", headers=auth(requester)).json()
    assert now["status"] == "stopped" and now["stop_reason"] == "授权已撤销", now
    assert _next(client, requester, run2["id"])["state"] == "stopped"
    again = _run(client, requester, g["id"], [_step()])
    assert again.status_code == 409 and again.json()["detail"]["code"] == "xapp_grant_inactive"


def test_expired_grant_stops_the_run_at_the_next_step(client, requester):
    g = _grant(client, requester)
    run = _run(client, requester, g["id"], [_step()]).json()
    with SessionLocal() as db:
        db.get(XappGrant, g["id"]).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert _next(client, requester, run["id"])["state"] == "stopped"


def test_limits(client, requester, monkeypatch):
    from app.core.config import settings

    g = _grant(client, requester)
    monkeypatch.setattr(settings, "XAPP_MAX_STEPS", 2)
    r = _run(client, requester, g["id"], [_step()] * 3)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "xapp_too_many_steps"
    monkeypatch.setattr(settings, "XAPP_DAILY_RUNS", 1)
    assert _run(client, requester, g["id"], [_step()]).status_code == 201
    r = _run(client, requester, g["id"], [_step()])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "xapp_daily_limit"


def test_records_are_in_export_and_erased_on_deletion(client, requester):
    from app.modules.account.deletion import erase_personal_data

    g = _grant(client, requester)
    _run(client, requester, g["id"], [_step()])
    out = client.get("/api/v1/users/me/export", headers=auth(requester)).json()
    assert out["xapp"]["grants"][0]["apps"] == [MAP] and out["xapp"]["runs"][0]["steps"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(client.get(f"{API}/grants", headers=auth(requester)).json()[0], "XappGrant")
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, requester["id"]))
        db.commit()
        assert db.query(XappGrant).count() == 0 and db.query(XappRun).count() == 0 and db.query(XappStep).count() == 0


def test_every_xapp_response_matches_the_sdk_types(client, requester):
    """CLI-083：每个跨 App 助手接口的真实响应都对得上共享 SDK 的类型。"""
    from tests.test_client_shape_alignment import _assert_shape

    catalog = client.get(f"{API}/catalog").json()
    _assert_shape(catalog, "XappCatalog")
    g = _grant(client, requester)
    _assert_shape(g, "XappGrant")
    listed = client.get(f"{API}/grants", headers=auth(requester)).json()[0]
    _assert_shape(listed, "XappGrant")
    run = _run(client, requester, g["id"], [_step(), _step(app=MAP, action="publish", intent="发一条动态", channel="a11y")]).json()
    runs = client.get(f"{API}/runs", headers=auth(requester)).json()[0]
    _assert_shape(runs, "XappRun")
    detail = client.get(f"{API}/runs/{run['id']}", headers=auth(requester)).json()
    _assert_shape(detail, "XappRunDetail")
    n = _next(client, requester, run["id"])
    _assert_shape(n, "XappNext")
    reported = _result(client, requester, run["id"], n["step"]["id"]).json()
    _assert_shape(reported, "XappStepOutcome")
    confirmed = client.post(f"{API}/runs/{run['id']}/steps/{run['steps'][1]['id']}/confirm", headers=auth(requester)).json()
    _assert_shape(confirmed, "XappStepOutcome")
    run2 = _run(client, requester, g["id"], [_step()]).json()
    stopped = client.post(f"{API}/runs/{run2['id']}/stop", json={}, headers=auth(requester)).json()
    _assert_shape(stopped, "XappRun")
    revoked = client.delete(f"{API}/grants/{g['id']}", headers=auth(requester)).json()
    _assert_shape(revoked, "XappGrantRevoked")
