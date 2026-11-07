"""SCN-316 / SCN-317 第六十八轮场景发掘：太阳能热水器清洗维修、老录像带转数字（428 号 spec，V455）。

- 「太阳能热水器清洗维修」不强制资质，发单人可加选高处作业证、电工证（SCN-294b）：上屋顶看天气系安全带
  （安全生产法第三十条）、除垢剂按说明不用强酸、碎真空管收干净、电辅热断电加漏保、换件先报价（消保法第五十二条）；
- 「老录像带转数字」不要资质：原件清点逐盒交回、受损先说风险、文件只交客户删工作副本（个保法第六条）、
  只转家庭自录不复制商业影片（著作权法）、交付格式与分段写清。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091，含 PACK-093 逐个标签检查）离线试过。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import ELECTRICIAN_CERT, HEIGHT_WORK_CERT
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_solar_pack_stays_safe_on_the_roof_and_quotes_first():
    d, problems = schema.validate(_load("solar-heater-service"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("安全带" in f for f in a.forbidden) and any("强酸" in f for f in a.forbidden)
    assert any("碎真空管" in f for f in a.forbidden) and any("不断电" in f for f in a.forbidden)
    assert any("不报价" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    cat = _categories()["太阳能热水器清洗维修"]
    assert "required_cert" not in cat and cat["optional_certs"] == [HEIGHT_WORK_CERT, ELECTRICIAN_CERT]
    t = d.task_templates[0].description
    assert "雨雪大风不上屋顶" in t and "不用强酸" in t and "换件前同意" in t


def test_tape_pack_returns_every_original_and_keeps_footage_private():
    d, problems = schema.validate(_load("tape-digitization"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不清点" in f for f in a.forbidden) and any("不说风险" in f for f in a.forbidden)
    assert any("留存或外传" in f for f in a.forbidden) and any("商业影片" in f for f in a.forbidden)
    assert any("交付格式" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["老录像带转数字"]
    t = d.task_templates[0].description
    assert "逐盒核对" in t and "删工作副本" in t and "家庭自录" in t


@pytest.mark.parametrize("key", ["solar-heater-service", "tape-digitization"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_and_the_roof_job_can_ask_for_a_cert(client, requester):
    w = make_verified(client, "13600045501")
    for title, cat in (("一楼院子里的太阳能不热了", "太阳能热水器清洗维修"), ("二十盒老录像带转数字", "老录像带转数字")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text
    roof = _post(client, requester, title="六楼屋顶太阳能除垢", description="坡顶", category="太阳能热水器清洗维修",
                 task_certs=[HEIGHT_WORK_CERT]).json()
    no = client.post(f"{API}/tasks/{roof['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and HEIGHT_WORK_CERT in no.json()["detail"]["message"], no.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("solar-heater-service", "solar-heater-helper", ("13700455001", "13700455002"), "上屋顶要注意什么", "上屋顶前看天气，防滑系安全带，2 米以上持高处作业证"),
    ("solar-heater-service", "solar-heater-helper", ("13700455003", "13700455004"), "除垢剂怎么用", "除垢剂按说明配比、冲洗干净，不用强酸"),
    ("solar-heater-service", "solar-heater-helper", ("13700455005", "13700455006"), "真空管碎了怎么办", "碎真空管戴手套作业，碎玻璃全部收走，换管型号对上"),
    ("solar-heater-service", "solar-heater-helper", ("13700455007", "13700455008"), "电辅热怎么修", "电辅热和控制器接线先断电，回路加漏电保护"),
    ("solar-heater-service", "solar-heater-helper", ("13700455009", "13700455010"), "换件要先报价吗", "先检测报价，换件前客户同意，旧件交回"),
    ("tape-digitization", "tape-digitization-helper", ("13700455011", "13700455012"), "原件怎么交接", "原件当面清点登记，全程保管，交回时逐盒核对"),
    ("tape-digitization", "tape-digitization-helper", ("13700455013", "13700455014"), "发霉的带子能转吗", "发霉断带先说风险，修复另算，客户同意再做"),
    ("tape-digitization", "tape-digitization-helper", ("13700455015", "13700455016"), "文件会外传吗", "转出的文件只交客户，交付后删工作副本，不留存不外传"),
    ("tape-digitization", "tape-digitization-helper", ("13700455017", "13700455018"), "电影能转吗", "只转家庭自己录的，不复制商业影片"),
    ("tape-digitization", "tape-digitization-helper", ("13700455019", "13700455020"), "交付什么格式", "交付格式、介质、时长写清，每段标上内容和年份"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("solar-heater-service", "solar-heater-helper", ("13700455021", "13700455022"), "摔下来", "上屋顶前看天气，防滑系安全带，2 米以上持高处作业证"),
    ("solar-heater-service", "solar-heater-helper", ("13700455023", "13700455024"), "发黄", "除垢剂按说明配比、冲洗干净，不用强酸"),
    ("solar-heater-service", "solar-heater-helper", ("13700455025", "13700455026"), "玻璃渣", "碎真空管戴手套作业，碎玻璃全部收走，换管型号对上"),
    ("solar-heater-service", "solar-heater-helper", ("13700455027", "13700455028"), "被电", "电辅热和控制器接线先断电，回路加漏电保护"),
    ("tape-digitization", "tape-digitization-helper", ("13700455029", "13700455030"), "十八盒", "原件当面清点登记，全程保管，交回时逐盒核对"),
    ("tape-digitization", "tape-digitization-helper", ("13700455031", "13700455032"), "白点", "发霉断带先说风险，修复另算，客户同意再做"),
    ("tape-digitization", "tape-digitization-helper", ("13700455033", "13700455034"), "放到了网上", "转出的文件只交客户，交付后删工作副本，不留存不外传"),
    ("tape-digitization", "tape-digitization-helper", ("13700455035", "13700455036"), "三个小时", "交付格式、介质、时长写清，每段标上内容和年份"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
