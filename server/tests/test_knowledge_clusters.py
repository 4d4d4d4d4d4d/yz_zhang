"""KB-070~076 经验按子类生长，而不是按样本堆积（108 号 spec，设计见 94 号）。

用户 2026-10-10：「知识图谱体系不可能把每个样本都添加，需要类似聚类一样，
把额外信息或者经验加到具体某个子类里，或者如果没有新建子类」。

向量用一个**语义桩**手工摆放：杭州与上海余弦 0.9（像又不够像），北京与它们正交（不像）。
缺省的词袋哈希不是语义模型——那条路单独测（退化模式不生长图谱）。
"""
import math
import random

import pytest

from app.core.db import SessionLocal
from app.vendors import registry
from app.vendors.base import VendorResult
from tests.conftest import JOB_HEADERS, auth, make_admin, register

VEC = {"杭州": [1.0, 0.0, 0.0], "上海": [0.9, math.sqrt(1 - 0.81), 0.0], "北京": [0.0, 0.0, 1.0]}


class SemanticStub:
    name = "local"   # 走同一套熔断留痕
    semantic = True
    model = "stub-sem-3"

    def embed(self, texts):
        out = []
        for t in texts:
            v = next((VEC[k] for k in VEC if k in t), None)
            if v is None:  # 没摆放过的文本：给一个确定的随机方向
                r = random.Random(t)
                v = [r.uniform(-1, 1) for _ in range(3)]
            out.append(list(v))
        return VendorResult(ok=True, external_ref="", status="succeeded",
                            data={"vectors": out, "model": self.model, "semantic": True})


@pytest.fixture()
def semantic(monkeypatch):
    monkeypatch.setitem(registry._instances, "embedding", SemanticStub())
    yield
    registry._instances.pop("embedding", None)


def _card(category="跑腿", city="杭州", outcome="completed", price=20000, days=1,
          task_id=None, decomposition=None):
    from app.modules.knowledge.models import KnowledgeCard

    with SessionLocal() as db:
        c = KnowledgeCard(category=category, city=city, title=f"{category}·{city}",
                          price_actual_cents=price, duration_days=days, outcome=outcome,
                          source_task_id=task_id, decomposition=decomposition or [])
        db.add(c)
        db.commit()
        return c.id


def _threshold(category="跑腿", merge=0.95, near=0.8, model="stub-sem-3"):
    from app.modules.knowledge.models import ClusterThreshold

    with SessionLocal() as db:
        row = db.query(ClusterThreshold).filter_by(category=category).first() or ClusterThreshold(
            category=category, calibrated_by=0, tau_merge=merge, tau_near=near, embedding_model=model)
        row.tau_merge, row.tau_near, row.embedding_model = merge, near, model
        db.add(row)
        db.commit()


