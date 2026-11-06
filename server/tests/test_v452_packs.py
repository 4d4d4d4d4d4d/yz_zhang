"""SCN-312 / SCN-313 第六十六轮场景发掘：代祭扫、办公设备维修（425 号 spec，V452）。

两个新类目都不要资质：
- 「代祭扫」：先核对墓位碑文、按约定项目不擅自加钱（消保法第二十条）、守防火规定不焚烧（森林防火条例）、
  带时间的连续照片如实回报、不拍别人家的墓碑；
- 「办公设备维修」：先检测报价旧件交回（消保法第五十二条）、配件写明原装兼容、设备硬盘里的文件不拷不带
  （数据安全法第二十七条）、废硒鼓墨盒按规定回收、打测试页写清保修。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091）离线试过。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_tomb_pack_verifies_the_grave_and_never_burns():
    d, problems = schema.validate(_load("proxy-tomb-sweeping"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("核对碑文" in f for f in a.forbidden) and any("加项目加钱" in f for f in a.forbidden)
    assert any("焚烧" in f for f in a.forbidden) and any("旧照片" in f for f in a.forbidden)
    assert any("别人家的墓碑" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["代祭扫"]
    t = d.task_templates[0].description
    assert "碑文" in t and "不焚烧" in t and "带时间" in t


def test_office_repair_pack_quotes_first_and_leaves_the_files_alone():
    d, problems = schema.validate(_load("office-equipment-repair"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不报价就换件" in f for f in a.forbidden) and any("冒充原装" in f for f in a.forbidden)
    assert any("设备里的文件" in f for f in a.forbidden) and any("废硒鼓" in f for f in a.forbidden)
    assert any("保修" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["办公设备维修"]
    t = d.task_templates[0].description
    assert "先检测报价" in t and "文件不拷不带" in t and "保修" in t


@pytest.mark.parametrize("key", ["proxy-tomb-sweeping", "office-equipment-repair"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600045201")
    for title, cat in (("清明替我去给爷爷扫墓", "代祭扫"), ("办公室复印机卡纸", "办公设备维修")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452001", "13700452002"), "墓位怎么核对", "先核对墓位和碑文，对上了再动手"),
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452003", "13700452004"), "能临时加项目吗", "按家属要的项目做，事先没说的不加、不加钱"),
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452005", "13700452006"), "能烧纸吗", "守墓园和林区的防火规定，不焚烧不放鞭炮"),
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452007", "13700452008"), "照片怎么拍", "带时间的连续照片或视频，如实回报，不拿旧照片充数"),
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452009", "13700452010"), "能拍别人家的墓碑吗", "举止庄重，不拍别人家的墓碑和人，照片只发委托人"),
    ("office-equipment-repair", "office-repair-helper", ("13700452011", "13700452012"), "换件前要报价吗", "先检测报价，换件前客户同意，旧件交回"),
    ("office-equipment-repair", "office-repair-helper", ("13700452013", "13700452014"), "配件是原装的吗", "配件写明原装还是兼容，价格分开写"),
    ("office-equipment-repair", "office-repair-helper", ("13700452015", "13700452016"), "复印机硬盘里的文件怎么办", "设备硬盘里的文件不拷贝不带走，换下的硬盘交回或当面清除"),
    ("office-equipment-repair", "office-repair-helper", ("13700452017", "13700452018"), "废硒鼓怎么处理", "废硒鼓墨盒按规定交回收，不乱丢"),
    ("office-equipment-repair", "office-repair-helper", ("13700452019", "13700452020"), "保修多久", "修好打测试页、讲清保养，保修期写在单子上"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452021", "13700452022"), "扫错了", "先核对墓位和碑文，对上了再动手"),
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452023", "13700452024"), "坐地起价", "按家属要的项目做，事先没说的不加、不加钱"),
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452025", "13700452026"), "引着", "守墓园和林区的防火规定，不焚烧不放鞭炮"),
    ("proxy-tomb-sweeping", "tomb-sweeping-helper", ("13700452027", "13700452028"), "一模一样", "带时间的连续照片或视频，如实回报，不拿旧照片充数"),
    ("office-equipment-repair", "office-repair-helper", ("13700452029", "13700452030"), "收了八百", "先检测报价，换件前客户同意，旧件交回"),
    ("office-equipment-repair", "office-repair-helper", ("13700452031", "13700452032"), "漏粉", "配件写明原装还是兼容，价格分开写"),
    ("office-equipment-repair", "office-repair-helper", ("13700452033", "13700452034"), "被谁看过", "设备硬盘里的文件不拷贝不带走，换下的硬盘交回或当面清除"),
    ("office-equipment-repair", "office-repair-helper", ("13700452035", "13700452036"), "又卡纸", "修好打测试页、讲清保养，保修期写在单子上"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
