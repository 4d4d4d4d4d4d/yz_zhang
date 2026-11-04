"""SCN-280 / SCN-281 第五十轮场景发掘：装修垃圾清运、Logo 设计（389 号 spec，V416）。

两个新类目都不要资质：
- 「装修垃圾清运」：先看量按车或按袋报价不中途加价、运到消纳场不乱倒、电梯楼道先铺保护、可回收和有害的分开、拉走前对一遍；
- 「Logo 设计」：先问清需求、原创不抄、要注册的请商标代理检索不保证能注册、方案数轮数与交付文件写清、著作权归属书面约定。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_debris_pack_quotes_up_front_and_never_dumps():
    d, problems = schema.validate(_load("renovation-debris"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("中途加价" in f for f in a.forbidden) and any("随便倒掉" in f for f in a.forbidden)
    assert any("不铺保护" in f for f in a.forbidden) and any("油漆桶" in f for f in a.forbidden)
    assert any("不跟业主核对" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["装修垃圾清运"]
    t = d.task_templates[0]
    assert "运到正规消纳场" in t.description and "先铺保护" in t.description and "哪些要留" in t.description


def test_logo_pack_stays_original_and_puts_copyright_in_writing():
    d, problems = schema.validate(_load("logo-design"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("模仿或套用" in f for f in a.forbidden) and any("保证一定能注册" in f for f in a.forbidden)
    assert any("矢量源文件" in f for f in a.forbidden) and any("著作权归属" in f for f in a.forbidden)
    assert any("修改轮数" in f for f in a.forbidden)
    assert {"money", "publish", "sign"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["Logo 设计"]
    t = d.task_templates[0].description
    assert "原创" in t and "矢量源文件" in t and "签书面约定" in t


@pytest.mark.parametrize("key", ["renovation-debris", "logo-design"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600041601")
    for title, cat in (("清运两车装修垃圾", "装修垃圾清运"), ("咖啡店 Logo", "Logo 设计")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("renovation-debris", "renovation-debris-helper", ("13900005501", "13900005502"), "按车还是按袋报价", "先看量，按车或按袋报价，写清含什么，不中途加价"),
    ("renovation-debris", "renovation-debris-helper", ("13900005503", "13900005504"), "运到哪个消纳场", "运到当地规定的消纳场，不乱倒、不混生活垃圾"),
    ("renovation-debris", "renovation-debris-helper", ("13900005505", "13900005506"), "电梯要铺保护吗", "电梯楼道先铺保护，按物业规定的时间运"),
    ("renovation-debris", "renovation-debris-helper", ("13900005507", "13900005508"), "油漆桶灯管怎么处理", "可回收的分开，油漆桶灯管单独处理"),
    ("renovation-debris", "renovation-debris-helper", ("13900005509", "13900005510"), "要留的东西怎么办", "拉走前和业主对一遍哪些要清、哪些要留"),
    ("logo-design", "logo-design-helper", ("13900005511", "13900005512"), "先问清行业名字吗", "先问清行业、名字、客户和用在哪，再动笔"),
    ("logo-design", "logo-design-helper", ("13900005513", "13900005514"), "能参考别人的标志吗", "原创设计，不抄别人的标志、不套知名品牌"),
    ("logo-design", "logo-design-helper", ("13900005515", "13900005516"), "能保证注册商标吗", "要注册的先请商标代理检索，设计师不保证能注册"),
    ("logo-design", "logo-design-helper", ("13900005517", "13900005518"), "交付哪些文件", "方案数、修改轮数、交付文件写清楚"),
    ("logo-design", "logo-design-helper", ("13900005519", "13900005520"), "著作权归谁", "著作权归谁、转让还是授权使用，写进书面约定"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("renovation-debris", "renovation-debris-helper", ("13900005521", "13900005522"), "坐地起价", "先看量，按车或按袋报价，写清含什么，不中途加价"),
    ("renovation-debris", "renovation-debris-helper", ("13900005523", "13900005524"), "物业不让", "电梯楼道先铺保护，按物业规定的时间运"),
    ("renovation-debris", "renovation-debris-helper", ("13900005525", "13900005526"), "能卖废品吗", "可回收的分开，油漆桶灯管单独处理"),
    ("renovation-debris", "renovation-debris-helper", ("13900005527", "13900005528"), "拉错了", "拉走前和业主对一遍哪些要清、哪些要留"),
    ("logo-design", "logo-design-helper", ("13900005529", "13900005530"), "没感觉", "先问清行业、名字、客户和用在哪，再动笔"),
    ("logo-design", "logo-design-helper", ("13900005531", "13900005532"), "跟别人撞车了", "原创设计，不抄别人的标志、不套知名品牌"),
    ("logo-design", "logo-design-helper", ("13900005533", "13900005534"), "驳回了", "要注册的先请商标代理检索，设计师不保证能注册"),
    ("logo-design", "logo-design-helper", ("13900005535", "13900005536"), "买断吗", "著作权归谁、转让还是授权使用，写进书面约定"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
