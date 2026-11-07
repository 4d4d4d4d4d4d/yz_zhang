"""LAW-060 / SCN-114 法律常识库的运营草稿流（163 号 spec，V192）。

以前法律问答只认代码里写死的四条：雷达看到「婚姻家庭」类问题 3 个人都没答上，补知识要改代码发版。
现在合规管理员起草 → 提交 → 另一位合规上线，问答立刻能答并带出处；雷达主题一键起草，
回答与出处留「【待填写】」，不写完不能提交、不能上线——法律内容不能由模板代写结论。
"""
from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.admin.models import AdminAudit
from app.modules.analytics.models import AnalyticsEvent
from tests.conftest import auth, make_admin, register

API = "/api/v1"
URL = f"{API}/admin/legal/faqs"
Q = "离婚后孩子抚养费怎么算"


def _role(client, phone, name, role):
    a = make_admin(client, phone, name)
    with SessionLocal() as db:
        db.get(User, a["id"]).admin_roles = [role]
        db.commit()
    return a


def _ask(client, u, q=Q):
    return client.post(f"{API}/legal/ask", json={"question": q}, headers=auth(u)).json()


def _gap(client, q=Q, base="1380031000"):
    users = [register(client, f"{base}{i}", f"人{i}") for i in range(3)]
    for u in users:
        assert _ask(client, u, q)["refused_reason"] == "out_of_scope"
    return users


def _unanswered(db):
    return db.query(AnalyticsEvent).filter(AnalyticsEvent.name == "legal_unanswered").count()


def test_radar_topic_to_published_answer_with_source_closes_the_loop(client):
    a = _role(client, "13800310101", "合规甲", "compliance")
    b = _role(client, "13800310102", "合规乙", "compliance")
    users = _gap(client)
    r = client.post(f"{URL}/radar-draft", json={"topic": "婚姻家庭"}, headers=auth(a))
    assert r.status_code == 201, r.text
    f = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(f, "LegalFaqRow")
    assert f["status"] == "draft" and f["origin"] == "radar:legal_gap:婚姻家庭"
    assert "抚养" in f["keywords"] and "离婚" in f["keywords"], "关键词取主题表里的常见词：同样的问题上线后就能命中"
    assert f["placeholders"] == ["回答", "出处"] and "3 个不同的人" in f["answer"]
    blocked = client.post(f"{URL}/{f['id']}/submit", headers=auth(a))
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "pack_placeholder_left"
    # 草稿没上线：问答照样答不上
    assert _ask(client, users[0])["refused_reason"] == "out_of_scope"
    body = {"topic": "婚姻家庭", "keywords": f["keywords"],
            "answer": "离婚后不直接抚养子女的一方应负担部分或者全部抚养费，数额与期限由双方协议；协议不成的，由人民法院判决。拿不准建议找律师。",
            "source": "《民法典》第一千零八十五条"}
    assert client.put(f"{URL}/{f['id']}", json=body, headers=auth(a)).json()["placeholders"] == []
    assert client.post(f"{URL}/{f['id']}/submit", headers=auth(a)).json()["status"] == "review"
    assert client.put(f"{URL}/{f['id']}", json=body, headers=auth(a)).json()["detail"]["code"] == "legal_faq_not_draft"
    same = client.post(f"{URL}/{f['id']}/approve", headers=auth(a))
    assert same.status_code == 409 and same.json()["detail"]["code"] == "legal_faq_four_eyes"
    pub = client.post(f"{URL}/{f['id']}/approve", headers=auth(b)).json()
    assert pub["status"] == "published" and pub["reviewed_by"] == b["id"]
    with SessionLocal() as db:
        before = _unanswered(db)
    ans = _ask(client, users[0])
    assert ans["refused"] is False and ans["refused_reason"] == "" and "抚养费" in ans["answer"]
    assert ans["source"] == "《民法典》第一千零八十五条" and ans["disclaimer"]
    with SessionLocal() as db:
        assert _unanswered(db) == before, "答上了就不再记成答不上"
        actions = [x.action for x in db.query(AdminAudit).order_by(AdminAudit.id)]
    assert "legal_faq_radar_draft" in actions and "legal_faq_publish" in actions
    # 下线：问答立刻不再用它
    gone = client.post(f"{URL}/{f['id']}/retire", json={"reason": "司法解释更新了，重写"}, headers=auth(b)).json()
    assert gone["status"] == "retired" and gone["retired_reason"] == "司法解释更新了，重写"
    assert _ask(client, users[0])["refused_reason"] == "out_of_scope"


def test_old_code_faqs_still_answer_and_carry_an_empty_source(client):
    u = register(client, "13800310201", "甲")
    r = _ask(client, u, "平台上的电子合约有法律效力吗")
    assert r["refused"] is False and "民法典" in r["answer"] and r["source"] == ""
    hi = _ask(client, u, "有人威胁我人身安全怎么办")
    assert hi["refused_reason"] == "high_risk" and hi["source"] == ""


def test_only_real_radar_topics_and_topics_with_keywords(client):
    a = _role(client, "13800310301", "合规", "compliance")
    nope = client.post(f"{URL}/radar-draft", json={"topic": "婚姻家庭"}, headers=auth(a))
    assert nope.status_code == 404, "雷达上没有的主题起草不了（不能绕过至少 3 个人）"
    _gap(client, "外星人的法律怎么适用", base="1380031090")   # 归到「其他」
    other = client.post(f"{URL}/radar-draft", json={"topic": "其他"}, headers=auth(a))
    assert other.status_code == 409 and other.json()["detail"]["code"] == "legal_faq_no_keywords"


def test_manual_draft_and_roles(client):
    a = _role(client, "13800310401", "合规", "compliance")
    ops = _role(client, "13800310402", "运营", "ops")
    body = {"keywords": [" 押金 ", "押金", "房东"], "answer": "押金一般在退租验房后返还，扣除要有约定和依据。", "source": "《民法典》第七百二十二条"}
    r = client.post(URL, json=body, headers=auth(a)).json()
    assert r["keywords"] == ["押金", "房东"] and r["origin"] == "manual" and r["placeholders"] == []
    empty = client.post(URL, json={**body, "keywords": [" "]}, headers=auth(a))
    assert empty.status_code == 400 and empty.json()["detail"]["code"] == "legal_faq_no_keywords"
    assert client.get(URL, headers=auth(ops)).status_code == 403, "法律内容归合规管"
    u = register(client, "13800310403", "普通人")
    assert client.post(URL, json=body, headers=auth(u)).status_code == 403
    assert client.post(f"{URL}/{r['id']}/approve", headers=auth(a)).json()["detail"]["code"] == "legal_faq_not_in_review"
    assert client.post(f"{URL}/99999/submit", headers=auth(a)).status_code == 404


def test_approve_rechecks_placeholders_even_if_submit_was_bypassed(client):
    from app.modules.legal.faq import LegalFaq

    a = _role(client, "13800310501", "合规甲", "compliance")
    b = _role(client, "13800310502", "合规乙", "compliance")
    _gap(client, base="1380031060")
    f = client.post(f"{URL}/radar-draft", json={"topic": "婚姻家庭"}, headers=auth(a)).json()
    with SessionLocal() as db:
        db.get(LegalFaq, f["id"]).status = "review"
        db.commit()
    r = client.post(f"{URL}/{f['id']}/approve", headers=auth(b))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pack_placeholder_left"
