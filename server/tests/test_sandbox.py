"""SBX-100~107 端侧隐私沙箱（128 号 spec）。

用户原话（2026-10-14）：「需要一套本地隐私性沙箱模式，能够在端侧手机上跑量化小模型从而信息不上传云端，
能够完成一些基本 agent 助理的操作。」服务端这边钉住：开关、开着时把原文交给 AI 的接口全部拒绝、
服务端替他跑的 AI 不出网、端侧模型目录四眼上架且必须有 sha256；清单与共享 SDK 双向一致。
"""
import re
from pathlib import Path

import pytest

from app.core.db import SessionLocal
from app.core.sandbox import CLOUD_AI_ROUTES, gateway_for
from app.main import app
from app.modules.account.models import User
from app.modules.decompose import llm
from tests.conftest import auth, make_admin

API = "/api/v1"
CORE = Path(__file__).resolve().parents[2] / "packages" / "core" / "src" / "sandbox.ts"
SHA = "a" * 64


def _on(client, user, enabled=True):
    r = client.put(f"{API}/users/me/sandbox", json={"enabled": enabled}, headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ 开关（SBX-101）
def test_toggle_remembers_since_and_explains(client, worker):
    assert client.get(f"{API}/users/me/sandbox", headers=auth(worker)).json()["enabled"] is False
    on = _on(client, worker)
    assert on["enabled"] is True and on["since"] and on["blocked_endpoints"] == len(CLOUD_AI_ROUTES)
    assert "原文不发到云端" in on["note"]
    assert _on(client, worker)["since"] == on["since"]          # 再开一次不重置起点
    off = _on(client, worker, False)
    assert off == {**off, "enabled": False, "since": None}
    with SessionLocal() as db:
        assert db.get(User, worker["id"]).privacy.get("sandbox") is False


# ------------------------------------------------------------------ 服务端兜底（SBX-103）
def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


@pytest.mark.parametrize("method,path", sorted(CLOUD_AI_ROUTES))
def test_every_cloud_ai_endpoint_refuses_a_sandboxed_user(client, worker, method, path):
    _on(client, worker)
    r = client.request(method, f"{API}{_fill(path)}", json={}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sandbox_cloud_ai_blocked", (path, r.text)


def test_the_same_endpoints_are_not_blocked_when_sandbox_is_off(client, worker):
    for method, path in sorted(CLOUD_AI_ROUTES):
        r = client.request(method, f"{API}{_fill(path)}", json={}, headers=auth(worker))
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else None
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code != "sandbox_cloud_ai_blocked", path


def test_ordinary_endpoints_still_work_in_sandbox(client, worker):
    _on(client, worker)
    assert client.get(f"{API}/users/me", headers=auth(worker)).status_code == 200
    assert client.post(f"{API}/notebook/notes", json={"body": "已脱敏的摘要"}, headers=auth(worker)).status_code == 201
    assert client.get(f"{API}/sandbox/models", headers=auth(worker)).status_code == 200


def test_server_side_ai_for_a_sandboxed_user_never_reaches_the_model(client, worker):
    """例行任务、已经建好的使命这类服务端替他跑的 AI：开着沙箱就只用模板，模型一次都不被调用。"""
    calls = []

    class Spy(llm.TemplateLLM):
        def expand(self, db, ctx):
            calls.append(ctx)
            return super().expand(db, ctx)

        def decompose(self, db, *a):
            calls.append(a)
            return super().decompose(db, *a)

    old = llm.get_gateway()
    llm.set_gateway(Spy())
    try:
        with SessionLocal() as db:
            assert isinstance(gateway_for(db, worker["id"]), Spy)
            db.get(User, worker["id"]).privacy = {"sandbox": True}
            db.commit()
            gw = gateway_for(db, worker["id"])
            assert type(gw) is llm.TemplateLLM
            from app.modules.workbench.models import WbItem
            from app.modules.workbench.service import breakdown

            item = WbItem(owner_id=worker["id"], title="整理报销单据", notes="我的身份证号与发票都在这里")
            db.add(item)
            db.flush()
            out = breakdown(db, item)
            assert out["steps"] and calls == []
    finally:
        llm.set_gateway(old)


# ------------------------------------------------------------------ 清单两端一致（SBX-102）
def test_cloud_ai_list_matches_the_sdk_both_ways():
    src = CORE.read_text(encoding="utf-8")
    block = src[src.index("CLOUD_AI_ENDPOINTS"):src.index("];", src.index("CLOUD_AI_ENDPOINTS"))]
    sdk = set(re.findall(r"\['(POST|GET|PUT|PATCH|DELETE)', '([^']+)'\]", block))
    assert sdk == set(CLOUD_AI_ROUTES), {"只在 SDK": sdk - set(CLOUD_AI_ROUTES), "只在服务端": set(CLOUD_AI_ROUTES) - sdk}


def test_every_listed_route_exists_and_every_ai_route_is_listed():
    paths = {(m.upper(), p[len(API):]) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert set(CLOUD_AI_ROUTES) <= paths, set(CLOUD_AI_ROUTES) - paths
    # 新加的「问 / 拆 / 起草 / 审阅」类接口必须决定进不进清单：名字像 AI 的写操作都要在清单里
    looks_ai = {(m, p) for m, p in paths if m == "POST" and re.search(r"/ask$|/breakdown$|/clarify$|/distill$|extract-todos$|"
                                                                      r"contract-review$|/legal/documents$|/invoke$", p)}
    assert looks_ai <= set(CLOUD_AI_ROUTES), looks_ai - set(CLOUD_AI_ROUTES)


# ------------------------------------------------------------------ 端侧模型目录（SBX-106）
def _model(**kw):
    return {"key": "qwen2.5-1.5b-instruct-q4km", "name": "Qwen2.5 1.5B Instruct", "family": "qwen2.5", "params_b": 1.5,
            "quant": "Q4_K_M", "skills": ["summarize", "todos"], "languages": ["zh", "en"], **kw}


def test_model_catalog_four_eyes_and_complete_before_publish(client, worker):
    a = make_admin(client, "13900000301", "运营甲")
    b = make_admin(client, "13900000302", "运营乙")
    assert client.post(f"{API}/admin/sandbox/models", json=_model(), headers=auth(worker)).status_code == 403
    bad = client.post(f"{API}/admin/sandbox/models", json=_model(skills=["pay"]), headers=auth(a))
    assert bad.json()["detail"]["code"] == "sandbox_model_bad_skill"
    m = client.post(f"{API}/admin/sandbox/models", json=_model(), headers=auth(a)).json()
    assert m["status"] == "draft"
    assert client.post(f"{API}/admin/sandbox/models", json=_model(), headers=auth(a)).json()["detail"]["code"] == "sandbox_model_exists"
    assert client.get(f"{API}/sandbox/models", headers=auth(worker)).json()["items"] == []
    own = client.post(f"{API}/admin/sandbox/models/{m['id']}/publish", headers=auth(a))
    assert own.json()["detail"]["code"] == "sandbox_model_four_eyes"
    thin = client.post(f"{API}/admin/sandbox/models/{m['id']}/publish", headers=auth(b))
    assert thin.json()["detail"]["code"] == "sandbox_model_incomplete" and "sha256" in thin.json()["detail"]["message"]
    full = _model(sha256=SHA.upper(), url="https://example.org/q.gguf", size_mb=1100, license="Apache-2.0", min_ram_gb=4)
    assert client.patch(f"{API}/admin/sandbox/models/{m['id']}", json={**full, "url": "http://example.org/q.gguf"},
                        headers=auth(a)).json()["sha256"] == SHA
    assert "https" in client.post(f"{API}/admin/sandbox/models/{m['id']}/publish", headers=auth(b)).json()["detail"]["message"]
    client.patch(f"{API}/admin/sandbox/models/{m['id']}", json=full, headers=auth(a))
    pub = client.post(f"{API}/admin/sandbox/models/{m['id']}/publish", headers=auth(b)).json()
    assert pub["status"] == "published" and pub["reviewed_by"] == b["id"]
    assert client.patch(f"{API}/admin/sandbox/models/{m['id']}", json=full, headers=auth(a)).json()["detail"]["code"] == "sandbox_model_not_draft"
    listed = client.get(f"{API}/sandbox/models", headers=auth(worker)).json()
    assert [x["key"] for x in listed["items"]] == ["qwen2.5-1.5b-instruct-q4km"] and "status" not in listed["items"][0]
    assert "不经平台" in listed["note"]
    client.post(f"{API}/admin/sandbox/models/{m['id']}/retire", json={"reason": "发现更好的替代"}, headers=auth(b))
    assert client.get(f"{API}/sandbox/models", headers=auth(worker)).json()["items"] == []


def test_model_input_rejects_unknown_fields(client):
    a = make_admin(client, "13900000303", "运营丙")
    r = client.post(f"{API}/admin/sandbox/models", json=_model(status="published"), headers=auth(a))
    assert r.status_code == 422


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_responses_match_sdk_types(client, worker):
    from tests.test_client_shape_alignment import _assert_shape

    a = make_admin(client, "13900000304", "运营丁")
    b = make_admin(client, "13900000305", "运营戊")
    state = client.get(f"{API}/users/me/sandbox", headers=auth(worker)).json()
    on = _on(client, worker)
    m = client.post(f"{API}/admin/sandbox/models", json=_model(sha256=SHA, url="https://example.org/q.gguf", size_mb=1100,
                                                                license="Apache-2.0", min_ram_gb=4), headers=auth(a)).json()
    pub = client.post(f"{API}/admin/sandbox/models/{m['id']}/publish", headers=auth(b)).json()
    rows = client.get(f"{API}/admin/sandbox/models", headers=auth(a)).json()
    listed = client.get(f"{API}/sandbox/models", headers=auth(worker)).json()
    _assert_shape(state, "SandboxState")
    _assert_shape(on, "SandboxState")
    _assert_shape(m, "SandboxModelAdminRow")
    _assert_shape(pub, "SandboxModelAdminRow")
    first_admin, first_public = rows[0], listed["items"][0]
    _assert_shape(first_admin, "SandboxModelAdminRow")
    _assert_shape(listed, "SandboxModelList")
    _assert_shape(first_public, "SandboxModelRow")
