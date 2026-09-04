"""LAW-005/030/031/032/044/045 协议版本化、单独同意与数据主体权利（26 号 spec 第 D 节）。

这批测试盯的是三个「看起来做了、其实没做」的地方：

1. **版本号存了但没人读**——`AGREEMENT_VERSION` 是我自己在 V50 加进配置又忘了用的，
   所以这里第一件事就是证明：改了版本号，关键动作真的会被拦下来。
2. **敏感项混在总协议里**——注册即同意的只有三份文书，证件/位置/支付
   必须由各自的动作单独同意，不能被注册那一下顺手勾掉。
3. **撤回是个假按钮**——只写一条 revoked 记录、依赖它的数据原样留着、
   能力照样能用，那就等于没撤。这里逐条验证撤回的**实际后果**。
"""
import pytest

from .conftest import auth, bind_payout, register, topup, verify_user
from .test_task_flow import publish_task


def agreements(client, user):
    r = client.get("/api/v1/legal/agreements", headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def scope_of(body, key):
    return next(s for s in body["sensitive_scopes"] if s["key"] == key)


@pytest.fixture()
def bump_version(monkeypatch):
    """把协议版本推到下一版——模拟「平台更新了隐私政策」。"""
    from app.core.config import settings

    def _bump(version="2099-01-01"):
        monkeypatch.setattr(settings, "AGREEMENT_VERSION", version)
        return version

    return _bump


# ---------- LAW-030 注册即同意三份文书 ----------
def test_registration_grants_documents_but_not_sensitive_scopes(client):
    user = register(client, "13800020001", "新用户")
    body = agreements(client, user)

    assert {d["key"] for d in body["documents"]} == {
        "user_terms", "privacy_policy", "platform_rules"
    }
    assert all(d["needs_reconsent"] is False for d in body["documents"])
    # 关键点：敏感项**没有**被注册那一下顺手同意掉
    assert all(s["granted"] is False for s in body["sensitive_scopes"])


# ---------- LAW-044 协议更新后必须重新同意 ----------
def test_law044_agreement_update_blocks_key_actions(client, requester, bump_version):
    topup(client, requester, 100000)
    # 更新前：发任务没问题
    publish_task(client, requester, budget_cents=10000)

    new_version = bump_version()
    body = agreements(client, requester)
    assert body["current_version"] == new_version
    assert all(d["needs_reconsent"] is True for d in body["documents"])

    r = client.post("/api/v1/tasks", json={
        "title": "协议更新后发布", "description": "x" * 20, "category": "跑腿",
        "task_type": "onsite", "budget_cents": 10000, "city": "北京",
        "lat": 39.9, "lng": 116.4,
    }, headers=auth(requester))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "agreement_update_required"

    # 重新同意后立即恢复
    ok = client.post("/api/v1/legal/agreements/accept", headers=auth(requester))
    assert ok.status_code == 200, ok.text
    assert ok.json()["accepted_version"] == new_version
    publish_task(client, requester, budget_cents=10000)


def test_law044_reading_agreements_is_never_blocked(client, requester, bump_version):
    """合规不能做成拒绝服务：协议过期时，看协议和注销账号必须还能用。

    否则用户会卡在「要同意才能用、要能用才能看到要同意什么」的死循环里。
    """
    bump_version()
    assert client.get("/api/v1/legal/agreements", headers=auth(requester)).status_code == 200
    assert client.get("/api/v1/users/me", headers=auth(requester)).status_code == 200
    assert client.get("/api/v1/tasks").status_code == 200
    assert client.get("/api/v1/users/me/export", headers=auth(requester)).status_code == 200


def test_law044_withdraw_blocked_until_reconsent(client, worker, bump_version):
    topup(client, worker, 50000)
    bind_payout(client, worker, "李四")
    bump_version()

    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000},
                    headers=auth(worker))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "agreement_update_required"

    client.post("/api/v1/legal/agreements/accept", headers=auth(worker))
    assert client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000},
                       headers=auth(worker)).status_code == 200


# ---------- LAW-031 敏感项单独同意 ----------
def test_law031_sensitive_consent_granted_by_the_action_that_needs_it(client):
    user = register(client, "13800020002", "小明")
    assert scope_of(agreements(client, user), "identity")["granted"] is False

    verify_user(client, user, "小明")
    body = agreements(client, user)
    assert scope_of(body, "identity")["granted"] is True
    assert scope_of(body, "identity")["granted_at"] is not None
    # 实名不会顺带把支付/位置也同意了
    assert scope_of(body, "payment")["granted"] is False
    assert scope_of(body, "location")["granted"] is False

    bind_payout(client, user, "小明")
    assert scope_of(agreements(client, user), "payment")["granted"] is True


