"""LAW-040~045 法律效力验证（26 号 spec）。

这套测试盯三件事：
1. **签署绑定文本**——签完改条款必须自证篡改；
2. **诚实标注证明力**——平台见证签名不冒充可靠电子签名，
   自算哈希链不冒充司法存证；
3. **用词不误导**——平台内部处理决定不得称作「仲裁裁决」。
"""
import pytest

from app.core.db import SessionLocal

from .conftest import JOB_HEADERS, auth, register, respond_dispute, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _sigs(client, user, contract_id):
    r = client.get(f"/api/v1/contracts/{contract_id}/signatures", headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def make_admin(client, phone="13800010001"):
    from app.modules.account.models import User

    admin = register(client, phone, "法务管理员")
    with SessionLocal() as db:
        row = db.get(User, admin["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return admin


# ---------- LAW-002/040 签署绑定合同全文 ----------
def test_signatures_recorded_for_both_parties(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)

    body = _sigs(client, requester, cid)
    assert body["valid"] is True
    roles = {s["role"] for s in body["signatures"]}
    assert roles == {"requester", "executor"}
    for s in body["signatures"]:
        assert s["signature_valid"] is True
        assert s["matches_current_terms"] is True
        assert s["document_hash"] == body["current_document_hash"]


def test_tampering_terms_after_signing_is_self_evident(client, requester, worker):
    """签署后改条款 → 哈希对不上，篡改自证并能定位到具体签名。

    这正是原实现（两个布尔位）做不到的：对方说「不是我签的那份」时，
    平台拿不出任何能反驳的东西。
    """
    from app.modules.contract.models import Contract

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)
    assert _sigs(client, requester, cid)["valid"] is True

    with SessionLocal() as db:
        row = db.get(Contract, cid)
        row.terms = row.terms + "\n（事后偷偷加的一条：违约金 100 万）"
        db.add(row)
        db.commit()

    after = _sigs(client, requester, cid)
    assert after["valid"] is False, "改了条款却校验通过 —— 签名没有绑定文本"
    assert all(s["matches_current_terms"] is False for s in after["signatures"])


def test_signature_requires_verified_identity(client, requester, worker):
    """LAW-003 未实名不得签署：签名要指向一个可确认的人。

    报名环节已强制实名，所以这里模拟的是**实名被撤销后**的情形
    （风控撤销、资料过期），签署守卫必须独立成立，而不是依赖上游拦过一次。
    """
    from app.modules.account.models import User

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    r = client.post(f"/api/v1/tasks/{task['id']}/applications",
                    json={"message": "我来"}, headers=auth(worker))
    app_id = r.json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept",
                      headers=auth(requester)).json()["contract_id"]

    with SessionLocal() as db:
        row = db.get(User, worker["id"])
        row.is_verified = False
        db.add(row)
        db.commit()

    r = client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(worker))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "verification_required"


def test_change_order_creates_new_version_signatures(client, requester, worker):
    """LAW-004 变更单经对方接受 = 对新版本的双方合意 → 各记一条新版本签名。

    刻意**不**强制再走一次签署流程：变更单本身就是要约+承诺，
    再加一步是多余的仪式，不会增加任何法律效力。
    """
    topup(client, requester, 200000)
    task = publish_task(client, requester, budget_cents=40000)
    cid = match_and_fund(client, requester, worker, task)
    before = _sigs(client, requester, cid)
    assert before["current_version"] == 1

    r = client.post(f"/api/v1/contracts/{cid}/change-orders",
                    json={"new_amount_cents": 50000, "reason": "范围增加"},
                    headers=auth(worker))
    order_id = r.json()["id"]
    r = client.post(f"/api/v1/contracts/{cid}/change-orders/{order_id}/accept",
                    headers=auth(requester))
    assert r.status_code == 200, r.text

    after = _sigs(client, requester, cid)
    assert after["current_version"] == 2
    assert after["valid"] is True, "新版本签名必须绑定变更后的条款"
    v2 = [s for s in after["signatures"] if s["contract_version"] == 2]
    assert {s["role"] for s in v2} == {"requester", "executor"}
    for s in v2:
        assert s["matches_current_terms"] is True
    # 旧版本签名对不上当前条款是**正常的**（条款已变更），不应被判为篡改
    v1 = [s for s in after["signatures"] if s["contract_version"] == 1]
    assert v1 and all(s["matches_current_terms"] is None for s in v1)


