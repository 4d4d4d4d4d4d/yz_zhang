"""SCN-329 / SCN-330 第七十四轮场景发掘：电热水器安装、汽车凹陷修复补漆（440 号 spec，V467）。

- 「电热水器安装」不强制资质，新拉线路可加选电工证（安全生产法第三十条）：只挂承重墙或实心墙、带接地的专用插座配漏电保护、
  安全阀接排水不堵、先注满水再通电防干烧、交代排污与镁棒（消保法第十八条）；
- 「汽车凹陷修复补漆」不要资质：先看漆面说清能否无痕修复（消保法第二十条）、按漆码调色先试一处、上门只做无痕修复和点补
  不在小区喷漆、修前修后拍照（第五十二条）、按处报价不临时加价。
问法写测试之前都先用 scripts/pack_probe.py 离线试过；写完用 scripts/pack_mutate.py（PACK-094）做变异红验。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import ELECTRICIAN_CERT
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_heater_pack_hangs_on_a_solid_wall_and_fills_before_power():
    d, problems = schema.validate(_load("water-heater-install"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("轻质隔墙" in f for f in a.forbidden) and any("没有接地" in f for f in a.forbidden)
    assert any("安全阀堵上" in f for f in a.forbidden) and any("没注满水" in f for f in a.forbidden)
    assert any("排污" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    cat = _categories()["电热水器安装"]
    assert "required_cert" not in cat and cat["optional_certs"] == [ELECTRICIAN_CERT]
    t = d.task_templates[0].description
    assert "实心墙" in t and "安全阀接排水" in t and "先注满水再通电" in t


def test_dent_pack_says_what_cannot_be_fixed_and_never_sprays_onsite():
    d, problems = schema.validate(_load("car-dent-repair"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("承诺无痕" in f for f in a.forbidden) and any("漆码" in f for f in a.forbidden)
    assert any("小区里大面积喷漆" in f for f in a.forbidden) and any("修前照片" in f for f in a.forbidden)
    assert any("现场再加价" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["汽车凹陷修复补漆"]
    t = d.task_templates[0].description
    assert "按车上漆码" in t and "不在小区喷漆" in t and "修前修后拍照" in t


@pytest.mark.parametrize("key", ["water-heater-install", "car-dent-repair"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_and_the_heater_can_ask_for_an_electrician(client, requester):
    w = make_verified(client, "13600046701")
    for title, cat in (("卫生间装60升热水器", "电热水器安装"), ("车门一个小坑", "汽车凹陷修复补漆")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text
    wired = _post(client, requester, title="热水器要新拉线", description="卫生间没有插座", category="电热水器安装",
                  task_certs=[ELECTRICIAN_CERT]).json()
    no = client.post(f"{API}/tasks/{wired['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and ELECTRICIAN_CERT in no.json()["detail"]["message"], no.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("water-heater-install", "water-heater-helper", ("13700467001", "13700467002"), "隔墙能挂吗", "只挂在承重墙或实心墙上，空心砖、轻质隔墙不挂"),
    ("water-heater-install", "water-heater-helper", ("13700467003", "13700467004"), "要专用插座吗", "用带接地的专用插座，线径够、配漏电保护，新拉线路持电工证"),
    ("water-heater-install", "water-heater-helper", ("13700467005", "13700467006"), "安全阀滴水正常吗", "进水口装安全阀，泄压口不能堵，排水管接到地漏"),
    ("water-heater-install", "water-heater-helper", ("13700467007", "13700467008"), "没注满水能通电吗", "装好先注满水，出热水口出水了再通电，防止干烧"),
    ("water-heater-install", "water-heater-helper", ("13700467009", "13700467010"), "多久排污", "交代多久排一次污、镁棒多久换、旧机怎么处理"),
    ("car-dent-repair", "car-dent-helper", ("13700467011", "13700467012"), "凹陷能无痕修复吗", "先看漆面：漆没破、不在棱线上的能无痕修复，其余当面说清"),
    ("car-dent-repair", "car-dent-helper", ("13700467013", "13700467014"), "补漆颜色怎么调", "补漆按车上的漆码调色，先在不显眼处试一点"),
    ("car-dent-repair", "car-dent-helper", ("13700467015", "13700467016"), "大面积喷漆怎么办", "上门只做无痕修复和点补，大面积喷漆进有烤漆房的店"),
    ("car-dent-repair", "car-dent-helper", ("13700467017", "13700467018"), "修前要拍照吗", "修前修后各拍一组照片，写清保修"),
    ("car-dent-repair", "car-dent-helper", ("13700467019", "13700467020"), "怎么报价", "看实车或照片后按处报价，到了现场不临时加价"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("water-heater-install", "water-heater-helper", ("13700467021", "13700467022"), "拔出来", "只挂在承重墙或实心墙上，空心砖、轻质隔墙不挂"),
    ("water-heater-install", "water-heater-helper", ("13700467023", "13700467024"), "焦味", "用带接地的专用插座，线径够、配漏电保护，新拉线路持电工证"),
    ("water-heater-install", "water-heater-helper", ("13700467025", "13700467026"), "滴答", "进水口装安全阀，泄压口不能堵，排水管接到地漏"),
    ("water-heater-install", "water-heater-helper", ("13700467027", "13700467028"), "冒烟", "装好先注满水，出热水口出水了再通电，防止干烧"),
    ("car-dent-repair", "car-dent-helper", ("13700467029", "13700467030"), "还是坑", "先看漆面：漆没破、不在棱线上的能无痕修复，其余当面说清"),
    ("car-dent-repair", "car-dent-helper", ("13700467031", "13700467032"), "像补过", "补漆按车上的漆码调色，先在不显眼处试一点"),
    ("car-dent-repair", "car-dent-helper", ("13700467033", "13700467034"), "被投诉", "上门只做无痕修复和点补，大面积喷漆进有烤漆房的店"),
    ("car-dent-repair", "car-dent-helper", ("13700467035", "13700467036"), "扯皮", "修前修后各拍一组照片，写清保修"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
