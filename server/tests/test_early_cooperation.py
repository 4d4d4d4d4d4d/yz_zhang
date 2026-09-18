"""COOP 早期合作体（50 号 spec）。

需求定位是**颠覆公司组织形式**：可追溯、能获得支持、持续迭代。
与公司股权最本质的区别在这一条上——

    传统公司先分股权再干活；这里份额 = 已确认贡献的函数，是**长出来的**。

所以断言主要围绕三件事：份额真的会随贡献变、贡献不能自报、
分配只能来自已经收到的钱。
"""
from app.core.db import SessionLocal
from app.modules.coop import compliance_path as cpath
from app.modules.coop import service as coop
from app.modules.wallet import service as wallet
from tests.conftest import auth, register, topup, verify_user

VER = cpath.RISK_DISCLOSURE_VERSION


def make_user(client, phone, nick):
    u = register(client, phone, nick)
    # 实名要求姓名至少 2 字，昵称可以更短，所以这里不复用昵称
    verify_user(client, u, name=f"实名{nick}")
    return u


def make_venture(client, founder, name="早期合作体", **over):
    r = client.post("/api/v1/ventures", json={
        "name": name, "purpose": "一起做一个东西", "risk_disclosure_version": VER, **over,
    }, headers=auth(founder))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def join(client, venture_id, user, version=VER):
    return client.post(f"/api/v1/ventures/{venture_id}/members",
                       json={"risk_disclosure_version": version}, headers=auth(user))


