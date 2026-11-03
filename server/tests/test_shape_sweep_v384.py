"""CLI-083b 响应形状棘轮再降一批（357 号 spec，V384）。

静态读不出键的调用点（返回 `dump_xxx(...)`、变量、展开）没有任何形状检查时，SDK 声明与服务端真实返回可以悄悄分叉。
这里对一批**每天都会走到**的接口（我的账户、钱包、协议与同意、私聊、圈子、团队、合作体、后台看板）跑一遍真实请求，
用 `_assert_shape` / `_assert_inline_shape` 三个方向比：声明了没给、给了没声明、类型对不上。
"""
from tests.conftest import auth, bind_payout, make_admin, money
from tests.test_client_shape_alignment import _assert_inline_shape, _assert_shape

API = "/api/v1"


def _first(rows):
    assert isinstance(rows, list) and rows, rows
    return rows[0]


def test_my_account_shapes(client, requester):
    h = auth(requester)
    got = client.get(f"{API}/users/me", headers=h).json()
    _assert_shape(got, "Me")
    got = client.patch(f"{API}/users/me", json={"bio": "做木工十年"}, headers=h).json()
    _assert_shape(got, "Me")
    got = client.get(f"{API}/me/referrals", headers=h).json()
    _assert_inline_shape(got, "myReferrals")
    got = client.get(f"{API}/me/newcomer", headers=h).json()
    _assert_inline_shape(got, "newcomerProgress")
    got = client.get(f"{API}/finance/my-tax", headers=h).json()
    _assert_shape(got, "TaxSummary")
    got = client.get(f"{API}/legal/agreements", headers=h).json()
    _assert_shape(got, "AgreementStatus")
    got = client.post(f"{API}/legal/agreements/accept", headers=h).json()
    _assert_inline_shape(got, "acceptAgreements")
    got = client.post(f"{API}/legal/consents/location/grant", headers=h).json()
    _assert_inline_shape(got, "grantConsent")
    got = client.post(f"{API}/legal/consents/location/revoke", headers=h).json()
    _assert_inline_shape(got, "revokeConsent")
    got = client.post(f"{API}/auth/send-code", json={"phone": "13800038401"}).json()
    _assert_inline_shape(got, "sendSmsCode")


def test_wallet_shapes(client, requester):
    h = auth(requester)
    bind_payout(client, requester)
    r = client.post(f"{API}/wallet/topup", json={"amount_cents": 50000}, headers=money(h))
    assert r.status_code == 200, r.text
    _assert_inline_shape(r.json(), "topup")
    w = client.post(f"{API}/wallet/withdraw", json={"amount_cents": 1000}, headers=money(h))
    assert w.status_code == 200, w.text
    _assert_inline_shape(w.json(), "withdraw")


def test_space_shapes(client, requester, worker):
    h = auth(requester)
    own = client.get(f"{API}/spaces/me", headers=h).json()
    _assert_shape(own, "OwnSpace")
    saved = client.put(f"{API}/spaces/me", json={"revision": own["revision"], "headline": "木工", "published": True}, headers=h)
    assert saved.status_code == 200, saved.text
    _assert_shape(saved.json(), "OwnSpace")
    got = client.get(f"{API}/spaces/{requester['id']}", headers=auth(worker)).json()
    _assert_shape(got, "PersonalSpace")


def test_social_shapes(client, requester, worker):
    a = auth(requester)
    conv = client.post(f"{API}/conversations/direct", json={"user_id": worker["id"]}, headers=a)
    assert conv.status_code in (200, 201), conv.text
    _assert_shape(conv.json(), "Conversation")
    sent = client.post(f"{API}/conversations/{conv.json()['id']}/messages", json={"content": "你好"}, headers=a)
    _assert_inline_shape(sent.json(), "sendMessage")
    circle = client.post(f"{API}/circles", json={"name": "木工圈", "kind": "interest"}, headers=a)
    assert circle.status_code in (200, 201), circle.text
    _assert_shape(circle.json(), "CircleInfo")
    got = client.get(f"{API}/circles/{circle.json()['id']}", headers=a).json()
    _assert_shape(got, "CircleInfo")
    got = _first(client.get(f"{API}/circles", headers=a).json())
    _assert_shape(got, "CircleInfo")
    got = _first(client.get(f"{API}/circles/{circle.json()['id']}/members", headers=a).json())
    _assert_inline_shape(got, "circleMembers")


def test_team_and_venture_shapes(client, requester):
    h = auth(requester)
    team = client.post(f"{API}/teams", json={"name": "木工队"}, headers=h)
    assert team.status_code in (200, 201), team.text
    _assert_shape(team.json(), "TeamView")


