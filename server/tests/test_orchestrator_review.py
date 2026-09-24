"""AIO-040~049 编排闭环增强验证（24 号 spec）。

这套测试盯的是「循环到底能不能收敛」，以及那条第一性约束：
**模型的判定永远不能单独动钱**。
"""
import pytest

from app.core.db import SessionLocal
from app.modules.orchestrator import review as review_mod
from app.modules.orchestrator.review import (
    QUALITY_BAR,
    ModelReview,
    ReviewResult,
    RuleReview,
    set_review_gateway,
)

from .conftest import auth, topup
from .test_orchestrator import _finish_task, _mission
from .test_task_flow import match_and_fund


@pytest.fixture(autouse=True)
def _reset_gateway():
    set_review_gateway(None)
    yield
    set_review_gateway(None)


def _tick(client, user, mission_id):
    r = client.post(f"/api/v1/missions/{mission_id}/tick", headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def _detail(client, user, mission_id):
    return client.get(f"/api/v1/missions/{mission_id}", headers=auth(user)).json()


class StubReview:
    """可控评审网关，用来在测试里精确制造 pass/revise/fail。"""

    name = "rule"

    def __init__(self, verdict="pass", score=100, missing=None):
        self.result = ReviewResult(verdict, score, ["stub"], missing or [], "rule")
        self.calls = 0

    def review(self, criteria, evidence):
        self.calls += 1
        return self.result


# ---------- AIO-001/002 验收要点显式化 ----------
def test_acceptance_criteria_reach_the_worker(client, requester):
    """执行者从一开始就该知道「怎样算做完」——这比事后争议便宜得多。"""
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="带验收要点的统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])

    step = detail["steps"][0]
    assert step["acceptance"], "规划必须给出验收要点（模板引擎路径也要有）"
    # Mission 级要求（_mission 里传了「物品无损」「现场清洁」）要下发到步
    assert "物品无损" in step["acceptance"]

    task = client.get(f"/api/v1/tasks/{step['task_id']}", headers=auth(requester)).json()
    assert "【验收要点】" in task["description"]
    assert "物品无损" in task["description"]


# ---------- AIO-010 规则评审真的在打分 ----------
def test_rule_review_distinguishes_evidence_quality(client, requester, worker):
    """规则评审不是占位符：有留痕有凭证的交付，分数必须高于「交一句做完了」。"""
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="证据质量对比")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])
    bare, rich = detail["steps"][0], detail["steps"][1]

    # 裸交付：直接验收，无留痕无凭证
    _finish_task(client, requester, worker, bare["task_id"])

    # 富交付：打卡 + 两条留痕 + 图片凭证
    import base64

    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()
    url = client.post("/api/v1/files",
                      json={"content_type": "image/png", "data_base64": png},
                      headers=auth(worker)).json()["url"]
    task = client.get(f"/api/v1/tasks/{rich['task_id']}", headers=auth(requester)).json()
    match_and_fund(client, requester, worker, task)
    for note in ("已到现场开始作业", "主体完成，附现场照"):
        client.post(f"/api/v1/tasks/{rich['task_id']}/progress",
                    json={"content": note, "images": [url]}, headers=auth(worker))
    client.post(f"/api/v1/tasks/{rich['task_id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{rich['task_id']}/accept-delivery", headers=auth(requester))

    _tick(client, requester, m["id"])
    after = _detail(client, requester, m["id"])
    scores = {s["id"]: s["review_score"] for s in after["steps"]}
    assert scores[rich["id"]] > scores[bare["id"]], (
        f"有凭证的交付没有拿到更高分：{scores}")


# ---------- AIO-047 质量闸门 ----------
def test_low_quality_does_not_count_as_success(client, requester, worker):
    """全部步骤「完成」但均分不过线 → 不算达标，转整改。

    只看完成率就会把「交一句做完了」当成达标——质量闸门是这个循环的意义。
    """
    topup(client, requester, 400000)
    m = _mission(client, requester, cap=300000, goal="质量闸门统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])

    set_review_gateway(StubReview("revise", QUALITY_BAR - 20, ["现场照片"]))
    for s in detail["steps"]:
        _finish_task(client, requester, worker, s["task_id"])
    r = _tick(client, requester, m["id"])

    assert r["status"] != "succeeded", "均分不过线不该判定为达标"
    after = _detail(client, requester, m["id"])
    # 转入整改：生成了修复步（能否立刻分发取决于剩余预算，那是另一条护栏）
    assert any(s["is_remedy"] for s in after["steps"]), "不达标必须转整改，而不是原地卡住"
    assert all(s["review_verdict"] == "revise"
               for s in after["steps"] if s["review_verdict"])


def test_quality_pct_reported(client, requester, worker):
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="质量分统计")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])
    set_review_gateway(StubReview("pass", 88))
    for s in detail["steps"]:
        _finish_task(client, requester, worker, s["task_id"])
    r = _tick(client, requester, m["id"])
    assert r["quality_pct"] == 88
    assert r["status"] == "succeeded"