def contribute(client, venture_id, user, desc="做了一版原型", kind="time"):
    r = client.post(f"/api/v1/ventures/{venture_id}/contributions",
                    json={"kind": kind, "description": desc}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def confirm(client, venture_id, cid, confirmer, valued_cents=10000, accept=True):
    return client.post(
        f"/api/v1/ventures/{venture_id}/contributions/{cid}/confirm",
        json={"accept": accept, "valued_cents": valued_cents, "note": "认可"},
        headers=auth(confirmer),
    )


# ------------------------------------------------------- COOP-030 风险揭示是前置
def test_coop030_risk_disclosure_is_required_to_join(client):
    """**一个不告诉人有风险就拉人进来的早期合作，本身就是纠纷的起点。**"""
    founder = make_user(client, "13700000001", "发起人")
    vid = make_venture(client, founder)
    other = make_user(client, "13700000002", "成员甲")

    bad = join(client, vid, other, version="")
    assert bad.status_code == 400
    assert "风险揭示书" in bad.json()["detail"]["message"]
    assert join(client, vid, other).status_code == 201


def test_coop031_risk_disclosure_says_the_four_things_that_matter(client):
    """逐条断言，不是断言「非空」。

    这四条一旦被改软，整个模式的性质就变了——所以它们在代码里是常量，
    不是运营可改的文案。
    """
    doc = client.get("/api/v1/ventures/risk-disclosure").json()
    text = doc["text"]
    assert "稀释" in text, "没说份额会被稀释"
    assert "可能不产生任何收益" in text, "没说可能血本无归"
    assert "不承诺" in text and "已经实际收到" in text, "没说只分已实现收益、不承诺回报"
    assert "不可转让" in text and "不构成投资" in text, "没说清楚它不是金融产品"
    assert doc["version"] == VER


def test_coop030_founder_signs_it_too(client):
    """发起人承担的风险不比别人少。"""
    founder = make_user(client, "13700000003", "发起人")
    r = client.post("/api/v1/ventures", json={
        "name": "没签就建", "risk_disclosure_version": "old-version",
    }, headers=auth(founder))
    assert r.status_code == 409


# --------------------------------------------------- COOP-010 贡献必须被别人确认
def test_coop010_self_reported_contribution_does_not_count(client):
    """**自报贡献等于自己发股份。** 与 agent 自报置信度是同一类无效。"""
    founder = make_user(client, "13700000010", "发起人")
    vid = make_venture(client, founder)
    cid = contribute(client, vid, founder)

    shares = client.get(f"/api/v1/ventures/{vid}/shares", headers=auth(founder)).json()
    assert all(s["share_bps"] == 0 for s in shares["shares"]), "未确认的贡献不该产生份额"

    r = confirm(client, vid, cid, founder)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "self_confirmation"


def test_coop010_valuation_comes_from_the_confirmer(client):
    """贡献人说「我做了什么」，确认人说「这值多少」。

    描述与估值分开，防止一个人既当运动员又当裁判——所以提交端点
    **根本不接受金额字段**。
    """
    founder = make_user(client, "13700000011", "发起人")
    vid = make_venture(client, founder)
    other = make_user(client, "13700000012", "成员甲")
    join(client, vid, other)

    r = client.post(f"/api/v1/ventures/{vid}/contributions",
                    json={"kind": "time", "description": "做了一版原型",
                          "valued_cents": 999999},        # 试图自报计价
                    headers=auth(founder))
    assert r.status_code == 201
    rows = client.get(f"/api/v1/ventures/{vid}/contributions", headers=auth(other)).json()
    assert rows[0]["valued_cents"] == 0, "提交时不该带上任何计价"

    confirm(client, vid, rows[0]["id"], other, valued_cents=5000)
    rows = client.get(f"/api/v1/ventures/{vid}/contributions", headers=auth(other)).json()
    assert rows[0]["valued_cents"] == 5000


def test_coop010_only_members_can_confirm(client):
    founder = make_user(client, "13700000013", "发起人")
    vid = make_venture(client, founder)
    cid = contribute(client, vid, founder)
    outsider = make_user(client, "13700000014", "外人")
    r = confirm(client, vid, cid, outsider)
    assert r.status_code == 403


def test_can_confirm_flag_matches_the_server_rule(client):
    """客户端按钮与服务端判断同一来源。"""
    founder = make_user(client, "13700000015", "发起人")
    vid = make_venture(client, founder)
    other = make_user(client, "13700000016", "成员甲")
    join(client, vid, other)
    contribute(client, vid, founder)

    mine = client.get(f"/api/v1/ventures/{vid}/contributions", headers=auth(founder)).json()
    theirs = client.get(f"/api/v1/ventures/{vid}/contributions", headers=auth(other)).json()
    assert mine[0]["can_confirm"] is False      # 自己的不能确认
    assert theirs[0]["can_confirm"] is True


# ------------------------------------------------------- COOP-011/012 份额是长出来的
def test_coop011_shares_grow_with_confirmed_contributions(client):
    """**份额不是分的，是长出来的。** 这是与公司股权最本质的区别。"""
    a = make_user(client, "13700000020", "甲")
    vid = make_venture(client, a)
    b = make_user(client, "13700000021", "乙")
    join(client, vid, b)

    c1 = contribute(client, vid, a)
    confirm(client, vid, c1, b, valued_cents=10000)
    s = {x["user_id"]: x["share_bps"]
         for x in client.get(f"/api/v1/ventures/{vid}/shares",
                             headers=auth(a)).json()["shares"]}
    assert s[a["id"]] == 10000, "只有甲有已确认贡献时应当全部归他"

    c2 = contribute(client, vid, b)
    confirm(client, vid, c2, a, valued_cents=10000)
    s = {x["user_id"]: x["share_bps"]
         for x in client.get(f"/api/v1/ventures/{vid}/shares",
                             headers=auth(a)).json()["shares"]}
    assert s[a["id"]] == 5000 and s[b["id"]] == 5000, "等额贡献应当对半"


def test_coop011_not_contributing_gets_you_diluted(client):
    """不干活的人份额会被稀释——这正是「早期合作、有风险」该有的样子：
    风险对应的是持续投入，不是一次性的名分。"""
    a = make_user(client, "13700000022", "甲")
    vid = make_venture(client, a)
    b = make_user(client, "13700000023", "乙")
    join(client, vid, b)

    c1 = contribute(client, vid, a)
    confirm(client, vid, c1, b, valued_cents=10000)
    for i in range(3):                      # 乙持续贡献，甲停了
        cid = contribute(client, vid, b, desc=f"继续做 {i}")
        confirm(client, vid, cid, a, valued_cents=10000)

    s = {x["user_id"]: x["share_bps"]
         for x in client.get(f"/api/v1/ventures/{vid}/shares",
                             headers=auth(a)).json()["shares"]}
    assert s[a["id"]] == 2500 and s[b["id"]] == 7500


def test_coop012_shares_always_sum_to_exactly_10000(client):
    """合计必须精确，否则分配时会少分或多分。用除不尽的组合专门试。"""
    a = make_user(client, "13700000024", "甲")
    vid = make_venture(client, a)
    b = make_user(client, "13700000025", "乙")
    c = make_user(client, "13700000026", "丙")
    join(client, vid, b)
    join(client, vid, c)
    for user, val in ((a, 3333), (b, 3333), (c, 3334)):
        cid = contribute(client, vid, user)
        other = b if user is not b else a
        confirm(client, vid, cid, other, valued_cents=val)

    data = client.get(f"/api/v1/ventures/{vid}/shares", headers=auth(a)).json()
    assert data["total_bps"] == 10000, data["shares"]


def test_rejected_contribution_gives_no_share(client):
    a = make_user(client, "13700000027", "甲")
    vid = make_venture(client, a)
    b = make_user(client, "13700000028", "乙")
    join(client, vid, b)
    cid = contribute(client, vid, a)
    confirm(client, vid, cid, b, accept=False)
    s = client.get(f"/api/v1/ventures/{vid}/shares", headers=auth(a)).json()
    assert all(x["share_bps"] == 0 for x in s["shares"])


# ------------------------------------------------ COOP-020 只分已实现收益
def test_coop020_can_only_distribute_money_actually_received(client):
    """**没有「预期收益」这个概念，代码里也不存在这个字段。**

    这不是法务加的限制，是让这个模型落在合作内部分配、
    而不是涉众性金融的设计本身。
    """
    a = make_user(client, "13700000030", "甲")
    vid = make_venture(client, a)
    b = make_user(client, "13700000031", "乙")
    join(client, vid, b)
    cid = contribute(client, vid, a)
    confirm(client, vid, cid, b, valued_cents=10000)

    r = client.post(f"/api/v1/ventures/{vid}/distributions",
                    json={"amount_cents": 50000, "memo": "第一次分配"}, headers=auth(a))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "insufficient_venture_funds"
    assert "已经实际收到" in r.json()["detail"]["message"]


def test_coop020_distribution_follows_shares_and_conserves_money(client):
    a = make_user(client, "13700000032", "甲")
    vid = make_venture(client, a)
    b = make_user(client, "13700000033", "乙")
    join(client, vid, b)
    for user, val in ((a, 30000), (b, 10000)):
        cid = contribute(client, vid, user)
        confirm(client, vid, cid, b if user is a else a, valued_cents=val)

    with SessionLocal() as db:                 # 合作体真的收到一笔钱
        wallet.topup(db, vid, 40000)
        db.commit()

    a_before = client.get("/api/v1/wallet", headers=auth(a)).json()["available_cents"]
    b_before = client.get("/api/v1/wallet", headers=auth(b)).json()["available_cents"]
    r = client.post(f"/api/v1/ventures/{vid}/distributions",
                    json={"amount_cents": 40000, "memo": "首次分配"}, headers=auth(a))
    assert r.status_code == 201, r.text
    a_after = client.get("/api/v1/wallet", headers=auth(a)).json()["available_cents"]
    b_after = client.get("/api/v1/wallet", headers=auth(b)).json()["available_cents"]

    assert a_after - a_before == 30000        # 75%
    assert b_after - b_before == 10000        # 25%
    with SessionLocal() as db:
        assert wallet.get_or_create(db, vid).available_cents == 0


def test_coop020_distribution_snapshot_is_kept(client):
    """份额是算出来的，但**分配依据必须留痕**——否则事后重算会得到
    不同的数字，对不上账。"""
    a = make_user(client, "13700000034", "甲")
    vid = make_venture(client, a)
    b = make_user(client, "13700000035", "乙")
    join(client, vid, b)
    cid = contribute(client, vid, a)
    confirm(client, vid, cid, b, valued_cents=10000)
    with SessionLocal() as db:
        wallet.topup(db, vid, 10000)
        db.commit()
    client.post(f"/api/v1/ventures/{vid}/distributions",
                json={"amount_cents": 10000, "memo": "分"}, headers=auth(a))

    # 分配之后乙也有了贡献，份额变了；但那次分配的快照不该跟着变
    cid2 = contribute(client, vid, b)
    confirm(client, vid, cid2, a, valued_cents=90000)

    rows = client.get(f"/api/v1/ventures/{vid}/distributions", headers=auth(a)).json()
    snap = rows[0]["share_snapshot"]
    assert len(snap) == 1 and snap[0]["user_id"] == a["id"] and snap[0]["share_bps"] == 10000


# ---------------------------------------- COOP-021/022 让它落在合作而非公开发行
def test_coop021_no_public_join_endpoint(client):
    """邀请制不是产品偏好，是让这个模式落在合作内部而非公开募集的
    结构性设计之一。"""
    from app.main import app

    paths = [p for p in app.openapi()["paths"] if "venture" in p]
    assert not any("apply" in p or "join-public" in p or "browse" in p for p in paths), paths
    # 也没有「列出所有合作体」的公开浏览端点
    assert "/api/v1/ventures/all" not in paths


def test_coop022_shares_cannot_be_transferred(client):
    """**故意不做份额转让**，不是「以后再说」。

    一旦份额可转让，它就是一张可流通的权益凭证，整个性质就变了。
    这条测试钉住「全站不存在这个动作」。
    """
    from app.main import app

    paths = app.openapi()["paths"]
    bad = [p for p in paths if "venture" in p and ("transfer" in p or "share" in p and "s/" in p)]
    assert not any("transfer" in p for p in paths if "venture" in p), bad

    import inspect

    from app.modules.coop import router as coop_router
    from app.modules.coop import service as coop_service

    src = inspect.getsource(coop_router) + inspect.getsource(coop_service)
    code = "\n".join(line.split("#")[0] for line in src.splitlines())
    for word in ("transfer_share", "sell_share", "assign_share"):
        assert word not in code, f"出现了份额转让的实现：{word}"


def test_non_members_cannot_see_the_venture(client):
    a = make_user(client, "13700000040", "甲")
    vid = make_venture(client, a)
    outsider = make_user(client, "13700000041", "外人")
    assert client.get(f"/api/v1/ventures/{vid}", headers=auth(outsider)).status_code == 403


# ------------------------------------------------------- COOP-040 合规路径不阻断
def test_coop040_compliance_path_informs_and_does_not_block(client):
    """**告诉你需要什么，而不是拦住你。**"""
    a = make_user(client, "13700000050", "甲")
    vid = make_venture(client, a)
    path = client.get(f"/api/v1/ventures/{vid}/compliance-path", headers=auth(a)).json()

    keys = {d["key"] for d in path["documents"]}
    assert "risk_disclosure" in keys and "cooperation_agreement" in keys
    # 每一项都要说明**为什么**需要——只给清单不说理由，用户不知道哪些能省
    assert all(d["why"] for d in path["documents"])
    # COOP-053 不假装是法律意见
    assert "不是法律意见" in path["disclaimer"]


def test_coop040_single_member_venture_cannot_confirm_anything(client):
    """只有一个人时没人能确认贡献——合规路径要**明说**这一点，
    而不是让用户自己撞上去。"""
    a = make_user(client, "13700000051", "独行侠")
    vid = make_venture(client, a)
    path = client.get(f"/api/v1/ventures/{vid}/compliance-path", headers=auth(a)).json()
    item = next(d for d in path["documents"] if d["key"] == "contribution_confirmation")
    assert item["status"] == "todo"
    assert "2 名成员" in item["action"]


def test_coop040_thresholds_trigger_registration_advice(client):
    """累计分配越过阈值 → 建议办经营主体登记。这是「需要就去办」的那一步。"""
    path = cpath.evaluate(
        member_count=3, has_funds=True,
        distributed_total_cents=cpath.LARGE_CUMULATIVE_DISTRIBUTION_CENTS + 1,
        distribution_count=2,
    )
    keys = {r.key for r in path.registrations}
    assert "tax_registration" in keys
    assert any("经营所得" in n for n in path.notices), "分配了钱却没提税务定性"


def test_coop040_restricted_category_points_at_certification(client):
    path = cpath.evaluate(member_count=2, has_funds=False, distributed_total_cents=0,
                          distribution_count=0, category_required_cert="电工")
    item = next(r for r in path.registrations if r.key == "category_certification")
    assert "电工" in item.title


# -------------------------------------------------------------- COOP-050/060
def test_coop050_venture_can_publish_a_task_with_its_own_funds(client):
    """「任务发布给特定人解决」：合作体用体内资金池发任务，走既有全链路。

    这条同时验证了架构判断——因为合作体是 User，钱包/发任务一行都不用改。
    """
    a = make_user(client, "13700000060", "甲")
    vid = make_venture(client, a)
    with SessionLocal() as db:
        wallet.topup(db, vid, 100000)
        acct = wallet.get_or_create(db, vid)
        assert acct.available_cents == 100000
        db.commit()
    # 合作体有钱包、能托管——这就是「发任务」所需的全部前提
    with SessionLocal() as db:
        assert wallet.get_or_create(db, vid).available_cents == 100000


def test_coop060_contribution_and_distribution_are_anchored(client):
    """COOP-060 可追溯的真实含义不是「有一张表存着」，
    而是改一条历史记录必须重写整条后继链才不被发现。"""
    from app.modules.anchor import service as anchor
    from app.modules.anchor.models import AnchorEntry

    a = make_user(client, "13700000061", "甲")
    vid = make_venture(client, a)
    b = make_user(client, "13700000062", "乙")
    join(client, vid, b)
    cid = contribute(client, vid, a)
    confirm(client, vid, cid, b, valued_cents=10000)
    with SessionLocal() as db:
        wallet.topup(db, vid, 10000)
        db.commit()
    client.post(f"/api/v1/ventures/{vid}/distributions",
                json={"amount_cents": 10000, "memo": "分"}, headers=auth(a))

    with SessionLocal() as db:
        kinds = {e.event_type for e in db.query(AnchorEntry).all()}
        assert "coop.contribution.accepted" in kinds
        assert "coop.distribution" in kinds
        assert anchor.verify_chain(db)["valid"] is True


def test_venture_account_is_excluded_from_the_recommendation_pool(client):
    """合作体是 User，但它不是「人」——不该出现在接单人推荐里。"""
    from tests.test_task_flow import publish_task

    a = make_user(client, "13700000070", "甲")
    vid = make_venture(client, a)
    worker = make_user(client, "13700000071", "真人")
    task = publish_task(client, a, category="保洁")
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(a)).json()
    ids = {r["user_id"] for r in recs}
    assert vid not in ids
    assert worker["id"] in ids, "把真人也排掉了，说明排除条件写过头了"