def test_admin_board_shapes(client, requester, worker):
    from tests.conftest import topup
    from tests.test_on_behalf import _post
    from tests.test_task_flow import match_and_fund

    admin = make_admin(client, "13600038401")
    h = auth(admin)
    # 一份在途合约：封禁影响里的合约列表不能是空的，否则嵌套形状比不到
    topup(client, requester, 40000)
    match_and_fund(client, requester, worker, _post(client, requester).json())
    got = client.get(f"{API}/admin/platform-finance", headers=h).json()
    _assert_shape(got, "PlatformFinanceView")
    got = client.get(f"{API}/admin/security", headers=h).json()
    _assert_shape(got, "SecurityBoardView")
    got = client.get(f"{API}/admin/users/{requester['id']}/ban-impact", headers=h).json()
    _assert_shape(got, "BanImpactView")
    assert got["in_flight_contracts"], "要有一份在途合约，嵌套的 BanImpactContract 才比得到"
    got = client.get(f"{API}/admin/north-star", headers=h).json()
    _assert_inline_shape(got, "northStar")
    got = client.get(f"{API}/admin/market-health", headers=h).json()
    _assert_inline_shape(got, "marketHealth")


def test_people_and_lists_shapes(client, requester, worker):
    from tests.test_friends_and_groups import decide, friend_request
    from tests.test_on_behalf import _post
    from tests.test_task_flow import match_and_fund

    a, b = auth(requester), auth(worker)
    req = friend_request(client, requester, worker["id"], remark="木工师傅").json()
    decide(client, worker, req["id"])
    friends = client.get(f"{API}/friends", headers=a).json()
    _assert_inline_shape(_first(friends), "friends")
    t = _post(client, requester).json()
    inv = client.post(f"{API}/tasks/{t['id']}/invitations", json={"user_id": worker["id"]}, headers=a)
    assert inv.status_code in (200, 201), inv.text
    invitations = client.get(f"{API}/invitations", headers=b).json()
    _assert_shape(_first(invitations), "InvitationItem")
    from tests.conftest import topup

    topup(client, requester, 40000)
    contract_id = match_and_fund(client, requester, worker, t)
    apps = client.get(f"{API}/users/me/applications", headers=b).json()
    _assert_inline_shape(_first(apps), "myApplications")
    sigs = client.get(f"{API}/contracts/{contract_id}/signatures", headers=a).json()
    _assert_shape(sigs, "SignatureReport")
    convs = client.get(f"{API}/conversations", headers=a).json()
    _assert_shape(_first(convs), "ConversationListItem")
    client.post(f"{API}/tasks/{t['id']}/deliver", headers=b)
    client.post(f"{API}/tasks/{t['id']}/accept-delivery", headers=a)
    r = client.post(f"{API}/tasks/{t['id']}/reviews", json={"stars": 5, "tags": [], "comment": "好"}, headers=a)
    assert r.status_code in (200, 201), r.text
    reviews = client.get(f"{API}/tasks/{t['id']}/reviews", headers=a).json()
    _assert_inline_shape(_first(reviews), "listReviews")
    worked = client.get(f"{API}/friends/worked-with", headers=a).json()
    _assert_inline_shape(_first(worked), "workedWith")


def test_my_teams_and_ventures_shapes(client):
    from tests.test_early_cooperation import make_user, make_venture

    founder = make_user(client, "13800238401", "阿青")
    make_venture(client, founder, name="社区咖啡")
    mine = client.get(f"{API}/ventures/mine", headers=auth(founder)).json()
    _assert_shape(_first(mine), "MyVentureRow")
    client.post(f"{API}/teams", json={"name": "咖啡队"}, headers=auth(founder))
    teams = client.get(f"{API}/teams/mine", headers=auth(founder)).json()
    _assert_shape(_first(teams), "MyTeamRow")


# ------------------------------------------------------------------ V386（359 号 spec）第三批
def test_compliance_and_moderation_shapes(client, requester):
    from tests.test_aml import funded_user, withdraw

    admin = make_admin(client, "13600038601")
    h = auth(admin)
    user = funded_user(client, "13900038601")
    withdraw(client, user, 999900)
    withdraw(client, user, 999900)
    listing = client.get(f"{API}/admin/aml/activities", headers=h).json()
    _assert_inline_shape(listing, "amlActivities")
    _assert_shape(_first(listing["items"]), "SuspiciousActivityRow")
    reviewed = client.post(f"{API}/admin/aml/activities/{listing['items'][0]['id']}/review",
                           json={"decision": "to_report", "note": "已核实，报合规官"}, headers=h).json()
    _assert_inline_shape(reviewed, "reviewAmlActivity")
    stats = client.get(f"{API}/admin/aml/stats", headers=h).json()
    _assert_shape(stats, "AmlStats")
    banned = client.post(f"{API}/admin/users/{requester['id']}/ban", headers=h).json()
    _assert_inline_shape(banned, "banUser")


