"""PACK-092c（436 号 spec，V463）场景包近义说法在后台维护：一位管理员提出，另一位确认才生效，任何一位都可以收回。

V462 的近义表写在仓库文件里，新出一个说法就要发版。配错会让所有场景包助手引用不相干的知识，所以四眼；
后台只能加写法，仓库里写死的收不回（与资质别名一样）。提出与确认都按当时生效的表查一遍（与仓库近义表的闸门同一套规则）。
"""
from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from app.modules.packs import service as psvc
from tests.conftest import auth, make_admin
from tests.test_v286_packs import _publish

API = "/api/v1"
S = f"{API}/admin/pack-synonyms"
DRONE = "看风力、电量和信号，留足返航余量，现场先试飞"


def _ask(client, user, q):
    r = client.post(f"{API}/packs/drone-aerial/assistants/drone-aerial-helper/ask", json={"q": q}, headers=auth(user))
    assert r.status_code == 200, r.text
    return [c["title"] for c in r.json()["citations"]]


def test_a_synonym_takes_effect_only_after_a_second_admin_approves_and_stops_when_revoked(client, requester):
    from tests.test_client_shape_alignment import _assert_shape

    _publish(client, "drone-aerial", ("13700463001", "13700463002"))
    ops1, ops2 = make_admin(client, "13700463003", "运营甲"), make_admin(client, "13700463004", "运营乙")
    assert DRONE not in _ask(client, requester, "风很大能飞吗"), "知识里写的是「风力」，还没配近义"
    r = client.post(S, json={"name": "大风", "words": [" 风力 "], "reason": "无人机的知识写的是风力"}, headers=auth(ops1))
    assert r.status_code == 201 and r.json()["status"] == "pending" and r.json()["words"] == ["风力"], r.text
    _assert_shape(r.json(), "PackSynonymItem")
    sid = r.json()["id"]
    assert DRONE not in _ask(client, requester, "风很大能飞吗"), "提出了还没确认，不生效"
    me = client.post(f"{S}/{sid}/approve", headers=auth(ops1))
    assert me.status_code == 403 and me.json()["detail"]["code"] == "pack_synonym_self", me.text
    ok = client.post(f"{S}/{sid}/approve", headers=auth(ops2))
    assert ok.status_code == 200 and ok.json()["status"] == "active" and ok.json()["approved_by"] == ops2["id"], ok.text
    assert DRONE in _ask(client, requester, "风很大能飞吗")
    ex = client.get(S + "/expand", params={"q": "风很大能飞吗"}, headers=auth(ops1)).json()
    assert "风力" in ex["words"] and "大风" in ex["words"], ex
    view = client.get(S, headers=auth(ops1)).json()
    _assert_shape(view, "PackSynonymList")
    wind = next(g for g in view["effective"] if g["name"] == "大风")
    assert "风力" in wind["words"] and "刮大风" in wind["words"], "并进仓库里的那一组，原来的写法都还在"
    gone = client.post(f"{S}/{sid}/revoke", headers=auth(ops1))
    assert gone.status_code == 200 and gone.json()["status"] == "revoked", gone.text
    assert DRONE not in _ask(client, requester, "风很大能飞吗"), "收回立刻失效"
    again = client.post(f"{S}/{sid}/revoke", headers=auth(ops2))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "pack_synonym_decided"
    with SessionLocal() as db:
        acts = {a.action for a in db.query(AdminAudit).filter(AdminAudit.target_type == "pack_synonym")}
    assert {"pack_synonym_propose", "pack_synonym_approve", "pack_synonym_revoke"} <= acts


def test_bad_proposals_are_refused_with_the_reason(client):
    ops = make_admin(client, "13700463011", "运营甲")
    cases = [
        ({"name": "大风", "words": ["暴雨"]}, "pack_synonym_word_taken"),          # 已经在「下雨」组
        ({"name": "设计", "words": ["标志设计"]}, "pack_synonym_skill_word"),      # 技能概念表里的词
        ({"name": "下雨", "words": ["雨"]}, "pack_synonym_short"),                 # 单字
        ({"name": "天公不作美", "words": [], "includes": ["没有这组"]}, "pack_synonym_unknown_include"),
        ({"name": "下雨", "words": ["暴雨", "雨天"]}, "pack_synonym_exists"),
        ({"name": "天公不作美", "words": ["老天爷变脸", "出门不顺", "天色不对", "天儿不好"],
          "includes": ["下雨", "大风", "下雪", "高温", "天气不好"]}, "pack_synonym_too_wide"),   # 5 + 8 + 6 + 5 + 4 + 5 = 33 > 32
    ]
    for body, code in cases:
        r = client.post(S, json={**body, "reason": "测试拦截规则"}, headers=auth(ops))
        assert r.status_code == 400 and r.json()["detail"]["code"] == code, (body, r.text)
    first = client.post(S, json={"name": "风力", "words": ["风力等级"], "reason": "第一次提出"}, headers=auth(ops))
    assert first.status_code == 201, first.text
    dup = client.post(S, json={"name": "风力", "words": ["几级风"], "reason": "同名还在等确认"}, headers=auth(ops))
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "pack_synonym_pending", dup.text


def test_approval_rechecks_against_the_table_as_it_is_now(client):
    ops1, ops2 = make_admin(client, "13700463021", "运营甲"), make_admin(client, "13700463022", "运营乙")
    a = client.post(S, json={"name": "大风", "words": ["风力"], "reason": "无人机写风力"}, headers=auth(ops1)).json()
    b = client.post(S, json={"name": "风况", "words": ["风力"], "reason": "另一个人也想加"}, headers=auth(ops1)).json()
    assert a["status"] == b["status"] == "pending"
    assert client.post(f"{S}/{a['id']}/approve", headers=auth(ops2)).status_code == 200
    late = client.post(f"{S}/{b['id']}/approve", headers=auth(ops2))
    assert late.status_code == 409 and late.json()["detail"]["code"] == "pack_synonym_word_taken", late.text
    assert "近义表变了" in late.json()["detail"]["message"]


def test_a_new_group_can_point_one_way_at_an_existing_group(client):
    ops1, ops2 = make_admin(client, "13700463031", "运营甲"), make_admin(client, "13700463032", "运营乙")
    r = client.post(S, json={"name": "天公不作美", "words": ["老天不帮忙"], "includes": ["下雨"], "reason": "老人常这么说"},
                    headers=auth(ops1))
    assert r.status_code == 201 and r.json()["words"] == ["天公不作美", "老天不帮忙"], "新的一组，组名也算一个写法"
    assert client.post(f"{S}/{r.json()['id']}/approve", headers=auth(ops2)).status_code == 200
    with SessionLocal() as db:
        assert "暴雨" in psvc.synonyms_in("天公不作美还去吗", db)
        assert "天公不作美" not in psvc.synonyms_in("下雨还去吗", db), "单向：问下雨不反推上位词"
        assert "暴雨" not in psvc.synonyms_in("天公不作美还去吗"), "不给 db 只看仓库里的（离线试问法与闸门）"