def test_signatures_require_party_or_admin(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)
    outsider = register(client, "13800010020", "路人")
    assert client.get(f"/api/v1/contracts/{cid}/signatures",
                      headers=auth(outsider)).status_code == 403


# ---------- LAW-013 诚实标注证明力 ----------
def test_platform_witness_signature_does_not_claim_to_be_qualified(client, requester, worker):
    """缺省实现必须**明说自己不是**《电子签名法》的可靠电子签名。

    冒充证明力比没有证明力更糟——上了法庭才发现顶不住，那时已经晚了。
    """
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)

    body = _sigs(client, requester, cid)
    assert all(s["reliability"] == "platform_witness" for s in body["signatures"])
    note = body["reliability_note"]
    assert "不能独立证明签名人身份" in note
    assert "不构成" in note and "可靠电子签名" in note


def test_local_notary_declares_no_third_party_backing(client, requester, worker):
    """自算哈希链不冒充司法存证。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)

    r = client.post("/api/v1/anchors/jobs/notarize", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["backed"] is False

    cov = client.get("/api/v1/anchors/coverage").json()
    assert cov["third_party_backed_to_seq"] == 0
    assert cov["uncovered_entries"] == cov["total_entries"]
    assert "无第三方背书" in cov["note"]
    assert cov["receipts"] and cov["receipts"][0]["backed"] is False


def test_notarize_is_incremental(client, requester, worker):
    """已覆盖区间不重复出回执；没有新增时不产生空回执。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)

    first = client.post("/api/v1/anchors/jobs/notarize", headers=JOB_HEADERS).json()
    assert first["notarized"] > 0
    second = client.post("/api/v1/anchors/jobs/notarize", headers=JOB_HEADERS).json()
    assert second["notarized"] == 0
    assert second["covered_to"] == first["covered_to"]


def test_third_party_backed_notary_reported(client, requester, worker, monkeypatch):
    """接了真存证后覆盖情况要如实变成 backed。"""
    from app.vendors.notary import NotaryReceipt, set_notary

    class RealNotary:
        name = "court-chain"
        backed = True

        def notarize(self, chain_head, seq_from, seq_to):
            return NotaryReceipt(receipt_no=f"JC-{seq_to}", authority="某司法链",
                                 backed=True, detail="已上链")

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)

    set_notary(RealNotary())
    try:
        client.post("/api/v1/anchors/jobs/notarize", headers=JOB_HEADERS)
        cov = client.get("/api/v1/anchors/coverage").json()
        assert cov["third_party_backed_to_seq"] == cov["total_entries"]
        assert cov["uncovered_entries"] == 0
        assert "全部存证均有第三方背书" in cov["note"]
    finally:
        set_notary(None)


# ---------- LAW-012/014 证据包 ----------
def _open_dispute(client, requester, worker):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/progress",
                json={"content": "已到现场"}, headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "成果不符合约定"}, headers=auth(requester))
    dispute_id = r.json()["id"]
    respond_dispute(client, dispute_id, worker)
    return task, cid, dispute_id


def test_evidence_package_covers_full_timeline(client, requester, worker):
    """LAW-014 证据包要覆盖完整时间线，而不是只有纠纷那几个字段。"""
    task, cid, dispute_id = _open_dispute(client, requester, worker)
    r = client.get(f"/api/v1/legal/disputes/{dispute_id}/evidence-export", headers=auth(requester))
    assert r.status_code == 200, r.text
    body = r.json()
    pkg = body["package"]

    assert pkg["task"]["id"] == task["id"]
    assert pkg["contract"]["id"] == cid and pkg["contract"]["terms"]
    assert pkg["signatures"]["signatures"], "证据包必须含签署记录"
    assert pkg["progress_logs"], "证据包必须含执行留痕"
    assert pkg["dispute"]["statements"], "证据包必须含双方陈述"
    assert body["sha256"]


