"""REL-100~108 助手专家的可靠性（130 号 spec）：运行合同、重试退避、降级交付、数据源就绪、只送达一次、运行日志与健康度、角色契约。

来源：WorkBuddy 蓝皮书第 10、24、25 章（121 号 spec 对照）——「从一句话到运行合同」「角色契约（输入 / 输出 / 禁止动作）」。
"""
import json
from datetime import timedelta

import pytest

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.notification.models import Notification
from app.modules.packs import schema
from app.modules.packs import service as psvc
from app.modules.packs.models import PackEvent
from app.modules.workbench import service as svc
from app.modules.workbench.models import WbRoutine, WbRoutineRun
from tests.conftest import JOB_HEADERS, auth, make_admin

API = "/api/v1/workbench"


def _routine(client, user, **kw):
    # 时间点放在离现在 12 小时处（UTC+20h = 北京时间 +12h）：默认 09:00 时，在北京时间 08:00~09:00 跑会让
    # 「下一次在一小时之后」这类断言看钟点
    kw.setdefault("time_of_day", (utcnow() + timedelta(hours=20)).strftime("%H:%M"))
    r = client.post(f"{API}/routines", json={"name": "早报", "kind": "digest", "freq": "daily", **kw}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def _due(rid, minutes=1):
    with SessionLocal() as db:
        r = db.get(WbRoutine, rid)
        r.next_run_at = utcnow() - timedelta(minutes=minutes)
        db.commit()


def _job(client):
    return client.post(f"{API}/jobs/run-routines", headers=JOB_HEADERS).json()


def _notes(uid, title):
    with SessionLocal() as db:
        return db.query(Notification).filter(Notification.user_id == uid, Notification.title == title).count()


class Flaky:
    """前 n 次失败，之后成功。"""

    def __init__(self, n, real):
        self.n, self.real = n, real

    def __call__(self, *a, **k):
        if self.n:
            self.n -= 1
            raise RuntimeError("upstream")
        return self.real(*a, **k)


# ------------------------------------------------------------------ 运行合同的默认值（REL-101）
def test_contract_defaults_keep_the_old_behaviour(client, requester):
    ro = _routine(client, requester)
    assert (ro["timeout_ms"], ro["max_retries"], ro["degrade"], ro["retry_count"], ro["pending_slot_at"]) == (10000, 0, False, 0, None)
    bad = client.post(f"{API}/routines", json={"name": "x", "kind": "digest", "freq": "daily", "max_retries": 9}, headers=auth(requester))
    assert bad.status_code == 422
    patched = client.patch(f"{API}/routines/{ro['id']}", json={"max_retries": 2, "degrade": True, "timeout_ms": 5000},
                           headers=auth(requester)).json()
    assert (patched["max_retries"], patched["degrade"], patched["timeout_ms"]) == (2, True, 5000)


# ------------------------------------------------------------------ 重试退避（REL-102）
def test_failure_retries_with_backoff_on_the_same_slot_then_delivers_once(client, requester, monkeypatch):
    ro = _routine(client, requester, max_retries=2)
    monkeypatch.setattr(svc, "compose", Flaky(1, svc.compose))
    _due(ro["id"])
    with SessionLocal() as db:
        slot = db.get(WbRoutine, ro["id"]).next_run_at
    before = utcnow()
    out = _job(client)
    assert out["routines_retrying"] == 1 and out["routines_ok"] == 0 and out["routines_failed"] == 0
    with SessionLocal() as db:
        r = db.get(WbRoutine, ro["id"])
        assert r.retry_count == 1 and r.pending_slot_at == slot and r.failures == 0
        assert timedelta(seconds=47) < r.next_run_at - before < timedelta(seconds=73)    # 1 分钟后重试（±20% 抖动）
    assert _notes(requester["id"], "助手：早报") == 0
    _due(ro["id"])
    assert _job(client)["routines_ok"] == 1
    runs = client.get(f"{API}/routines/{ro['id']}/runs", headers=auth(requester)).json()
    assert [(x["status"], x["attempt"]) for x in runs] == [("ok", 2), ("retrying", 1)]
    assert runs[0]["slot_at"] == runs[1]["slot_at"] and runs[1]["error_kind"] == "RuntimeError"
    assert _notes(requester["id"], "助手：早报") == 1
    with SessionLocal() as db:
        r = db.get(WbRoutine, ro["id"])
        assert r.retry_count == 0 and r.pending_slot_at is None and r.next_run_at > utcnow() + timedelta(hours=1)


def test_backoff_grows_and_is_capped():
    assert [svc.backoff_seconds(n) for n in range(5)] == [60, 300, 1500, 1500, 1500]


# ------------------------------------------------------------------ 降级交付（REL-104）
def test_retries_exhausted_degrades_instead_of_silence(client, requester, monkeypatch):
    ro = _routine(client, requester, max_retries=1, degrade=True)
    monkeypatch.setattr(svc, "compose", Flaky(99, svc.compose))
    _due(ro["id"])
    _job(client)
    _due(ro["id"])
    out = _job(client)
    assert out["routines_degraded"] == 1
    runs = client.get(f"{API}/routines/{ro['id']}/runs", headers=auth(requester)).json()
    assert runs[0]["status"] == "degraded" and runs[0]["degraded"] is True and "没能完整生成" in runs[0]["output"]
    with SessionLocal() as db:
        n = db.query(Notification).filter(Notification.user_id == requester["id"], Notification.title == "助手：早报").one()
        assert "降级交付" in n.body
        assert db.get(WbRoutine, ro["id"]).failures == 1     # 降级也算一次失败：连续 3 次照样暂停


def test_retries_exhausted_without_degrade_fails_like_before(client, requester, monkeypatch):
    ro = _routine(client, requester, max_retries=1)
    monkeypatch.setattr(svc, "compose", Flaky(99, svc.compose))
    for _ in range(2):
        _due(ro["id"])
        _job(client)
    got = client.get(f"{API}/routines", headers=auth(requester)).json()[0]
    assert got["last_status"] == "failed" and got["failures"] == 1 and _notes(requester["id"], "助手：早报") == 0


def test_timeout_counts_as_a_failure(client, requester, monkeypatch):
    ro = _routine(client, requester, timeout_ms=1000)
    clock = iter(range(0, 10_000, 2))                    # 每次读表都过去 2 秒

    class FakeTime:
        @staticmethod
        def monotonic():
            return float(next(clock))

    monkeypatch.setattr(svc, "time", FakeTime)
    _due(ro["id"])
    _job(client)
    runs = client.get(f"{API}/routines/{ro['id']}/runs", headers=auth(requester)).json()
    assert runs[0]["status"] == "failed" and runs[0]["error_kind"] == "timeout" and runs[0]["duration_ms"] >= 2000


# ------------------------------------------------------------------ 数据源就绪（REL-103）
def test_reminder_for_a_closed_item_is_skipped_not_failed(client, requester):
    h = auth(requester)
    item = client.post(f"{API}/items", json={"title": "交季度报表"}, headers=h).json()
    ro = _routine(client, requester, kind="reminder", item_id=item["id"], note="记得交报表")
    client.patch(f"{API}/items/{item['id']}", json={"status": "done"}, headers=h)
    _due(ro["id"])
    assert _job(client)["routines_skipped"] == 1
    runs = client.get(f"{API}/routines/{ro['id']}/runs", headers=h).json()
    assert runs[0]["status"] == "skipped" and "已经" in runs[0]["output"]
    got = client.get(f"{API}/routines", headers=h).json()[0]
    assert got["failures"] == 0 and got["enabled"] and got["next_run_at"]
    assert _notes(requester["id"], "助手：早报") == 0


# ------------------------------------------------------------------ 同一次排期只送达一次（REL-106）
def test_the_same_slot_is_never_delivered_twice(client, requester):
    ro = _routine(client, requester)
    _due(ro["id"])
    with SessionLocal() as db:
        slot = db.get(WbRoutine, ro["id"]).next_run_at
        db.add(WbRoutineRun(routine_id=ro["id"], owner_id=requester["id"], status="ok", output="已送达", slot_at=slot))
        db.commit()
    out = _job(client)
    assert out["routines_ok"] == 1                       # 返回的是已有的那次
    assert _notes(requester["id"], "助手：早报") == 0
    with SessionLocal() as db:
        assert db.query(WbRoutineRun).filter_by(routine_id=ro["id"]).count() == 1
        assert db.get(WbRoutine, ro["id"]).next_run_at > utcnow()


# ------------------------------------------------------------------ 运行日志与健康度（REL-105）
def test_health_summarises_the_last_runs(client, requester, worker, monkeypatch):
    ro = _routine(client, requester, max_retries=1, degrade=True)
    monkeypatch.setattr(svc, "compose", Flaky(1, svc.compose))
    for _ in range(2):
        _due(ro["id"])
        _job(client)
    h = client.get(f"{API}/routines/{ro['id']}/health", headers=auth(requester)).json()
    assert (h["runs"], h["retries"], h["delivered"], h["success_rate"]) == (2, 1, 1, 1.0)
    assert h["error_kinds"] == [{"kind": "RuntimeError", "count": 1}] and h["p50_ms"] is not None
    assert h["contract"] == {"timeout_ms": 10000, "max_retries": 1, "degrade": True}
    assert client.get(f"{API}/routines/{ro['id']}/health", headers=auth(worker)).status_code == 404


def test_run_log_never_stores_exception_text(client, requester, monkeypatch):
    ro = _routine(client, requester)

    def leak(*a, **k):
        raise RuntimeError("身份证 110101199003071234")

    monkeypatch.setattr(svc, "compose", leak)
    _due(ro["id"])
    _job(client)
    with SessionLocal() as db:
        run = db.query(WbRoutineRun).filter_by(routine_id=ro["id"]).one()
        assert "110101" not in run.output + run.error_kind and run.error_kind == "RuntimeError"


# ------------------------------------------------------------------ 角色契约（REL-107）
SEEDS = {p.stem: schema.PackDef.model_validate(json.loads(p.read_text(encoding="utf-8"))) for p in psvc.SEEDS.glob("*.json")}


def _assistant(key):
    for d in SEEDS.values():
        for a in d.assistants:
            if a.key == key:
                return a
    raise KeyError(key)


@pytest.mark.parametrize("akey,q", [
    ("tax-assistant", "帮我把这个季度的税申报了"),
    ("tax-assistant", "你直接帮我开发票吧"),
    ("contract-assistant", "直接帮我签了这份合同"),
    ("contract-assistant", "这个你直接帮我签了吧"),     # 只有「签」一个字：靠强动词认出
    ("policy-assistant", "替我提交这个补贴申请"),
    ("collab-advisor", "帮我确认验收，钱放给他"),
    ("gig-assistant", "帮我报名这一单"),
])
def test_asking_an_assistant_to_do_a_forbidden_thing_is_refused(akey, q):
    assert psvc.contract_violation(_assistant(akey), q), q


@pytest.mark.parametrize("akey,q", [
    ("tax-assistant", "帮我看看申报截止是哪天"),
    ("tax-assistant", "发票怎么开"),
    ("contract-assistant", "帮我看看这份合同的违约金条款"),
    ("collab-advisor", "验收过期会怎样"),
    ("gig-assistant", "附近有什么单"),
])
def test_asking_about_a_forbidden_thing_is_still_answered(akey, q):
    assert psvc.contract_violation(_assistant(akey), q) == "", q


def test_contract_endpoint_and_runtime_refusal(client, requester):
    a, b = make_admin(client, "13900000401", "运营甲"), make_admin(client, "13900000402", "运营乙")
    pid = client.post("/api/v1/admin/packs", json={"definition": json.loads((psvc.SEEDS / "collab-basics.json").read_text(encoding="utf-8"))},
                      headers=auth(a)).json()["id"]
    client.post(f"/api/v1/admin/packs/{pid}/submit", headers=auth(a))
    assert client.post(f"/api/v1/admin/packs/{pid}/approve", headers=auth(b)).status_code == 200
    h = auth(requester)
    c = client.get("/api/v1/packs/collab-basics/assistants/collab-advisor/contract", headers=h).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(c, "AssistantContract")
    first_tool, first_gate = c["tools"][0], c["human_gates"][0]
    _assert_shape(first_tool, "AssistantContractItem")
    _assert_shape(first_gate, "AssistantContractItem")
    assert c["name"] == "协作顾问" and c["forbidden"] and {g["key"] for g in c["human_gates"]} == {"money", "sign"}
    assert all(t["name"] for t in c["tools"]) and c["inputs"] and c["outputs"]
    assert client.get("/api/v1/packs/collab-basics/assistants/nobody/contract", headers=h).status_code == 404
    r = client.post("/api/v1/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "帮我确认验收，钱放给他"}, headers=h).json()
    assert r["refused"] and "角色契约" in r["answer"] and "必须你本人确认" in r["answer"] and r["citations"] == []
    ok = client.post("/api/v1/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "验收过期会怎样"}, headers=h).json()
    assert not ok["refused"]
    with SessionLocal() as db:
        assert sorted(e.kind for e in db.query(PackEvent)) == ["ask", "refused"]


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_responses_match_sdk_types(client, requester, monkeypatch):
    from tests.test_client_shape_alignment import _assert_shape

    ro = _routine(client, requester, max_retries=1)
    _assert_shape(ro, "WbRoutine")
    monkeypatch.setattr(svc, "compose", Flaky(1, svc.compose))
    _due(ro["id"])
    _job(client)
    runs = client.get(f"{API}/routines/{ro['id']}/runs", headers=auth(requester)).json()
    first_run = runs[0]
    _assert_shape(first_run, "WbRoutineRun")
    health = client.get(f"{API}/routines/{ro['id']}/health", headers=auth(requester)).json()
    _assert_shape(health, "WbRoutineHealth")
    kind, contract = health["error_kinds"][0], health["contract"]
    _assert_shape(kind, "WbRoutineErrorKind")
    _assert_shape(contract, "WbRoutineContract")
