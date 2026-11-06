"""SCN-308 / SCN-309 第六十四轮场景发掘：门头招牌安装、活动音响灯光（421 号 spec，V448）。

两个新类目都不强制资质，但发单人可以按这一单加选（SCN-294b，407 号）：
- 「门头招牌安装」可加选高处作业证、电工证：先问清报批（城市市容和环境卫生管理条例）、上高处与接电持证
  （安全生产法第三十条）、支架打进结构抗风、发光字防水加漏电保护、试亮清场；
- 「活动音响灯光」可加选电工证：设备清单写备用、持证接电独立回路、线缆贴地固定、灯架配重加安全绳、
  守音量与结束时间（噪声污染防治法）。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091）离线试过。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import ELECTRICIAN_CERT, HEIGHT_WORK_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_shop_sign_pack_asks_for_the_permit_and_anchors_into_structure():
    d, problems = schema.validate(_load("shop-sign"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("报批" in f for f in a.forbidden) and any("没有证" in f for f in a.forbidden)
    assert any("空心砖" in f for f in a.forbidden) and any("漏电保护" in f for f in a.forbidden)
    assert any("占道" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    cat = _categories()["门头招牌安装"]
    assert "required_cert" not in cat and cat["optional_certs"] == [HEIGHT_WORK_CERT, ELECTRICIAN_CERT]
    t = d.task_templates[0].description
    assert "报批" in t and "高处作业证" in t and "漏电保护" in t


def test_event_av_pack_keeps_backups_and_tapes_the_cables():
    d, problems = schema.validate(_load("event-av"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("备用" in f for f in a.forbidden) and any("串插排" in f for f in a.forbidden)
    assert any("线缆不固定" in f for f in a.forbidden) and any("配重" in f for f in a.forbidden)
    assert any("音量" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    cat = _categories()["活动音响灯光"]
    assert "required_cert" not in cat and cat["optional_certs"] == [ELECTRICIAN_CERT]
    t = d.task_templates[0].description
    assert "备用" in t and "独立回路" in t and "配重" in t


@pytest.mark.parametrize("key", ["shop-sign", "event-av"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_publisher_can_ask_for_the_height_cert_on_a_tall_sign(client, requester):
    ops = make_admin(client, "13600044801", "审核")
    w = make_verified(client, "13600044802")
    low = _post(client, requester, title="门口小灯箱换面", description="一米五高，不接电", category="门头招牌安装").json()
    assert client.post(f"{API}/tasks/{low['id']}/applications", json={}, headers=auth(w)).status_code == 201
    tall = _post(client, requester, title="二楼外墙发光字", description="离地五米，要接电", category="门头招牌安装",
                 task_certs=[HEIGHT_WORK_CERT]).json()
    assert tall["task_certs"] == [HEIGHT_WORK_CERT]
    no = client.post(f"{API}/tasks/{tall['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and HEIGHT_WORK_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=HEIGHT_WORK_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件可查"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{tall['id']}/applications", json={}, headers=auth(w)).status_code == 201
    av = _post(client, requester, title="年会音响灯光", description="两百人", category="活动音响灯光")
    assert av.status_code in (200, 201), av.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("shop-sign", "shop-sign-helper", ("13700448001", "13700448002"), "装招牌要报批吗", "先请店主问清当地要不要报批，批了再装"),
    ("shop-sign", "shop-sign-helper", ("13700448003", "13700448004"), "要什么证", "上 2 米以上持高处作业证，接电持电工证"),
    ("shop-sign", "shop-sign-helper", ("13700448005", "13700448006"), "支架怎么固定", "支架打进墙体结构，大招牌按风压加固"),
    ("shop-sign", "shop-sign-helper", ("13700448007", "13700448008"), "发光字怎么防水", "发光字接线防水、加漏电保护，变压器放通风处"),
    ("shop-sign", "shop-sign-helper", ("13700448009", "13700448010"), "装完要做什么", "装完通电试亮、拍照，清走边角料不占道"),
    ("event-av", "event-av-helper", ("13700448011", "13700448012"), "设备清单怎么写", "设备清单、型号、数量和备用写清"),
    ("event-av", "event-av-helper", ("13700448013", "13700448014"), "接电要注意什么", "接电持电工证，大功率设备用独立回路"),
    ("event-av", "event-av-helper", ("13700448015", "13700448016"), "线怎么走", "线缆走线槽或贴地固定，通道上不留绊脚线"),
    ("event-av", "event-av-helper", ("13700448017", "13700448018"), "灯架要配重吗", "灯架音箱架加配重、挂安全绳，人多处不搭高架"),
    ("event-av", "event-av-helper", ("13700448019", "13700448020"), "音量有限制吗", "音量和结束时间守场地与居民区的规定"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("shop-sign", "shop-sign-helper", ("13700448021", "13700448022"), "梯子顶上", "上 2 米以上持高处作业证，接电持电工证"),
    ("shop-sign", "shop-sign-helper", ("13700448023", "13700448024"), "砸到人", "支架打进墙体结构，大招牌按风压加固"),
    ("shop-sign", "shop-sign-helper", ("13700448025", "13700448026"), "不亮了", "发光字接线防水、加漏电保护，变压器放通风处"),
    ("shop-sign", "shop-sign-helper", ("13700448027", "13700448028"), "缺笔画", "装完通电试亮、拍照，清走边角料不占道"),
    ("event-av", "event-av-helper", ("13700448029", "13700448030"), "话筒没电", "设备清单、型号、数量和备用写清"),
    ("event-av", "event-av-helper", ("13700448031", "13700448032"), "跳闸", "接电持电工证，大功率设备用独立回路"),
    ("event-av", "event-av-helper", ("13700448033", "13700448034"), "绊倒", "线缆走线槽或贴地固定，通道上不留绊脚线"),
    ("event-av", "event-av-helper", ("13700448035", "13700448036"), "扰民", "音量和结束时间守场地与居民区的规定"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
