"""SCN-222 / SCN-223 第二十四轮场景发掘：插画约稿、代驾（337 号 spec，V364）。

两个数据文件、两个新类目：「插画约稿」不要资质；「代驾」与「陪驾」一样要审核通过的驾驶证（三年以上驾龄）。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import DRIVER_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_illustration_pack_spells_out_license_ai_and_stages():
    d, problems = schema.validate(_load("illustration-commission"))
    assert d is not None and not problems, problems
    assert d.segment == "creator"
    a = d.assistants[0]
    assert {"money", "sign"} <= set(a.human_gates)
    assert any("隐瞒用 AI" in f for f in a.forbidden) and any("描图" in f for f in a.forbidden)
    assert any("授权范围" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["插画约稿"]
    t = d.task_templates[0].description
    assert "授权" in t and "AI" in t and "分三期确认" in t


def test_designated_driver_pack_checks_license_insurance_and_keys():
    d, problems = schema.validate(_load("designated-driver"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("准驾车型不符" in f for f in a.forbidden) and any("醉酒" in f for f in a.forbidden)
    assert any("不拍车况" in f for f in a.forbidden)
    assert _categories()["代驾"]["required_cert"] == DRIVER_CERT
    t = d.task_templates[0]
    assert "拍车况" in t.description and "钥匙交给" in t.description
    assert "出发前拍车况与里程" in t.visit_checklist


@pytest.mark.parametrize("key", ["illustration-commission", "designated-driver"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_only_a_reviewed_driver_license_can_take_a_designated_driving_job(client, requester):
    ops = make_admin(client, "13600003641", "运营")
    t = _post(client, requester, title="酒后代驾", description="从饭店到小区，约 12 公里，自动挡", category="代驾").json()
    w = make_verified(client, "13600003642")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and DRIVER_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=DRIVER_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    ok = client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件清晰，驾龄满三年"},
                     headers=auth(ops))
    assert ok.status_code == 200, ok.text
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    art = _post(client, requester, title="头像约稿", description="自用头像，全程手绘", category="插画约稿", is_remote=True)
    assert art.status_code in (200, 201), art.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("illustration-commission", "illustration-helper", ("13900003641", "13900003642"), "客户说要拿去印周边卖", "先问用途，授权范围写进单子"),
    ("illustration-commission", "illustration-helper", ("13900003643", "13900003644"), "客户说是AI画的要退款", "用没用 AI，接单前说清"),
    ("illustration-commission", "illustration-helper", ("13900003645", "13900003646"), "已经改了好多次了还要改", "草图、线稿、上色分阶段确认，改稿轮数写清"),
    ("illustration-commission", "illustration-helper", ("13900003647", "13900003648"), "客户画到一半不要了", "画到哪一步取消付多少，事先写清"),
    ("designated-driver", "designated-driver-helper", ("13900003649", "13900003650"), "客户说车上多了一道划痕", "出发前和客户一起绕车拍车况"),
    ("designated-driver", "designated-driver-helper", ("13900003651", "13900003652"), "客户喝多了还要自己开走", "钥匙交给清醒的人，不把车交给醉酒的人开"),
    ("designated-driver", "designated-driver-helper", ("13900003653", "13900003654"), "我是C2能接手动挡吗", "驾龄与准驾车型对得上才接"),
    ("designated-driver", "designated-driver-helper", ("13900003655", "13900003656"), "代驾路上被拍了扣分谁管", "按约定路线开；代驾期间的违章自己处理"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("illustration-commission", "illustration-helper", ("13900003657", "13900003658"), "客户怀疑是电脑画的", "用没用 AI，接单前说清"),
    ("designated-driver", "designated-driver-helper", ("13900003659", "13900003660"), "客户硬说我把他车蹭了", "出发前和客户一起绕车拍车况"),
    ("designated-driver", "designated-driver-helper", ("13900003661", "13900003662"), "客户断片了怎么交车", "钥匙交给清醒的人，不把车交给醉酒的人开"),
    ("designated-driver", "designated-driver-helper", ("13900003663", "13900003664"), "不太会踩离合能接吗", "驾龄与准驾车型对得上才接"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
