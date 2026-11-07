"""OUT-050 浮动对价分档（443 号 spec，V470）。

52 号只做了一档：平台判定指标全部通过才加付，差一条就一分不加。三条指标做到两条的人和一条都没做的人拿的一样，
「做得好多给钱」就成了「做到满分才给钱」。分档：「通过至少 k 条平台判定指标，加付 X 元」，取达到的最高一档、不累加。
规则：档位按条数和金额都严格递增；够不着的档不许发；最高一档就是托管上限（OUT-002/003）；
没达到的差额原路退回发布方，资金守恒；分档随已签署的合同走（IPC-003）。
"""
from app.core.db import SessionLocal
from tests.conftest import auth, make_admin, topup
from tests.test_ip_and_outcome_pricing import publish
from tests.test_task_flow import match_and_fund

CRITERIA = [
    {"text": "交付说明写明「已自测」", "kind": "auto", "check": {"op": "contains", "value": "已自测"}},
    {"text": "交付说明写明「已附文档」", "kind": "auto", "check": {"op": "contains", "value": "已附文档"}},
    {"text": "交付说明写明「已部署」", "kind": "auto", "check": {"op": "contains", "value": "已部署"}},
    {"text": "整体观感", "kind": "manual"},
]
TIERS = [{"min_passed": 1, "bonus_cents": 2000}, {"min_passed": 2, "bonus_cents": 5000}, {"min_passed": 3, "bonus_cents": 9000}]


def tiered(client, requester, **over):
    body = {"pricing": "outcome", "budget_cents": 20000, "acceptance_criteria": CRITERIA, "bonus_tiers": TIERS, **over}
    return publish(client, requester, **body)


def _run(client, requester, worker, note, **over):
    task = tiered(client, requester, **over).json()
    cid = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", json={"note": note}, headers=auth(worker))
    r0 = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    w0 = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester)).status_code == 200
    r1 = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    w1 = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    return task, cid, r1 - r0, w1 - w0


def test_publishing_fills_the_cap_from_the_top_tier_and_shows_the_tiers(client, requester):
    r = tiered(client, requester)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["bonus_cents"] == 9000 and t["bonus_tiers"] == TIERS
    got = client.get(f"/api/v1/tasks/{t['id']}", headers=auth(requester)).json()
    assert got["bonus_tiers"] == TIERS, "执行方报名前就要看得到分档"


def test_bad_tiers_are_refused_with_the_reason(client, requester):
    cases = [
        ([{"min_passed": 2, "bonus_cents": 2000}, {"min_passed": 1, "bonus_cents": 5000}], {}, "bonus_tiers_not_increasing"),
        ([{"min_passed": 1, "bonus_cents": 5000}, {"min_passed": 2, "bonus_cents": 5000}], {}, "bonus_tiers_not_increasing"),
        ([{"min_passed": 1, "bonus_cents": 2000}, {"min_passed": 4, "bonus_cents": 5000}], {}, "bonus_tier_unreachable"),
        (TIERS, {"bonus_cents": 5000}, "bonus_tiers_mismatch"),
        ([{"min_passed": 3, "bonus_cents": 30000}], {}, "bonus_too_large"),        # 最高一档也受「不超过基础报酬」管
    ]
    for tiers, extra, code in cases:
        r = tiered(client, requester, bonus_tiers=tiers, **extra)
        assert r.status_code == 400 and r.json()["detail"]["code"] == code, (tiers, r.text)
    assert "只有 3 条" in tiered(client, requester, bonus_tiers=cases[2][0]).json()["detail"]["message"]
    r = publish(client, requester, pricing="fixed", bonus_tiers=TIERS)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bonus_not_allowed"


def test_escrow_is_the_top_tier_and_payout_follows_the_tier_reached(client, requester, worker):
    topup(client, requester, 500000)
    topup(client, worker, 50000)
    # 通过两条：拿第二档 5000，差额 4000 退回发布方
    task, cid, back, got = _run(client, requester, worker, "已自测，已附文档")
    c = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()
    assert c["amount_cents"] == 29000, "托管 = 基础 20000 + 最高一档 9000"
    assert back == 4000, back
    assert 20000 + 5000 > got > (20000 + 5000) * 0.85, got     # 扣佣金后到账
    # 一条都没通过：一分不加，9000 全退
    _, _, back, got = _run(client, requester, worker, "做完了", title="零条")
    assert back == 9000 and got < 20000
    # 三条全过：拿满 9000，不退
    _, _, back, got = _run(client, requester, worker, "已自测，已附文档，已部署", title="三条")
    assert back == 0 and got > 29000 * 0.85


def test_money_is_conserved_and_terms_spell_out_every_tier(client, requester, worker):
    admin = make_admin(client, "13400000470")
    topup(client, requester, 500000)
    topup(client, worker, 50000)
    for note, title in (("已自测", "一条"), ("已自测，已附文档", "两条"), ("做完了", "没过")):
        _run(client, requester, worker, note, title=title)
    rec = client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()
    assert rec["ok"] is True, rec["mismatches"]
    task = tiered(client, requester, title="看条款").json()
    cid = match_and_fund(client, requester, worker, task)
    terms = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()["terms"]
    assert "分档加付" in terms and "取达到的最高一档、不累加" in terms and "不随任何收益浮动" in terms
    assert "通过至少 1 条平台判定指标，加付 20.00 元" in terms and "通过至少 3 条平台判定指标，加付 90.00 元" in terms
    assert "差额原路退回发布方" in terms


def test_tiers_follow_the_signed_contract_not_later_task_edits(client, requester, worker):
    """IPC-003 同理：签约后偷偷把任务的分档改成「三条才给、只给 1 元」，这一单照签约时的分档付。"""
    from app.modules.task.models import Task

    topup(client, requester, 500000)
    topup(client, worker, 50000)
    task = tiered(client, requester).json()
    match_and_fund(client, requester, worker, task)
    with SessionLocal() as db:
        db.get(Task, task["id"]).bonus_tiers = [{"min_passed": 3, "bonus_cents": 100}]
        db.commit()
    client.post(f"/api/v1/tasks/{task['id']}/deliver", json={"note": "已自测，已附文档"}, headers=auth(worker))
    r0 = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    r1 = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    assert r1 - r0 == 4000, "退回的差额应按签约时的分档算（两条拿 5000，退 4000）"


def test_single_tier_outcome_pricing_is_unchanged(client, requester, worker):
    """不给分档的老写法照旧：全部通过付全额，否则全退（52 号的测试也照跑）。"""
    topup(client, requester, 500000)
    topup(client, worker, 50000)
    task = publish(client, requester, pricing="outcome", budget_cents=20000, bonus_cents=5000,
                   acceptance_criteria=CRITERIA[:2]).json()
    assert task["bonus_tiers"] == []
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", json={"note": "已自测"}, headers=auth(worker))
    r0 = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    r1 = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    assert r1 - r0 == 5000, "两条只过一条：没分档的照旧全退"