def test_certification_queue_shapes(client):
    from tests.test_certification import apply_cert, make_verified

    admin = make_admin(client, "13600038602")
    w = make_verified(client, "13600038603")
    apply_cert(client, w, name="健康证明")
    pending = client.get(f"{API}/admin/certifications/pending", headers=auth(admin)).json()
    _assert_shape(_first(pending), "PendingCertificationRow")
    rows = client.get(f"{API}/admin/certifications?status=pending", headers=auth(admin)).json()
    _assert_shape(_first(rows), "PendingCertificationRow")


def test_anchor_shapes(client, requester, worker):
    from tests.test_anchor_chain import _build_chain

    contract_id = _build_chain(client, requester, worker)
    verify = client.get(f"{API}/anchors/verify").json()
    _assert_inline_shape(verify, "verifyAnchorChain")
    coverage = client.get(f"{API}/anchors/coverage", headers=auth(requester)).json()
    _assert_shape(coverage, "AnchorCoverage")
    chain = client.get(f"{API}/anchors/blockchain", headers=auth(requester)).json()
    _assert_inline_shape(chain, "blockchainStatus")
    anchors = client.get(f"{API}/anchors/contracts/{contract_id}", headers=auth(requester)).json()
    _assert_inline_shape(_first(anchors), "contractAnchors")


def test_venture_governance_shapes(client):
    from tests.test_organization_records import body
    from tests.test_payout_governance import setup, vote

    a, b, vid, base, proposal = setup(client)
    _assert_shape(proposal, "PayoutProposalView")
    voted = vote(client, base, b, proposal).json()
    _assert_shape(voted, "PayoutProposalView")
    proposals = client.get(f"{base}/payout-proposals", headers=auth(a)).json()
    _assert_shape(_first(proposals), "PayoutProposalView")
    rec = client.post(f"{base}/organization-records", headers=auth(a), json=body(a))
    assert rec.status_code == 201, rec.text
    record = rec.json()
    _assert_shape(record, "OrganizationRecordView")
    records = client.get(f"{base}/organization-records", headers=auth(a)).json()
    _assert_shape(_first(records), "OrganizationRecordView")


def test_new_venture_and_team_spend_shapes(client):
    from tests.test_early_cooperation import VER, make_user
    from tests.test_team_spend_return import _setup

    founder = make_user(client, "13800238601", "阿青")
    r = client.post(f"{API}/ventures", json={"name": "社区面包", "purpose": "一起做", "risk_disclosure_version": VER},
                    headers=auth(founder))
    assert r.status_code == 201, r.text
    venture = r.json()
    _assert_shape(venture, "VentureView")
    owner, staff, team_id, _ = _setup(client, "86")
    req = client.post(f"{API}/teams/{team_id}/spends", json={"amount_cents": 1000, "purpose": "打印"}, headers=auth(staff))
    assert req.status_code == 201, req.text
    spend = req.json()
    _assert_inline_shape(spend, "requestTeamSpend")
    # 超出额度的一笔：进审批 → 所有者批准 → 申请人执行
    big = client.post(f"{API}/teams/{team_id}/spends", json={"amount_cents": 30000, "purpose": "采购"}, headers=auth(staff)).json()
    assert big["needed_approval"] is True and big["reason"], big
    _assert_inline_shape(big, "requestTeamSpend")
    client.post(f"{API}/teams/{team_id}/spends/{big['id']}/decide", json={"approve": True, "reason": "同意"}, headers=auth(owner))
    ex = client.post(f"{API}/teams/{team_id}/spends/{big['id']}/execute", headers=auth(staff))
    assert ex.status_code == 200, ex.text
    executed = ex.json()
    _assert_inline_shape(executed, "executeTeamSpend")


def test_machine_mandate_shapes(client):
    from tests.test_machine_delegation import setup

    user, key, _ = setup(client)
    got = client.get(f"{API}/developer/api-keys/{key['id']}/mandate", headers=auth(user)).json()
    _assert_shape(got, "MachineMandateView")