def test_evidence_package_states_its_limits(client, requester, worker):
    """LAW-013 诚实标注：哪些有第三方背书、哪些没有，以及决定的法律性质。"""
    _, _, dispute_id = _open_dispute(client, requester, worker)
    body = client.get(f"/api/v1/legal/disputes/{dispute_id}/evidence-export",
                      headers=auth(requester)).json()

    integrity = body["integrity"]
    assert integrity["chain_valid"] is True
    assert integrity["uncovered_entries"] > 0  # 尚未接第三方存证

    notice = body["evidentiary_notice"]
    assert "不能独立证明签名人身份" in notice["signatures"]
    assert "无第三方背书" in notice["chain"]
    assert "不是法律意义上的仲裁裁决" in notice["decision"]
    assert "不具有强制执行力" in notice["decision"]


def test_evidence_export_requires_party(client, requester, worker):
    _, _, dispute_id = _open_dispute(client, requester, worker)
    outsider = register(client, "13800010030", "路人")
    assert client.get(f"/api/v1/legal/disputes/{dispute_id}/evidence-export",
                      headers=auth(outsider)).status_code == 403


# ---------- LAW-021/043 用词切分 ----------
def test_platform_decision_is_not_called_arbitration_award(client):
    """全站对外文案不得把平台内部处理称作「仲裁裁决」。

    平台的处理决定是依当事人事先授权做的合同履行调整，没有强制执行力；
    用「仲裁裁决」这个词会让用户以为已经走完法律程序，是实质性的误导。
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in root.rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if "仲裁裁决" not in line:
                continue
            # 唯一允许的用法：明确声明「不是」法律意义上的仲裁裁决
            if "不是法律意义上的仲裁裁决" in line:
                continue
            offenders.append(f"{path.relative_to(root)}:{lineno}: {line.strip()}")
    assert not offenders, "以下位置把平台处理决定称作仲裁裁决：\n" + "\n".join(offenders)


def test_legal_guidance_points_to_real_escalation(client, requester):
    """LAW-022 升级路径要说清楚：平台处理 → 不服可提请仲裁机构或法院。"""
    r = client.post("/api/v1/legal/ask", json={"question": "对方拖欠款项怎么办"},
                    headers=auth(requester))
    assert r.status_code == 200, r.text
    answer = str(r.json())
    assert "平台处理决定" in answer or "平台处理" in answer
    assert "仲裁机构" in answer or "法院" in answer


def test_contract_terms_carry_dispute_clause(client, requester, worker):
    """LAW-020 争议解决条款必须写进合同，并区分平台处理与法律途径。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)
    terms = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()["terms"]
    assert "平台" in terms and "处理决定" in terms
    assert "仲裁机构" in terms or "法院" in terms


# ---------- 签名供应商可替换 ----------
def test_qualified_provider_upgrades_the_notice(client, requester, worker):
    """接了第三方 CA 后，证明力声明要如实升级。"""
    from app.vendors.signature import SignatureResult, set_signature_provider

    class CaSignature:
        name = "ca-demo"
        reliability = "qualified"

        def sign(self, signer_id, document_hash, meta):
            return SignatureResult(signature=f"ca-{signer_id}-{document_hash[:8]}",
                                   certificate="CERT", timestamp_token="TSA",
                                   algorithm="RSA-SHA256", reliability="qualified",
                                   provider=self.name)

        def verify(self, signer_id, document_hash, result):
            return result.signature == f"ca-{signer_id}-{document_hash[:8]}"

    set_signature_provider(CaSignature())
    try:
        topup(client, requester, 100000)
        task = publish_task(client, requester, budget_cents=30000)
        cid = match_and_fund(client, requester, worker, task)
        body = _sigs(client, requester, cid)
        assert body["valid"] is True
        assert all(s["reliability"] == "qualified" for s in body["signatures"])
        assert "构成可靠电子签名" in body["reliability_note"]
    finally:
        set_signature_provider(None)
