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