def test_law031_checkin_grants_location_consent(client, requester, worker):
    from .test_task_flow import match_and_fund

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)

    assert scope_of(agreements(client, worker), "location")["granted"] is False
    r = client.post(f"/api/v1/tasks/{task['id']}/checkin",
                    json={"lat": task["lat"], "lng": task["lng"]}, headers=auth(worker))
    assert r.status_code == 201, r.text
    assert scope_of(agreements(client, worker), "location")["granted"] is True


def test_law031_never_consented_gets_the_actionable_error_not_a_consent_lecture(client, worker):
    """从没绑过卡就提现 → 报「没绑收款账户」，而不是「请先同意支付信息处理」。

    合规校验插在业务校验前面，会把一个能照做的提示换成一句让人去点空设置页的话。
    敏感项的「从未同意」交给具体业务校验，合规只管「撤回后必须停」。
    """
    topup(client, worker, 50000)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000},
                    headers=auth(worker))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "no_payout_account"


def test_unknown_scope_rejected(client, requester):
    for path in ("grant", "revoke"):
        r = client.post(f"/api/v1/legal/consents/browsing_history/{path}",
                        headers=auth(requester))
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "invalid_scope"


# ---------- LAW-032 撤回同意及其**实际后果** ----------
def test_law032_revoking_payment_unbinds_payout_account(client, worker):
    from app.core.db import SessionLocal
    from app.modules.wallet.models import PayoutAccount

    topup(client, worker, 50000)
    bind_payout(client, worker, "李四")
    with SessionLocal() as db:
        assert db.get(PayoutAccount, worker["id"]) is not None

    r = client.post("/api/v1/legal/consents/payment/revoke", headers=auth(worker))
    assert r.status_code == 200, r.text
    assert "payout_account_unbound" in r.json()["applied"]
    with SessionLocal() as db:
        assert db.get(PayoutAccount, worker["id"]) is None

    # 能力真的停了，而不是只写了条记录
    blocked = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000},
                          headers=auth(worker))
    assert blocked.status_code == 400
    assert blocked.json()["detail"]["code"] == "no_payout_account"


def test_law032_revoked_consent_is_not_silently_reacquired(client, worker):
    """撤回后再做同一个动作，不能「自动重新同意」——必须用户显式再授权。

    这是 ensure() 存在的全部理由：首次随动作同意是合理的，
    撤回之后还随动作同意，就是把用户的撤回当没看见。
    """
    bind_payout(client, worker, "李四")
    client.post("/api/v1/legal/consents/payment/revoke", headers=auth(worker))

    again = client.put("/api/v1/wallet/payout-account",
                       json={"kind": "bank", "account_no": "6222020000123456",
                             "holder_name": "李四"}, headers=auth(worker))
    assert again.status_code == 409, again.text
    assert again.json()["detail"]["code"] == "consent_withdrawn"

    ok = client.post("/api/v1/legal/consents/payment/grant", headers=auth(worker))
    assert ok.status_code == 200, ok.text
    bind_payout(client, worker, "李四")


def test_law032_revoking_identity_disables_verified_only_actions(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)

    r = client.post("/api/v1/legal/consents/identity/revoke", headers=auth(worker))
    assert r.status_code == 200, r.text

    blocked = client.post(f"/api/v1/tasks/{task['id']}/applications",
                          json={"message": "我来做"}, headers=auth(worker))
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["detail"]["code"] == "consent_withdrawn"

    client.post("/api/v1/legal/consents/identity/grant", headers=auth(worker))
    assert client.post(f"/api/v1/tasks/{task['id']}/applications",
                       json={"message": "我来做"}, headers=auth(worker)).status_code == 201


def test_law032_revoking_location_keeps_live_task_checkins_as_evidence(client, requester, worker):
    """删除权 vs 举证需要：进行中任务的打卡坐标是对方的唯一凭据，依法保留。

    全删掉会让「你根本没到场」这种争议变成各说各话——
    PIPL 把「法律法规另有规定」列为删除权例外，正是为了这种情形。
    """
    from app.core.db import SessionLocal
    from app.modules.task.models import ProgressLog
    from .test_task_flow import match_and_fund

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/checkin",
                json={"lat": task["lat"], "lng": task["lng"]}, headers=auth(worker))

    r = client.post("/api/v1/legal/consents/location/revoke", headers=auth(worker))
    assert r.status_code == 200, r.text
    assert "live_task_checkins_retained_for_dispute" in r.json()["applied"]
    with SessionLocal() as db:
        kept = db.query(ProgressLog).filter(
            ProgressLog.task_id == task["id"], ProgressLog.kind == "checkin"
        ).one()
        assert kept.lat is not None

    # 但后续打卡被拒——保留旧证据不等于可以继续采集
    blocked = client.post(f"/api/v1/tasks/{task['id']}/checkin",
                          json={"lat": task["lat"], "lng": task["lng"]},
                          headers=auth(worker))
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "consent_withdrawn"


