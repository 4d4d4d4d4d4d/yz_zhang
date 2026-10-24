"""INF-100~109 影响力与专家等级（127 号 spec）。

用户原话：「对于平台来说……也可以考虑用区块链 POS 来累计用户影响力从而提升专业能力成为专家。」
做法：影响力只能靠闭环合作挣、不可转让、可质押担保、败诉罚没、按半衰期衰减、每日快照的 Merkle 根锚定进存证链。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.main import app
from app.modules.account.models import User, utcnow
from app.modules.anchor.models import AnchorEntry
from app.modules.influence import service as svc
from app.modules.influence.models import InfluenceEvent, InfluenceSnapshot, InfluenceVouch
from app.modules.notification.models import Notification
from app.modules.task.models import Review, Task
from tests.conftest import JOB_HEADERS, auth, ban_user_row, make_admin, register, respond_dispute, topup

from .test_task_flow import match_and_fund, publish_task

API = "/api/v1"


def _done(executor_id, creator_id, category="保洁", budget=20000, stars=None, revealed=True, days_ago=0.0, earn=True):
    """直接造一单已完成的（再按事件的路径记账）。"""
    at = utcnow() - timedelta(days=days_ago)
    with SessionLocal() as db:
        t = Task(creator_id=creator_id, executor_id=executor_id, title=f"{category}单", description="", category=category,
                 budget_cents=budget, status="completed", completed_at=at)
        db.add(t)
        db.flush()
        if stars:
            db.add(Review(task_id=t.id, reviewer_id=creator_id, target_id=executor_id, stars=stars,
                          rating_applied=revealed, created_at=at))
        if earn:
            svc.on_task_completed(db, {"task_id": t.id})
        db.commit()
        return t.id


def _grant(uid, points, category="保洁", days_ago=0.0, ref_id=None):
    with SessionLocal() as db:
        n = db.query(InfluenceEvent).count()
        db.add(InfluenceEvent(user_id=uid, category=category, kind="earn_task", points=points, ref_type="seed",
                              ref_id=ref_id or 900000 + n, reason="测试", created_at=utcnow() - timedelta(days=days_ago)))
        db.commit()


def _skilled(client, phone, nickname, points=100.0, category="保洁"):
    """一个在该类目已经是熟手的人（3 单 + 足够的影响力）。"""
    u = register(client, phone, nickname)
    other = register(client, "138" + phone[3:], f"{nickname}的客户")
    for _ in range(3):
        _done(u["id"], other["id"], category, earn=False)
    _grant(u["id"], points, category)
    return u


def _points(client, user, category="保洁"):
    me = client.get(f"{API}/influence/me", headers=auth(user)).json()
    return next((c for c in me["categories"] if c["category"] == category), None)


# ------------------------------------------------------------------ 挣（INF-101）
def test_earning_through_the_real_task_flow_and_only_once(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"{API}/tasks/{task['id']}/deliver", headers=auth(worker))
    assert client.post(f"{API}/tasks/{task['id']}/accept-delivery", headers=auth(requester)).status_code == 200
    w = round(svc.task_weight(20000), 2)
    with SessionLocal() as db:
        rows = {(e.user_id, e.kind): e.points for e in db.query(InfluenceEvent)}
        assert rows == {(worker["id"], "earn_task"): w, (requester["id"], "earn_publish"): round(w * 0.2, 2)}
        svc.on_task_completed(db, {"task_id": task["id"]})        # 重放：不重复记
        db.commit()
        assert db.query(InfluenceEvent).count() == 2
    mine = _points(client, worker)
    assert mine["points"] == round(w) and mine["tier"] == "newcomer" and mine["completed"] == 1
    assert "还要再完成 2 单" in mine["gaps"][0]


def test_same_pair_diminishes_but_a_new_client_counts_in_full(client, requester, worker):
    other = register(client, "13900000071", "另一个发单方")
    for _ in range(3):
        _done(worker["id"], requester["id"])
    _done(worker["id"], other["id"])
    w = svc.task_weight(20000)
    with SessionLocal() as db:
        got = [e.points for e in db.query(InfluenceEvent).filter(InfluenceEvent.user_id == worker["id"])
               .order_by(InfluenceEvent.id)]
    assert got == [round(w, 2), round(w / 2, 2), round(w / 3, 2), round(w, 2)]


def test_task_weight_grows_slowly_and_is_capped():
    assert svc.task_weight(0) == 10
    assert 10 < svc.task_weight(100_000) < svc.task_weight(1_000_000) <= 30
    assert svc.task_weight(10 ** 12) == 30


def test_decay_halves_every_180_days(client, worker):
    now = utcnow()
    assert svc.decay(10, now - timedelta(days=180), now) == 5
    assert abs(svc.decay(10, now - timedelta(days=360), now) - 2.5) < 1e-9
    _grant(worker["id"], 40, days_ago=180)
    assert _points(client, worker)["points"] == 20


def test_ratings_count_only_after_reveal(client, requester, worker):
    tid = _done(worker["id"], requester["id"], stars=5, revealed=False, earn=False)
    with SessionLocal() as db:
        assert svc.ledger(db, [worker["id"]]) == {}
        db.query(Review).filter(Review.task_id == tid).update({"rating_applied": True})
        db.commit()
        assert svc.ledger(db, [worker["id"]]) == {(worker["id"], "保洁"): 4.0}
        # 发单方被评的星不算进他「做」的类目（只算执行方）
        db.add(Review(task_id=tid, reviewer_id=worker["id"], target_id=requester["id"], stars=1, rating_applied=True))
        db.commit()
        assert svc.ledger(db, [requester["id"]]) == {}


# ------------------------------------------------------------------ 等级（INF-102）
def test_tiers_need_points_completions_stars_identity_and_a_clean_record():
    now = utcnow()
    good = {"completed": 12, "stars": [5, 5, 4], "last_slash": None}
    assert svc.tier(10, good, True)[0] == "newcomer"
    assert svc.tier(30, {"completed": 3}, False)[0] == "skilled"
    assert svc.tier(30, {"completed": 2}, False)[0] == "newcomer"
    assert svc.tier(150, good, True)[0] == "expert"
    key, gaps = svc.tier(150, good, False)
    assert key == "skilled" and "要先完成实名" in gaps[0] and gaps[0].startswith("升到「专家」")
    assert svc.tier(150, {**good, "stars": [4, 4, 5]}, True)[0] == "skilled"
    assert svc.tier(150, {**good, "last_slash": now - timedelta(days=30)}, True)[0] == "skilled"
    assert svc.tier(150, {**good, "last_slash": now - timedelta(days=200)}, True)[0] == "expert"
    senior = {"completed": 40, "stars": [5] * 10, "last_slash": None}
    assert svc.tier(320, senior, True)[0] == "expert_senior"
    assert svc.tier(320, senior, True)[1] == []


# ------------------------------------------------------------------ 罚没、担保罚没与申诉恢复（INF-103 / 105）
def test_dispute_loss_slashes_the_executor_and_the_voucher_and_appeal_restores_both(client, requester, worker):
    _grant(worker["id"], 100)
    voucher = _skilled(client, "13900000081", "担保人")
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    v = client.post(f"{API}/influence/vouches", json={"subject_id": worker["id"], "category": "保洁",
                                                      "task_id": task["id"], "stake": 20}, headers=auth(voucher))
    assert v.status_code == 201, v.text
    # 开工了：担保锁住，不能撤
    locked = client.delete(f"{API}/influence/vouches/{v.json()['id']}", headers=auth(voucher))
    assert locked.status_code == 409 and locked.json()["detail"]["code"] == "influence_vouch_locked"
    d = client.post(f"{API}/tasks/{task['id']}/disputes", json={"reason": "交付不符约定，要求重做或退款"},
                    headers=auth(requester)).json()
    respond_dispute(client, d["id"], worker)
    admin = make_admin(client, "13900000091", "仲裁员")
    assert client.post(f"{API}/disputes/{d['id']}/verdict", json={"executor_share_bps": 2000, "reason": "主要责任在执行方"},
                       headers=auth(admin)).status_code == 200
    with SessionLocal() as db:
        slash = db.query(InfluenceEvent).filter_by(user_id=worker["id"], kind="slash_dispute").one()
        assert slash.points == -30.0                                    # 当前 100 的 30%
        assert db.query(InfluenceEvent).filter_by(user_id=worker["id"], kind="earn_task").count() == 1  # 只有种子那条
        vs = db.query(InfluenceEvent).filter_by(user_id=voucher["id"], kind="slash_vouch").one()
        assert vs.points == -10.0 and db.get(InfluenceVouch, v.json()["id"]).status == "slashed"
    assert _points(client, worker)["points"] == 70
    # 申诉改判：恢复罚没，担保人恢复担保额，执行方这一单照常算挣
    assert client.post(f"{API}/disputes/{d['id']}/appeal", headers=auth(worker)).status_code == 200
    senior = make_admin(client, "13900000092", "复核员")
    r = client.post(f"{API}/disputes/{d['id']}/appeal-verdict", json={"executor_share_bps": 8000, "reason": "复核：执行方基本按约完成"},
                    headers=auth(senior))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.query(InfluenceEvent).filter_by(user_id=worker["id"], kind="restore").one().points == 30.0
        assert db.query(InfluenceEvent).filter_by(user_id=voucher["id"], kind="restore").one().points == 10.0
        assert db.get(InfluenceVouch, v.json()["id"]).status == "released"
        earned = db.query(InfluenceEvent).filter_by(user_id=worker["id"], kind="earn_task", ref_type="task").one()
        assert earned.points == round(svc.task_weight(20000) * 0.8, 2)
        # 原来那条罚没还在：账本只增不改
        assert db.query(InfluenceEvent).filter_by(user_id=worker["id"], kind="slash_dispute").count() == 1


def test_slash_has_a_floor_and_a_recent_slash_blocks_expert():
    now = utcnow()
    assert max(svc.SLASH_MIN, 5 * svc.SLASH_RATE) == 10.0
    stats = {"completed": 15, "stars": [5, 5], "last_slash": now}
    key, gaps = svc.tier(200, stats, True, now)
    assert key == "skilled" and "近 180 天内不能有纠纷败诉" in gaps[0]


def test_vouch_released_and_rewarded_when_the_task_completes(client, requester, worker):
    voucher = _skilled(client, "13900000082", "担保人")
    with SessionLocal() as db:
        t = Task(creator_id=requester["id"], executor_id=worker["id"], title="保洁单", description="", category="保洁",
                 budget_cents=20000, status="completed", completed_at=utcnow())
        db.add(t)
        db.flush()
        db.add(InfluenceVouch(voucher_id=voucher["id"], subject_id=worker["id"], category="保洁", task_id=t.id, stake=20))
        svc.on_task_completed(db, {"task_id": t.id})
        db.commit()
        v = db.query(InfluenceVouch).one()
        assert v.status == "released" and v.resolved_at is not None
        assert db.query(InfluenceEvent).filter_by(user_id=voucher["id"], kind="earn_vouch").one().points == 2.0


def test_vouch_rules(client, requester, worker):
    voucher = _skilled(client, "13900000083", "担保人", points=60)
    h = auth(voucher)

    def vouch(**kw):
        return client.post(f"{API}/influence/vouches", json={"subject_id": worker["id"], "category": "保洁", "stake": 10, **kw},
                           headers=h)

    def code(r):
        return r.json()["detail"]["code"]

    assert code(client.post(f"{API}/influence/vouches", json={"subject_id": voucher["id"], "category": "保洁", "stake": 1},
                            headers=h)) == "influence_vouch_self"
    newbie = client.post(f"{API}/influence/vouches", json={"subject_id": worker["id"], "category": "保洁", "stake": 1},
                         headers=auth(requester))
    assert newbie.status_code == 409 and code(newbie) == "influence_vouch_tier"
    assert code(vouch(category="设计")) == "influence_vouch_tier"          # 等级按类目算
    assert code(vouch(stake=31)) == "influence_stake_exceeds"              # 最多 60 的一半
    other = publish_task(client, requester, title="没报名的单")
    assert code(vouch(task_id=other["id"])) == "influence_vouch_task_mismatch"
    first = vouch(stake=25)
    assert first.status_code == 201 and first.json()["status"] == "active"
    assert code(vouch(stake=1)) == "influence_vouch_exists"
    assert code(vouch(stake=10, subject_id=requester["id"])) == "influence_stake_exceeds"   # 已锁 25，只剩 5
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.user_id == worker["id"], Notification.title == "有人为你担保").count() == 1
    mine = _points(client, voucher)
    assert mine["locked"] == 25 and mine["available"] == 5
    # 别人撤不了；本人撤了以后释放额度，再撤说清楚已经结束
    assert client.delete(f"{API}/influence/vouches/{first.json()['id']}", headers=auth(worker)).status_code == 404
    assert client.delete(f"{API}/influence/vouches/{first.json()['id']}", headers=h).json() == {"withdrawn": True}
    assert code(client.delete(f"{API}/influence/vouches/{first.json()['id']}", headers=h)) == "influence_vouch_closed"
    assert _points(client, voucher)["available"] == 30
    received = client.get(f"{API}/influence/me", headers=auth(worker)).json()["vouches_received"]
    assert received[0]["voucher_nickname"] == "担保人" and received[0]["status"] == "withdrawn"


def test_category_vouches_expire_after_180_days_without_reward(client, worker):
    voucher = _skilled(client, "13900000084", "担保人")
    with SessionLocal() as db:
        db.add(InfluenceVouch(voucher_id=voucher["id"], subject_id=worker["id"], category="保洁", stake=10,
                              created_at=utcnow() - timedelta(days=181)))
        db.add(InfluenceVouch(voucher_id=voucher["id"], subject_id=worker["id"], category="保洁", stake=10, task_id=None))
        db.commit()
    r = client.post(f"{API}/influence/jobs/snapshot", headers=JOB_HEADERS).json()
    assert r["released"] == 1
    assert client.post(f"{API}/influence/jobs/snapshot").status_code in (401, 403)
    with SessionLocal() as db:
        assert db.query(InfluenceEvent).filter_by(kind="earn_vouch").count() == 0


# ------------------------------------------------------------------ 对外与隐私（INF-107）
def test_public_view_and_leaderboard_respect_privacy(client, requester, worker):
    expert = _skilled(client, "13900000085", "公开熟手")
    hidden = _skilled(client, "13900000086", "不公开熟手")
    banned = _skilled(client, "13900000087", "被封熟手")
    with SessionLocal() as db:
        db.get(User, hidden["id"]).privacy = {"profile_public": False}
        db.commit()
    ban_user_row(banned["id"])
    _grant(worker["id"], 5)                                                # 新手不上榜
    board = client.get(f"{API}/influence/leaderboard", params={"category": "保洁"}, headers=auth(requester)).json()
    assert [r["user_id"] for r in board["items"]] == [expert["id"]] and board["items"][0]["tier_name"] == "熟手"
    pub = client.get(f"{API}/users/{expert['id']}/influence", headers=auth(requester))
    assert pub.status_code == 200
    cat = pub.json()["categories"][0]
    assert "locked" not in cat and "gaps" not in cat and "events" not in pub.json()
    assert client.get(f"{API}/users/{hidden['id']}/influence", headers=auth(requester)).status_code == 404
    assert client.get(f"{API}/users/{hidden['id']}/influence", headers=auth(hidden)).status_code == 200
    assert client.get(f"{API}/users/{banned['id']}/influence", headers=auth(requester)).status_code == 404


# ------------------------------------------------------------------ 不可转让（INF-108）
def test_there_is_no_way_to_move_influence_to_someone_else():
    # 用 OpenAPI 列接口：include 进来的路由不会摊平到 app.routes（见 test_job_orchestration）
    routes = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() if "influence" in p for m in ops}
    writes = {(m, p) for m, p in routes if m not in ("GET", "HEAD")}
    assert len(routes) == 8
    assert writes == {("POST", "/api/v1/influence/vouches"), ("DELETE", "/api/v1/influence/vouches/{vouch_id}"),
                      ("POST", "/api/v1/influence/jobs/snapshot")}
    for word in ("transfer", "gift", "redeem", "withdraw", "convert", "buy", "sell"):
        assert not any(word in p for _, p in routes), word


def test_vouch_body_cannot_carry_points_or_a_voucher(client, worker, requester):
    r = client.post(f"{API}/influence/vouches", json={"subject_id": worker["id"], "category": "保洁", "stake": 1,
                                                      "voucher_id": worker["id"]}, headers=auth(requester))
    assert r.status_code == 422


# ------------------------------------------------------------------ 快照与证明（INF-106）
def test_merkle_proofs_verify_for_every_leaf_and_reject_tampering():
    for n in (1, 2, 3, 5, 8):
        leaves = [svc.leaf(i, "保洁", float(i)) for i in range(n)]
        root, levels = svc.merkle(leaves)
        for lf in leaves:
            assert svc.verify_proof(lf, svc.proof(levels, lf), root)
        forged = svc.leaf(0, "保洁", 999.0)
        assert not svc.verify_proof(forged, svc.proof(levels, leaves[0]), root)


def test_snapshot_is_anchored_and_my_proof_verifies(client, requester, worker):
    _grant(worker["id"], 40)
    _grant(worker["id"], 12, category="设计")
    _grant(requester["id"], 7)
    assert client.get(f"{API}/influence/snapshots/latest", headers=auth(worker)).json() == {"snapshot": None}
    assert client.get(f"{API}/influence/me/proof", headers=auth(worker)).json() == {"snapshot": None, "items": []}
    snap = client.post(f"{API}/influence/jobs/snapshot", headers=JOB_HEADERS).json()["snapshot"]
    assert snap["leaves"] == 3 and len(snap["merkle_root"]) == 64
    with SessionLocal() as db:
        entry = db.query(AnchorEntry).filter_by(event_type="influence.snapshot").one()
        assert entry.seq == snap["anchor_seq"] and snap["merkle_root"] in entry.payload
    proof = client.get(f"{API}/influence/me/proof", headers=auth(worker)).json()
    assert {i["category"] for i in proof["items"]} == {"保洁", "设计"} and all(i["verified"] for i in proof["items"])
    assert proof["snapshot"]["merkle_root"] == snap["merkle_root"]
    # 快照存的是那一刻的数：之后再挣，旧快照的证明照样成立
    _grant(worker["id"], 5)
    again = client.get(f"{API}/influence/me/proof", headers=auth(worker)).json()
    assert all(i["verified"] for i in again["items"]) and again["items"] == proof["items"]
    with SessionLocal() as db:
        s = db.query(InfluenceSnapshot).one()
        s.entries = [[u, c, p + 1 if u == worker["id"] else p] for u, c, p in s.entries]   # 篡改存下来的数
        db.commit()
    assert not any(i["verified"] for i in client.get(f"{API}/influence/me/proof", headers=auth(worker)).json()["items"])


# ------------------------------------------------------------------ 撮合加分（INF-104）
def test_matching_gives_tier_bonus_with_a_reason(client, requester, worker):
    from app.modules.matching.service import FIT_TIER, _category_fit

    with SessionLocal() as db:
        u = db.get(User, worker["id"])
        u.is_verified = True
        db.commit()
    for _ in range(10):
        _done(worker["id"], requester["id"], stars=5, earn=False)
    _grant(worker["id"], 140)
    with SessionLocal() as db:
        t = Task(creator_id=requester["id"], title="三居室深度保洁", description="", category="保洁", budget_cents=20000,
                 status="published", required_skills=["保洁"])
        db.add(t)
        db.flush()
        fit = _category_fit(db, t, [db.get(User, worker["id"]), db.get(User, requester["id"])])
    bonus, why = fit[worker["id"]]
    assert any("「保洁」专家" in w for w in why) and bonus >= FIT_TIER["expert"]
    assert requester["id"] not in fit


# ------------------------------------------------------------------ 注销与导出（INF-109）
def test_erase_and_export(client, requester, worker):
    from app.modules.account.deletion import erase_personal_data

    voucher = _skilled(client, "13900000088", "担保人")
    client.post(f"{API}/influence/vouches", json={"subject_id": worker["id"], "category": "保洁", "stake": 10}, headers=auth(voucher))
    exp = client.get(f"{API}/users/me/export", headers=auth(voucher)).json()["influence"]
    assert exp["events"] and exp["vouches"][0]["role"] == "voucher"
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, worker["id"]))
        db.commit()
        assert db.query(InfluenceVouch).one().status == "released"            # 为他作的担保释放，不罚没
        erase_personal_data(db, db.get(User, voucher["id"]))
        db.commit()
        assert db.query(InfluenceEvent).filter_by(user_id=voucher["id"]).count() == 0
        assert db.query(InfluenceVouch).count() == 0


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_responses_match_sdk_types(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_inline_shape, _assert_shape

    voucher = _skilled(client, "13900000089", "担保人")
    _grant(worker["id"], 12)
    h = auth(voucher)
    v = client.post(f"{API}/influence/vouches", json={"subject_id": worker["id"], "category": "保洁", "stake": 10, "note": "靠谱"},
                    headers=h).json()
    client.post(f"{API}/influence/jobs/snapshot", headers=JOB_HEADERS)
    mine = client.get(f"{API}/influence/me", headers=h).json()
    pub = client.get(f"{API}/users/{voucher['id']}/influence", headers=auth(requester)).json()
    worker_pub = client.get(f"{API}/users/{worker['id']}/influence", headers=auth(requester)).json()
    board = client.get(f"{API}/influence/leaderboard", params={"category": "保洁"}, headers=auth(requester)).json()
    snap = client.get(f"{API}/influence/snapshots/latest", headers=h).json()
    proof = client.get(f"{API}/influence/me/proof", headers=h).json()
    assert mine["events"] and mine["vouches_given"] and pub["categories"] and worker_pub["vouched"] and board["items"] and proof["items"]
    _assert_shape(v, "InfluenceVouchRow")
    _assert_shape(mine, "InfluenceMine")
    first_cat, first_event, first_given = mine["categories"][0], mine["events"][0], mine["vouches_given"][0]
    _assert_shape(first_cat, "InfluenceMyCategory")
    _assert_shape(first_event, "InfluenceEventRow")
    _assert_shape(first_given, "InfluenceVouchRow")
    _assert_shape(pub, "InfluencePublic")
    pub_cat, vouched = pub["categories"][0], worker_pub["vouched"][0]
    _assert_shape(pub_cat, "InfluenceCategory")
    _assert_shape(vouched, "InfluenceVouchedSummary")
    _assert_shape(board, "InfluenceLeaderboard")
    first_row = board["items"][0]
    _assert_shape(first_row, "InfluenceLeaderRow")
    _assert_shape(snap, "InfluenceLatestSnapshot")
    snap_view = snap["snapshot"]
    _assert_shape(snap_view, "InfluenceSnapshotView")
    _assert_shape(proof, "InfluenceProof")
    first_item = proof["items"][0]
    _assert_shape(first_item, "InfluenceProofItem")
    _assert_inline_shape(client.delete(f"{API}/influence/vouches/{v['id']}", headers=h).json(), "withdrawVouch")