def _run(client):
    r = client.post("/api/v1/knowledge/jobs/cluster", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _state(card_id):
    from app.modules.knowledge.models import KnowledgeCard

    with SessionLocal() as db:
        c = db.get(KnowledgeCard, card_id)
        return c.cluster_state, c.cluster_id, dict(c.cluster_hint or {})


def _cluster(cid):
    from app.modules.knowledge.models import KnowledgeCluster

    with SessionLocal() as db:
        c = db.get(KnowledgeCluster, cid)
        db.expunge(c)
        return c


# ------------------------------------------------------------------ KB-070 三条判定
def test_kb070_merge_create_and_undecided_are_three_different_outcomes(client, semantic):
    _threshold()
    first = _card(city="杭州")
    _run(client)
    st, cid, _ = _state(first)
    assert st == "assigned" and cid, "平台第一次见到：新建子类"
    assert _cluster(cid).created_by == "auto" and _cluster(cid).sample_count == 1

    same = _card(city="杭州")
    near = _card(city="上海")
    far = _card(city="北京")
    rep = _run(client)
    assert rep["assigned"] == 1 and rep["undecided"] == 1 and rep["created"] == 1, rep
    assert _state(same)[:2] == ("assigned", cid), "一回事：并入"
    st, _, hint = _state(near)
    assert st == "undecided" and hint["nearest_id"] == cid and 0.85 < hint["similarity"] < 0.95, \
        "像又不够像：进待定区，带上最像的子类与相似度"
    st, other, _ = _state(far)
    assert st == "assigned" and other != cid, "不像：新建"


def test_kb070a_incremental_centroid_equals_a_full_recompute(client, semantic):
    """增量并入算出来的质心，与按成员重算一致（随机向量）。"""
    from app.modules.knowledge import clusters
    from app.modules.knowledge.models import KnowledgeCard, KnowledgeCluster

    rnd = random.Random(7)
    with SessionLocal() as db:
        cl = KnowledgeCluster(category="跑腿", label="t", embedding_model="m", outcome_counts={}, centroid=[])
        db.add(cl)
        db.flush()
        vecs = []
        for i in range(25):
            v = [rnd.uniform(-1, 1) for _ in range(8)]
            vecs.append(v)
            card = KnowledgeCard(category="跑腿", city=f"c{i}", title="x", embedding=v, embedding_model="m",
                                 outcome=rnd.choice(("completed", "disputed", "cancelled")))
            db.add(card)
            db.flush()
            clusters._add(cl, card)
        db.flush()
        incremental = list(cl.centroid)
        counts = dict(cl.outcome_counts)
        clusters.recompute(db, cl)
        assert cl.sample_count == 25
        assert max(abs(a - b) for a, b in zip(incremental, cl.centroid)) < 1e-9
        assert counts == cl.outcome_counts
        db.rollback()


def test_kb070b_different_categories_never_share_a_cluster(client, semantic):
    _threshold("跑腿")
    _threshold("保洁")
    a = _card(category="跑腿", city="杭州")
    b = _card(category="保洁", city="杭州")  # 向量完全相同
    _run(client)
    assert _state(a)[1] != _state(b)[1], "措辞（向量）一样也不许跨大类并到一起"


# ------------------------------------------------------------------ KB-071 阈值
def test_kb071_no_threshold_means_held_and_alerted(client, semantic):
    card = _card(category="搬家", city="杭州")
    before = _held_metric(client, "no_threshold")
    _run(client)
    st, cid, hint = _state(card)
    assert st == "held" and cid is None and "还没有标定" in hint["note"]
    assert _held_metric(client, "no_threshold") == before + 1, "被拒的归并必须进指标"
    _threshold("搬家")
    _run(client)
    assert _state(card)[0] == "assigned", "标定之后下一轮重试"


def test_kb071a_threshold_from_another_model_is_refused(client, semantic):
    _threshold("跑腿", model="old-model")
    card = _card(city="杭州")
    _run(client)
    st, _, hint = _state(card)
    assert st == "held" and hint["reason"] == "model_mismatch" and "old-model" in hint["note"]


def test_kb071b_degraded_embedding_never_grows_the_graph(client):
    """缺省词袋哈希：不自动新建子类，只并入运营建的子类。"""
    from app.modules.knowledge.clusters import _provider_state

    model, semantic_ok = _provider_state()
    assert semantic_ok is False, "这条测的就是退化模式"
    _threshold("跑腿", model=model, merge=0.95, near=0.0)
    first = _card(city="杭州")
    _run(client)
    st, cid, hint = _state(first)
    assert st == "undecided" and cid is None and "不是语义模型" in hint["why"]

    admin = make_admin(client, "13800140001")
    r = client.post(f"/api/v1/admin/knowledge/cards/{first}/assign", json={"new_label": "跑腿·同城代取"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text
    ops_cluster = r.json()["id"]
    again = _card(city="杭州")
    _run(client)
    assert _state(again)[:2] == ("assigned", ops_cluster), "退化模式下并进运营建的子类"


def _held_metric(client, reason):
    text = client.get("/metrics", headers=JOB_HEADERS).text
    line = next(l for l in text.splitlines() if l.startswith(f'knowledge_cluster_held_total{{reason="{reason}"}}'))
    return int(line.split()[-1])


def test_kb071_calibration_from_labeled_pairs(client, semantic):
    admin = make_admin(client, "13800140002")
    hz = [_card(city="杭州") for _ in range(3)]
    sh = [_card(city="上海") for _ in range(2)]
    bj = [_card(city="北京") for _ in range(2)]
    pairs = [{"a": hz[0], "b": hz[1], "same": True}, {"a": hz[1], "b": hz[2], "same": True},
             {"a": hz[0], "b": sh[0], "same": True}, {"a": sh[0], "b": sh[1], "same": True},
             {"a": hz[0], "b": bj[0], "same": False}, {"a": sh[1], "b": bj[1], "same": False}]
    r = client.post("/api/v1/admin/knowledge/thresholds/跑腿/calibrate", json={"pairs": pairs}, headers=auth(admin))
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["embedding_model"] == "stub-sem-3" and t["labeled_pairs"] == 6 and t["errors"] == 0
    # 0 误判的 τ 落在 (0, 0.9]，并列取最高（保守）→ 0.9；
    # τ_near = 被标成一回事的最低相似度（杭州-上海 0.9）
    assert abs(t["tau_merge"] - 0.9) < 1e-3 and abs(t["tau_near"] - 0.9) < 1e-3

    too_few = client.post("/api/v1/admin/knowledge/thresholds/跑腿/calibrate",
                          json={"pairs": pairs[:5]}, headers=auth(admin))
    assert too_few.status_code == 422
    cross = _card(category="保洁", city="杭州")
    bad = client.post("/api/v1/admin/knowledge/thresholds/跑腿/calibrate",
                      json={"pairs": pairs[:5] + [{"a": hz[0], "b": cross, "same": False}]}, headers=auth(admin))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "calibration_cross_category"


# ------------------------------------------------------------------ KB-072 分歧与结果构成
def test_kb072a_dissent_is_kept_not_averaged_away(client, semantic):
    from app.modules.knowledge import clusters
    from app.modules.knowledge.models import KnowledgeCluster

    _threshold()
    common = [{"title": "接单确认"}, {"title": "取件"}, {"title": "送达拍照"}]
    other = [{"title": "约时间"}, {"title": "上门代办"}, {"title": "回执"}]
    for i in range(3):
        _card(city="杭州", task_id=9000 + i, decomposition=common)
    for i in range(2):
        _card(city="杭州", task_id=9100 + i, decomposition=other)
    _card(city="杭州", task_id=9200, decomposition=[{"title": "只此一家的做法"}, {"title": "张三家门口"}])
    _run(client)
    with SessionLocal() as db:
        cl = db.query(KnowledgeCluster).filter_by(category="跑腿").first()
        v = clusters.view(db, cl, detail=True)
    assert [s["title"] for s in v["consensus_steps"]] == ["接单确认", "取件", "送达拍照"]
    assert len(v["dissent"]) == 1 and v["dissent"][0]["count"] == 2
    assert sorted(v["dissent"][0]["steps"]) == sorted(["约时间", "上门代办", "回执"])
    assert v["dissent_hidden"] == 1, "只出现过一次的做法不展示文字，但被数出来"
    assert "张三家门口" not in str(v), "只出现在一个任务里的步骤文字不展示（k-匿名）"


def test_kb072b_outcome_mix_counts_disputes_and_cancellations(client, semantic):
    from app.modules.account.models import User
    from app.modules.dispute.models import Dispute
    from app.modules.knowledge import service
    from app.modules.knowledge.models import KnowledgeCard
    from app.modules.task.models import Task

    with SessionLocal() as db:
        u = User(phone="13800140099", nickname="x", password_hash="x")
        db.add(u)
        db.flush()
        disputed = Task(creator_id=u.id, executor_id=u.id, title="t", category="跑腿", city="杭州",
                        budget_cents=1000, status="completed", is_remote=True)
        cancelled = Task(creator_id=u.id, executor_id=u.id, title="t", category="跑腿", city="杭州",
                         budget_cents=1000, status="cancelled", is_remote=True)
        never_taken = Task(creator_id=u.id, title="t", category="跑腿", city="杭州",
                           budget_cents=1000, status="cancelled", is_remote=True)
        db.add_all([disputed, cancelled, never_taken])
        db.flush()
        db.add(Dispute(task_id=disputed.id, contract_id=0, opened_by=u.id, reason="r"))
        db.flush()
        service._on_task_completed(db, {"task_id": disputed.id})
        service._on_task_cancelled(db, {"task_id": cancelled.id})
        service._on_task_cancelled(db, {"task_id": never_taken.id})
        db.commit()
        outcomes = {c.source_task_id: c.outcome for c in db.query(KnowledgeCard)
                    .filter(KnowledgeCard.source_task_id.in_([disputed.id, cancelled.id, never_taken.id]))}
    assert outcomes == {disputed.id: "disputed", cancelled.id: "cancelled"}, \
        "经过纠纷的记 disputed；成交后取消的记 cancelled；没人接过的撤回不是经验"
    _threshold()
    _run(client)
    r = client.get("/api/v1/knowledge/clusters", params={"category": "跑腿"}).json()
    mix = r["items"][0]["outcome_mix"]
    assert mix["disputed"] >= 1 and mix["cancelled"] >= 1


# ------------------------------------------------------------------ KB-073~075 对外
def test_kb073_every_conclusion_carries_sample_size_and_time_range(client, semantic):
    _threshold()
    for _ in range(3):
        _card(city="杭州", price=20000)
    _run(client)
    items = client.get("/api/v1/knowledge/clusters", params={"category": "跑腿"}).json()["items"]
    v = items[0]
    assert v["sample_count"] == 3 and v["first_sample_at"] and v["last_sample_at"]
    assert v["few_samples"] is True and "样本过少" in v["note"]
    pr = client.get("/api/v1/knowledge/price-reference",
                    params={"category": "跑腿", "cluster_id": v["id"]}).json()
    assert "p50_cents" not in pr and "不给参考价" in pr["message"], "样本太少的子类不出价"

    for p in (10000, 30000):
        _card(city="杭州", price=p)
    _run(client)
    pr = client.get("/api/v1/knowledge/price-reference",
                    params={"category": "跑腿", "cluster_id": v["id"]}).json()
    assert pr["sample_size"] == 5 and pr["p50_cents"] == 20000


def test_kb074_detail_gives_no_individual_evidence_without_consent(client, semantic):
    _threshold()
    _card(city="杭州")
    _run(client)
    cid = client.get("/api/v1/knowledge/clusters", params={"category": "跑腿"}).json()["items"][0]["id"]
    ev = client.get(f"/api/v1/knowledge/clusters/{cid}").json()["evidence"]
    assert ev["shown"] == [] and ev["hidden"] == 1 and "授权" in ev["note"]


# ------------------------------------------------------------------ 风控与撤回
def test_risk_flagged_tasks_never_enter_a_cluster(client, semantic):
    from app.modules.aml.models import SuspiciousActivity

    _threshold()
    card = _card(city="杭州", task_id=777001)
    with SessionLocal() as db:
        db.add(SuspiciousActivity(user_id=1, pattern="wash", ref_type="task", ref_id=777001))
        db.commit()
    _run(client)
    st, cid, hint = _state(card)
    assert st == "excluded" and cid is None and "风控" in hint["reason"]


def test_kb076_retract_removes_the_sample_and_recomputes(client, semantic):
    _threshold()
    keep = _card(city="杭州", task_id=778001)
    bad = _card(city="上海", task_id=778002)
    _threshold(merge=0.85, near=0.5)  # 让上海也并进来
    _run(client)
    cid = _state(keep)[1]
    assert _state(bad)[1] == cid and _cluster(cid).sample_count == 2
    admin = make_admin(client, "13800140003")
    r = client.post("/api/v1/admin/knowledge/tasks/778002/retract", json={"reason": "事后确认刷单"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text
    assert _state(bad)[0] == "retracted"
    cl = _cluster(cid)
    assert cl.sample_count == 1 and max(abs(a - b) for a, b in zip(cl.centroid, VEC["杭州"])) < 1e-9


# ------------------------------------------------------------------ 运营面
def test_admin_assign_choose_one_and_only_admins(client, semantic):
    _threshold()
    _card(city="杭州")
    near = _card(city="上海")
    _run(client)
    user = register(client, "13800140004")
    assert client.post(f"/api/v1/admin/knowledge/cards/{near}/assign", json={"new_label": "x"},
                       headers=auth(user)).status_code == 403
    admin = make_admin(client, "13800140005")
    both = client.post(f"/api/v1/admin/knowledge/cards/{near}/assign",
                       json={"cluster_id": 1, "new_label": "x"}, headers=auth(admin))
    assert both.status_code == 400 and both.json()["detail"]["code"] == "assign_choose_one"
    hint = _state(near)[2]
    ok = client.post(f"/api/v1/admin/knowledge/cards/{near}/assign",
                     json={"cluster_id": hint["nearest_id"]}, headers=auth(admin))
    assert ok.status_code == 200 and ok.json()["sample_count"] == 2


def test_merge_keeps_old_references_resolvable(client, semantic):
    _threshold()
    a = _card(city="杭州")
    b = _card(city="北京")
    _run(client)
    ca, cb = _state(a)[1], _state(b)[1]
    admin = make_admin(client, "13800140006")
    r = client.post(f"/api/v1/admin/knowledge/clusters/{cb}/merge", json={"target_id": ca}, headers=auth(admin))
    assert r.status_code == 200 and r.json()["sample_count"] == 2
    old = client.get(f"/api/v1/knowledge/clusters/{cb}").json()
    assert old["status"] == "merged" and old["merged_into"] == ca, "历史引用不悬空"


def test_undecided_samples_sit_in_a_declared_review_queue(client, semantic):
    from app.modules.admin.queues import BY_KEY

    q = BY_KEY["knowledge"]
    assert q.tells_submitter == "" and "没有在等" in q.no_tell_why
    _threshold()
    _card(city="杭州")
    near = _card(city="上海")
    _run(client)
    with SessionLocal() as db:
        assert near in [row[0] for row in q.pending(db)]


def test_cluster_job_is_scheduled_and_guarded(client):
    from app.core.jobs import JOBS

    assert any(j.path == "/knowledge/jobs/cluster" for j in JOBS)
    assert client.post("/api/v1/knowledge/jobs/cluster").status_code in (401, 403)


def test_cluster_responses_match_the_sdk_declarations(client, semantic):
    from tests.test_client_shape_alignment import _assert_shape

    _threshold()
    _card(city="杭州")
    _run(client)
    lst = client.get("/api/v1/knowledge/clusters").json()
    _assert_shape(lst, "KnowledgeClusterList")
    _assert_shape(lst["items"][0], "KnowledgeCluster")
    detail = client.get(f"/api/v1/knowledge/clusters/{lst['items'][0]['id']}").json()
    _assert_shape(detail, "KnowledgeClusterDetail")
    admin = make_admin(client, "13800140007")
    _assert_shape(client.get("/api/v1/admin/knowledge/overview", headers=auth(admin)).json(),
                  "KnowledgeAdminOverview")