def test_law032_base_documents_cannot_be_revoked_piecemeal(client, requester):
    """撤回《用户协议》等于终止服务关系，应走注销（会先校验无未结资金与纠纷）。"""
    r = client.post("/api/v1/legal/consents/user_terms/revoke", headers=auth(requester))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "use_account_deactivation"


def test_law032_revoke_twice_is_rejected(client, worker):
    bind_payout(client, worker, "李四")
    assert client.post("/api/v1/legal/consents/payment/revoke",
                       headers=auth(worker)).status_code == 200
    again = client.post("/api/v1/legal/consents/payment/revoke", headers=auth(worker))
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "not_consented"


def test_law032_rights_map_points_at_endpoints_that_exist(client, requester):
    """权利入口不能是写在文档里的空头支票——逐个打过去看通不通。"""
    rights = agreements(client, requester)["rights"]
    assert client.get(rights["access"].removeprefix("GET "),
                      headers=auth(requester)).status_code == 200
    assert client.get(rights["export"].removeprefix("GET "),
                      headers=auth(requester)).status_code == 200
    assert client.patch(rights["rectify"].removeprefix("PATCH "),
                        json={"nickname": "改个名"}, headers=auth(requester)).status_code == 200
    # 撤回入口是带参数的模板，替换后应可用
    path = rights["withdraw_consent"].removeprefix("POST ").replace("{scope}", "location")
    assert client.post(path, headers=auth(requester)).status_code in (200, 409)


def test_law032_export_includes_consent_history(client, worker):
    bind_payout(client, worker, "李四")
    client.post("/api/v1/legal/consents/payment/revoke", headers=auth(worker))

    body = client.get("/api/v1/users/me/export", headers=auth(worker)).json()
    scopes = {c["scope"] for c in body["consents"]}
    assert {"user_terms", "privacy_policy", "platform_rules", "identity", "payment"} <= scopes
    payment = [c for c in body["consents"] if c["scope"] == "payment"]
    assert any(c["revoked_at"] for c in payment)
    # 只增不改：撤回不抹掉「他当时确实同意过」这个事实
    assert all(c["granted_at"] for c in payment)


def test_revocation_effect_is_disclosed_before_revoking(client, requester):
    """撤回前必须能看到会失去什么，否则用户点完才发现接不了单。"""
    body = agreements(client, requester)
    for scope in body["sensitive_scopes"]:
        assert scope["revocable"] is True
        assert len(scope["revocation_effect"]) > 10


# ---------- LAW-045 未成年人拦截 ----------
def test_law045_minor_cannot_complete_verification(client):
    from datetime import date

    user = register(client, "13800020003", "小学生")
    born = date.today().replace(year=date.today().year - 15)
    id_number = f"110101{born:%Y%m%d}1234"
    r = client.post("/api/v1/users/me/verify",
                    json={"real_name": "小学生", "id_number": id_number},
                    headers=auth(user))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "minor_not_allowed"

    # 拦下了就不能留下「已实名」的既成事实
    me = client.get("/api/v1/users/me", headers=auth(user)).json()
    assert me["is_verified"] is False


def test_law045_adult_passes_and_is_flagged(client):
    from app.core.db import SessionLocal
    from app.modules.account.models import User

    user = register(client, "13800020004", "成年人")
    verify_user(client, user, "成年人", id_number="110101199001011234")
    with SessionLocal() as db:
        assert db.get(User, user["id"]).is_adult is True


def test_law045_unparsable_id_is_not_blocked(client):
    """拦截基于确证的事实，而不是解析失败的猜测。

    15 位老身份证是最典型的例子：它没有世纪位，按 18 位规则去切会切出乱码。
    但持 15 位证件的人 1999 年前就已登记，必然早已成年——
    在这里误伤一个真实成年人，比放过一个理论上的未成年人代价更大。
    """
    user = register(client, "13800020005", "老证件")
    r = client.post("/api/v1/users/me/verify",
                    json={"real_name": "老证件", "id_number": "110101900101123"},
                    headers=auth(user))
    assert r.status_code == 200, r.text