# ---------- AIO-021 修复步带整改要点 ----------
def test_remedy_carries_fixup_notes(client, requester, worker):
    """原实现是同规格重发——同样的标题、预算、技能要求再发一次，
    凭什么这次会成功。修复步必须告诉执行者上一轮缺什么。"""
    topup(client, requester, 400000)
    m = _mission(client, requester, cap=300000, goal="整改要点统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])

    set_review_gateway(StubReview("fail", 10, ["现场照片", "交付说明"]))
    _finish_task(client, requester, worker, detail["steps"][0]["task_id"])
    _tick(client, requester, m["id"])

    after = _detail(client, requester, m["id"])
    remedy = next(s for s in after["steps"] if s["is_remedy"])
    task = client.get(f"/api/v1/tasks/{remedy['task_id']}", headers=auth(requester)).json()
    assert "本轮整改要求" in task["description"]
    assert "现场照片" in task["description"] and "交付说明" in task["description"]
    assert "【验收要点】" in task["description"]  # 验收要点仍然在


def test_remedy_is_idempotent_by_parent_fk(client, requester):
    """AIO-022 幂等改用 parent_step_id：重复 tick 不产生重复修复步。"""
    topup(client, requester, 400000)
    m = _mission(client, requester, cap=300000, goal="幂等统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])
    client.post(f"/api/v1/tasks/{detail['steps'][0]['task_id']}/cancel",
                headers=auth(requester))

    _tick(client, requester, m["id"])
    first = len([s for s in _detail(client, requester, m["id"])["steps"] if s["is_remedy"]])
    _tick(client, requester, m["id"])
    second = len([s for s in _detail(client, requester, m["id"])["steps"] if s["is_remedy"]])
    assert first == second == 1, f"修复步被重复生成：{first} → {second}"


def test_repeated_failure_boosts_budget(client, requester):
    """AIO-021 连续多轮不达标 → 上浮预算重新招募，而不是无限重试同一形态。"""
    topup(client, requester, 500000)
    m = _mission(client, requester, cap=400000, iters=5, goal="上浮预算统筹")
    _tick(client, requester, m["id"])

    budgets = []
    for _ in range(3):
        detail = _detail(client, requester, m["id"])
        live = [s for s in detail["steps"] if s["status"] == "dispatched"]
        if not live:
            break
        budgets.append(live[0]["budget_cents"])
        for s in live:
            client.post(f"/api/v1/tasks/{s['task_id']}/cancel", headers=auth(requester))
        _tick(client, requester, m["id"])

    assert len(budgets) >= 3
    assert budgets[-1] > budgets[0], f"多轮失败后预算没有上浮：{budgets}"


# ---------- AIO-012 模型不得动钱（第一性约束）----------
def test_review_verdict_never_moves_money(client, requester, worker):
    """评审判 fail 时，合约资金状态必须零变化。

    模型会错，而资金操作不可逆。AI 只做「谁该看一眼」的分诊。
    """
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="资金零变化统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])
    step = detail["steps"][0]

    set_review_gateway(StubReview("fail", 0, ["全部"]))
    _finish_task(client, requester, worker, step["task_id"])

    before_r = client.get("/api/v1/wallet", headers=auth(requester)).json()
    before_w = client.get("/api/v1/wallet", headers=auth(worker)).json()
    contract_before = client.get(f"/api/v1/contracts/by-task/{step['task_id']}",
                                 headers=auth(requester)).json()

    _tick(client, requester, m["id"])

    after_r = client.get("/api/v1/wallet", headers=auth(requester)).json()
    after_w = client.get("/api/v1/wallet", headers=auth(worker)).json()
    contract_after = client.get(f"/api/v1/contracts/by-task/{step['task_id']}",
                                headers=auth(requester)).json()
    assert after_r == before_r, "评审不达标不得改变发布方资金"
    assert after_w == before_w, "评审不达标不得从执行者账上扣钱"
    assert contract_after["status"] == contract_before["status"]
    assert contract_after["released_cents"] == contract_before["released_cents"]


# ---------- AIO-013 评审留痕 ----------
def test_review_is_recorded_with_provenance(client, requester, worker):
    """没有留痕的自动判定在纠纷里毫无价值。"""
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="留痕统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])
    step = detail["steps"][0]
    _finish_task(client, requester, worker, step["task_id"])
    _tick(client, requester, m["id"])

    r = client.get(f"/api/v1/missions/{m['id']}/steps/{step['id']}/reviews",
                   headers=auth(requester))
    assert r.status_code == 200, r.text
    rows = r.json()["reviews"]
    assert rows, "评审必须留痕"
    row = rows[0]
    assert row["reviewer"] == "rule"
    assert row["prompt_version"]
    assert row["verdict"] in ("pass", "revise", "fail")
    assert row["duration_ms"] >= 0


def test_review_digest_is_redacted():
    """AIO-033 送模型与落库的内容都不得含手机号/证件号。"""
    from app.core.observability import redact

    raw = "联系人 13812345678，证件 110101199001011234"
    out = redact(raw)
    assert "13812345678" not in out and "110101199001011234" not in out


# ---------- AIO-040/042 降级 ----------
def test_model_review_falls_back_on_bad_output(monkeypatch):
    """结构化输出不合规 → 降级规则评审，不抛错。"""
    gateway = ModelReview("claude-opus-4-8")

    def boom(*_a, **_k):
        raise ValueError("模型返回了不合规 JSON")

    monkeypatch.setattr(gateway, "_call", boom)
    evidence = {"task_id": 1, "progress_count": 2, "image_count": 1,
                "delivery_note": "完成", "reject_count": 0, "checkin_count": 1}
    result = gateway.review(["要点"], evidence)
    assert result.reviewer == "rule"          # 已降级
    assert result.verdict in ("pass", "revise")


def test_rule_review_handles_missing_evidence():
    result = RuleReview().review(["要点"], {})
    assert result.verdict == "fail" and result.score == 0


# ---------- AIO-043 配额 ----------
def test_model_call_quota_degrades_to_rule(client, requester, worker, monkeypatch):
    """达到模型调用上限后停止调用并降级，不静默烧 API 账单。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ORC_MAX_MODEL_CALLS", 1)
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="配额统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])

    calls = {"n": 0}

    class CountingModel:
        name = "anthropic:test-model"

        def review(self, criteria, evidence):
            calls["n"] += 1
            return ReviewResult("pass", 90, [], [], self.name)

    set_review_gateway(CountingModel())
    for s in detail["steps"]:
        _finish_task(client, requester, worker, s["task_id"])
    _tick(client, requester, m["id"])

    assert calls["n"] == 1, f"配额未生效，模型被调用了 {calls['n']} 次"
    after = _detail(client, requester, m["id"])
    assert after["model_calls"] == 1
    # 其余步降级为规则评审，循环照常推进
    assert all(s["review_verdict"] for s in after["steps"] if s["status"] in ("done", "failed"))


# ---------- AIO-049 时间线 ----------
def test_timeline_is_human_readable(client, requester, worker):
    """agent 必须可解释，否则没人敢授权它自动花钱。"""
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="时间线统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])
    assert detail["timeline"], "每轮 tick 都应留下摘要"
    first = detail["timeline"][0]
    assert "规划出" in first["summary"] and "发布" in first["summary"]
    assert "下一步" in first["summary"]

    for s in detail["steps"]:
        _finish_task(client, requester, worker, s["task_id"])
    _tick(client, requester, m["id"])
    final = _detail(client, requester, m["id"])
    assert final["timeline"][-1]["action"] == "completed"
    assert "达标" in final["timeline"][-1]["summary"]


# ---------- 闭环：失败 → 整改 → 达标 ----------
def test_full_loop_recovers_from_first_round_failure(client, requester, worker):
    """本 spec 的验收标准：首轮全部流单 → 修复 → 真正走到 succeeded。

    此前这个场景会因为预算被虚耗的占用卡死在 blocked，循环闭不上。
    """
    topup(client, requester, 500000)
    m = _mission(client, requester, cap=300000, iters=5, goal="闭环恢复统筹")
    _tick(client, requester, m["id"])
    detail = _detail(client, requester, m["id"])

    for s in detail["steps"]:
        client.post(f"/api/v1/tasks/{s['task_id']}/cancel", headers=auth(requester))
    r = _tick(client, requester, m["id"])
    assert r["status"] == "running" and r["dispatched"] >= 1

    after = _detail(client, requester, m["id"])
    for s in [x for x in after["steps"] if x["status"] == "dispatched"]:
        _finish_task(client, requester, worker, s["task_id"])
    final = _tick(client, requester, m["id"])

    assert final["status"] == "succeeded", f"循环没有收敛：{final}"
    assert final["completion_pct"] == 100
    detail = _detail(client, requester, m["id"])
    assert detail["spent_cents"] + detail["committed_cents"] <= detail["budget_cap_cents"]
