"""SCN-112 雷达主题一键起草知识条目（162 号 spec，V186）。

雷达看到了缺口（例如「婚姻家庭」类法律问题 3 个人都没答上），补知识以前全靠手写。现在一键起草进场景包的草稿：
只有骨架与依据，答案和出处留空（「【待填写】」）——模板不编造答案；空不填完不能提交审核，上线照样四眼。
"""
import copy

from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from app.modules.packs import schema
from tests.conftest import auth, register
from tests.test_packs import SEED, _publish

API = "/api/v1"
URL = f"{API}/admin/packs/radar/draft-knowledge"


def _legal_gap(client, topic_question="离婚后孩子抚养费怎么算", base="1380029002"):
    for i in range(3):
        u = register(client, f"{base}{i}", f"人{i}")
        client.post(f"{API}/legal/ask", json={"question": topic_question}, headers=auth(u))


def _fill(definition, key):
    d = copy.deepcopy(definition)
    for k in d["knowledge"]:
        if k["key"] == key:
            k["body"] = "抚养费一般按月给付，比例参照民法典与最高法司法解释；协商不成可以起诉。拿不准建议找律师。"
            k["source"] = "《民法典》第一千零八十五条"
    return d


def test_draft_goes_into_a_new_draft_version_with_placeholders_and_cannot_be_submitted_until_filled(client, admins):
    a, b = admins
    pub = _publish(client, admins)
    _legal_gap(client)
    r = client.post(URL, json={"source": "legal_gap", "key": "婚姻家庭", "pack_key": pub["key"]}, headers=auth(a))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["new_version"] is True and out["pack"]["status"] == "draft" and out["pack"]["version"] == pub["version"] + 1
    assert out["placeholders"] == 1
    k = next(x for x in out["pack"]["definition"]["knowledge"] if x["key"] == out["knowledge_key"])
    assert k["title"] == "婚姻家庭：常见问题怎么答" and k["kind"] == "rule"
    assert schema.PLACEHOLDER in k["body"] and schema.PLACEHOLDER in k["source"], "答案与出处必须留给人写，不能编"
    assert "3 个不同的人" in k["body"] and "抚养" in k["body"], "起草依据与主题常见词要带上，方便写的人"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(out, "RadarKnowledgeDraft")
    # 原来上线的版本不受影响
    assert client.get(f"{API}/packs/{pub['key']}", headers=auth(a)).json()["version"] == pub["version"]
    # 留着空就不能提交审核
    pid = out["pack"]["id"]
    blocked = client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "pack_placeholder_left"
    assert "出处" in blocked.json()["detail"]["message"] or "出处" in str(blocked.json())
    # 填完：提交、另一位管理员上线
    filled = client.put(f"{API}/admin/packs/{pid}", json={"definition": _fill(out["pack"]["definition"], out["knowledge_key"])},
                        headers=auth(a))
    assert filled.status_code == 200, filled.text
    assert client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a)).status_code == 200
    assert client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(a)).json()["detail"]["code"] == "pack_four_eyes"
    assert client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b)).json()["status"] == "published"
    with SessionLocal() as db:
        audit = db.query(AdminAudit).filter(AdminAudit.action == "pack_radar_draft").one()
        assert "legal_gap:婚姻家庭" in audit.detail and audit.admin_id == a["id"]


def test_a_second_draft_lands_in_the_same_draft_with_a_fresh_key(client, admins):
    a, _ = admins
    pub = _publish(client, admins)
    _legal_gap(client)
    _legal_gap(client, "房东不退押金怎么办", base="1380029003")
    first = client.post(URL, json={"source": "legal_gap", "key": "婚姻家庭", "pack_key": pub["key"]}, headers=auth(a)).json()
    second = client.post(URL, json={"source": "legal_gap", "key": "租房买房", "pack_key": pub["key"]}, headers=auth(a)).json()
    assert second["new_version"] is False and second["pack"]["id"] == first["pack"]["id"]
    assert first["knowledge_key"] != second["knowledge_key"]
    assert second["placeholders"] == 2


def test_only_signals_that_are_really_on_the_radar(client, admins):
    a, _ = admins
    pub = _publish(client, admins)
    for i in range(2):   # 只有 2 个人：不够 k-匿名，雷达上没有
        u = register(client, f"138002900{5 + i}", f"人{i}")
        client.post(f"{API}/legal/ask", json={"question": "离婚后孩子抚养费怎么算"}, headers=auth(u))
    r = client.post(URL, json={"source": "legal_gap", "key": "婚姻家庭", "pack_key": pub["key"]}, headers=auth(a))
    assert r.status_code == 404
    _legal_gap(client, base="1380029004")
    nopack = client.post(URL, json={"source": "legal_gap", "key": "婚姻家庭", "pack_key": "no-such-pack"}, headers=auth(a))
    assert nopack.status_code == 404


def test_pack_in_review_is_not_touched_and_only_ops_can_draft(client, admins):
    a, _ = admins
    pub = _publish(client, admins)
    _legal_gap(client)
    d = copy.deepcopy(SEED)
    d["summary"] = "第二版"
    v2 = client.post(f"{API}/admin/packs", json={"definition": d}, headers=auth(a)).json()
    client.post(f"{API}/admin/packs/{v2['id']}/submit", headers=auth(a))
    r = client.post(URL, json={"source": "legal_gap", "key": "婚姻家庭", "pack_key": pub["key"]}, headers=auth(a))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pack_draft_exists"
    u = register(client, "13800290099", "普通人")
    assert client.post(URL, json={"source": "legal_gap", "key": "婚姻家庭", "pack_key": pub["key"]}, headers=auth(u)).status_code == 403


def test_approve_also_refuses_leftover_placeholders(client, admins):
    """绕过提交（直接改库成待审核）也上不了线：上线时再查一遍。"""
    from app.modules.packs.models import ScenarioPack

    a, b = admins
    pub = _publish(client, admins)
    _legal_gap(client)
    out = client.post(URL, json={"source": "legal_gap", "key": "婚姻家庭", "pack_key": pub["key"]}, headers=auth(a)).json()
    with SessionLocal() as db:
        db.get(ScenarioPack, out["pack"]["id"]).status = "review"
        db.commit()
    r = client.post(f"{API}/admin/packs/{out['pack']['id']}/approve", headers=auth(b))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pack_placeholder_left"