# ------------------------------------------------------------------ V388（361 号 spec）第四批：交叉类型
def test_intersection_typed_task_and_contract_shapes(client, requester, worker):
    from tests.conftest import topup
    from tests.test_on_behalf import _post

    created = _post(client, requester).json()
    _assert_inline_shape(created, "createTask")
    topup(client, requester, 40000)
    app_id = client.post(f"{API}/tasks/{created['id']}/applications", json={"message": "有经验"}, headers=auth(worker)).json()["id"]
    contract_id = client.post(f"{API}/applications/{app_id}/accept", headers=auth(requester)).json()["contract_id"]
    for u in (requester, worker):
        client.post(f"{API}/contracts/{contract_id}/sign", headers=auth(u))
    f = client.post(f"{API}/contracts/{contract_id}/fund", headers=auth(requester))
    assert f.status_code == 200, f.text
    funded = f.json()
    _assert_inline_shape(funded, "fundContract")


def test_mission_shapes(client, requester, monkeypatch):
    from tests.test_mission_method import _create

    m = _create(client, requester)
    assert m.status_code == 201, m.text
    mid = m.json()["id"]
    detail = client.get(f"{API}/missions/{mid}", headers=auth(requester)).json()
    _assert_inline_shape(detail, "getMission")
    ticked = client.post(f"{API}/missions/{mid}/tick", headers=auth(requester)).json()
    _assert_shape(ticked, "MissionTickResult")
    cancelled = client.post(f"{API}/missions/{mid}/cancel", headers=auth(requester)).json()
    _assert_inline_shape(cancelled, "cancelMission")


def test_dispute_settlement_shapes(client, requester, worker):
    from tests.test_im_dispute_support import _open_dispute

    _task, dispute = _open_dispute(client, requester, worker)
    proposed = client.post(f"{API}/disputes/{dispute['id']}/settlement", json={"executor_share_bps": 5000},
                           headers=auth(requester)).json()
    _assert_shape(proposed, "Dispute")
    accepted = client.post(f"{API}/disputes/{dispute['id']}/settlement/accept", headers=auth(worker)).json()
    _assert_shape(accepted, "Dispute")


def test_content_comment_and_template_shapes(client, requester, worker):
    post = client.post(f"{API}/contents", json={"kind": "post", "body": "今天的作品"}, headers=auth(requester))
    assert post.status_code == 201, post.text
    cid = post.json()["id"]
    client.post(f"{API}/contents/{cid}/comments", json={"body": "做得好"}, headers=auth(worker))
    comments = client.get(f"{API}/contents/{cid}/comments", headers=auth(worker)).json()
    _assert_inline_shape(_first(comments), "contentComments")
    templates = client.get(f"{API}/knowledge/templates?category=保洁", headers=auth(requester)).json()
    _assert_inline_shape(templates, "decompositionTemplate")


# ------------------------------------------------------------------ V390（363 号 spec）第五批：null / 联合 / Partial
def test_agent_run_and_verification_order_shapes(client, requester):
    from app.modules.agent.runner import set_runner
    from tests.test_agent_delivery_closure import agent_task
    from tests.test_agent_execution import FakeRunner, make_agent
    from tests.test_verification_escalation import make_verifier

    runner = FakeRunner()
    set_runner(runner)
    try:
        admin = make_admin(client, "13800039001")
        agent_id = make_agent(client, admin, confidence_threshold_bps=9000)
        task, _, _ = agent_task(client, requester, admin, agent_id=agent_id)
        runner.confidence_bps = 4000
        r = client.post(f"{API}/tasks/{task['id']}/agent-run", headers=auth(requester))
        assert r.status_code == 201, r.text
        ran = r.json()
        _assert_inline_shape(ran, "runAgent")
        order = client.post(f"{API}/tasks/{task['id']}/verification", headers=auth(requester)).json()
        verifier = make_verifier(client, "13800039002")
        open_orders = client.get(f"{API}/verification-orders", headers=auth(verifier)).json()
        _assert_inline_shape(_first(open_orders), "openVerificationOrders")
        detail = client.get(f"{API}/verification-orders/{order['id']}", headers=auth(requester)).json()
        _assert_shape(detail, "VerificationOrderDetail")
        client.post(f"{API}/verification-orders/{order['id']}/claim", headers=auth(verifier))
        out = client.post(f"{API}/verification-orders/{order['id']}/outcome",
                          json={"outcome": "approved", "comment": "抽查三处，结论无误"}, headers=auth(verifier))
        assert out.status_code == 200, out.text
        outcome = out.json()
        _assert_inline_shape(outcome, "submitVerificationOutcome")
    finally:
        set_runner(None)


def test_appeal_profile_and_platform_settle_shapes(client, requester, worker):
    from tests.conftest import topup
    from tests.test_dispute_client_loop import open_dispute
    from tests.test_task_flow import match_and_fund, publish_task

    admin = make_admin(client, "13800039003")
    _task, dispute = open_dispute(client, requester, worker)
    did = dispute["id"]
    client.post(f"{API}/disputes/{did}/statements", json={"content": "我方陈述如下。"}, headers=auth(worker))
    client.post(f"{API}/disputes/{did}/verdict", json={"executor_share_bps": 3000, "reason": "交付部分达标"}, headers=auth(admin))
    a = client.post(f"{API}/disputes/{did}/appeal", headers=auth(worker))
    assert a.status_code == 200, a.text
    appealed = a.json()
    _assert_inline_shape(appealed, "appealDispute")
    profile = client.get(f"{API}/users/{worker['id']}", headers=auth(requester)).json()
    _assert_inline_shape(profile, "publicProfile")
    # 一单闭环产生佣金，平台才有钱可结算
    topup(client, requester, 40000)
    t = publish_task(client, requester)
    match_and_fund(client, requester, worker, t)
    client.post(f"{API}/tasks/{t['id']}/deliver", headers=auth(worker))
    client.post(f"{API}/tasks/{t['id']}/accept-delivery", headers=auth(requester))
    s = client.post(f"{API}/admin/platform-finance/settle", json={"amount_cents": 100, "memo": "测试结算"}, headers=auth(admin))
    assert s.status_code == 200, s.text
    settled = s.json()
    _assert_inline_shape(settled, "settlePlatform")


def test_pending_team_and_empty_mandate_shapes(client):
    from tests.test_machine_delegation import setup
    from tests.test_team_accounts import make_team, make_user

    owner = make_user(client, "13300039001", "老板")
    team_id = make_team(client, owner)
    client.post(f"{API}/teams/{team_id}/company", json={"company_name": "某某科技有限公司", "tax_number": "91310000MA1K00000X",
                                                       "license_images": ["lic-90.png"]}, headers=auth(owner))
    admin = make_admin(client, "13300039009")
    pending = client.get(f"{API}/admin/teams/pending", headers=auth(admin)).json()
    _assert_shape(_first(pending), "PendingTeamRow")
    user, _key, _ = setup(client)
    # 一把从没授权过的 Key：GET 授权返回 null（MachineMandateView | null 的 null 那一半）
    fresh = client.post(f"{API}/developer/api-keys", headers=auth(user), json={"name": "只读", "scopes": ["tasks:read"]}).json()
    none = client.get(f"{API}/developer/api-keys/{fresh['id']}/mandate", headers=auth(user)).json()
    assert none is None
    _assert_inline_shape(none, "machineMandate")


def test_knowledge_calibration_and_retract_shapes(client, monkeypatch):
    from app.vendors import registry
    from tests.test_knowledge_clusters import SemanticStub, _card, _run, _threshold

    monkeypatch.setitem(registry._instances, "embedding", SemanticStub())
    try:
        admin = make_admin(client, "13800039004")
        hz = [_card(city="杭州") for _ in range(3)]
        sh = [_card(city="上海") for _ in range(2)]
        bj = [_card(city="北京") for _ in range(2)]
        pairs = [{"a": hz[0], "b": hz[1], "same": True}, {"a": hz[1], "b": hz[2], "same": True},
                 {"a": hz[0], "b": sh[0], "same": True}, {"a": sh[0], "b": sh[1], "same": True},
                 {"a": hz[0], "b": bj[0], "same": False}, {"a": sh[1], "b": bj[1], "same": False}]
        r = client.post(f"{API}/admin/knowledge/thresholds/跑腿/calibrate", json={"pairs": pairs}, headers=auth(admin))
        assert r.status_code == 200, r.text
        got = client.get(f"{API}/admin/knowledge/thresholds/跑腿/pairs", headers=auth(admin)).json()
        _assert_shape(_first(got), "KnowledgeCalibrationPair")
        _threshold()
        _card(city="杭州", task_id=779001)
        _run(client)
        rr = client.post(f"{API}/admin/knowledge/tasks/779001/retract", json={"reason": "事后确认刷单"}, headers=auth(admin))
        assert rr.status_code == 200, rr.text
        retracted = rr.json()
        _assert_inline_shape(retracted, "retractKnowledgeTask")
    finally:
        registry._instances.pop("embedding", None)
