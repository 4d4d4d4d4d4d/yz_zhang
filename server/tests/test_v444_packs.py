"""SCN-304 / SCN-305 第六十二轮场景发掘：电视投影挂装、空置房屋代看护（417 号 spec，V444）。

两个新类目都不要资质：
- 「电视投影挂装」：先看墙体（石膏板找龙骨或加背板）、打孔前探水电管线、挂架承重留余量、
  走线不剔承重墙（住宅室内装饰装修管理办法第五条）、装完试机调平清灰；
- 「空置房屋代看护」：钥匙交接有记录并归还（民法典第九百二十二条）、按约定时间上门并回报（第九百二十四条）、
  水电气门窗逐项查、只拍检查项不翻柜子（个保法第六条）、不住不用不带人。
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


def test_tv_mount_pack_checks_the_wall_and_the_pipes_first():
    d, problems = schema.validate(_load("tv-mount"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("石膏板墙" in f for f in a.forbidden) and any("不探管线" in f for f in a.forbidden)
    assert any("承重不留余量" in f for f in a.forbidden) and any("剔承重墙" in f for f in a.forbidden)
    assert any("不试挂" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["电视投影挂装"]
    t = d.task_templates[0].description
    assert "探水电管线" in t and "不剔承重墙" in t and "试机" in t


def test_vacant_home_pack_keeps_records_and_stays_out_of_private_things():
    d, problems = schema.validate(_load("vacant-home-care"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不留记录" in f for f in a.forbidden) and any("不按约定时间" in f for f in a.forbidden)
    assert any("水电气门窗" in f for f in a.forbidden) and any("翻柜子" in f for f in a.forbidden)
    assert any("带别人进门" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["空置房屋代看护"]
    t = d.task_templates[0].description
    assert "交接写记录" in t and "拍照回报" in t and "不住不用不带人" in t


@pytest.mark.parametrize("key", ["tv-mount", "vacant-home-care"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600044401")
    for title, cat in (("客厅挂 75 寸电视", "电视投影挂装"), ("出国三个月帮忙看家", "空置房屋代看护")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("tv-mount", "tv-mount-helper", ("13700444001", "13700444002"), "石膏板墙能挂电视吗", "先看墙体：实墙用膨胀螺栓，石膏板找龙骨或加背板"),
    ("tv-mount", "tv-mount-helper", ("13700444003", "13700444004"), "打孔前要做什么", "打孔前探水电管线，避开开关插座的上下方"),
    ("tv-mount", "tv-mount-helper", ("13700444005", "13700444006"), "挂架承重要多少", "挂架承重按电视重量留余量，伸缩挂架更要打牢"),
    ("tv-mount", "tv-mount-helper", ("13700444007", "13700444008"), "线怎么藏", "走线用线槽或预埋管，不剔承重墙和梁柱"),
    ("tv-mount", "tv-mount-helper", ("13700444009", "13700444010"), "装完要检查什么", "装完试挂、试机、调水平，灰尘收拾干净再走"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444011", "13700444012"), "钥匙怎么交接", "钥匙交接有记录，结束时归还或请房主改密码"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444013", "13700444014"), "上门频次怎么定", "按约定的时间上门，每次在平台签到回报"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444015", "13700444016"), "要查燃气阀吗", "水电气门窗漏水逐项查，开窗通风，异常先关阀断电"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444017", "13700444018"), "回报照片要拍哪些", "只拍检查项，不翻柜子、不拍私人物品"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444019", "13700444020"), "能在房子里住吗", "不在房子里住、不用房主的东西、不带别人进门"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("tv-mount", "tv-mount-helper", ("13700444021", "13700444022"), "掉下来", "先看墙体：实墙用膨胀螺栓，石膏板找龙骨或加背板"),
    ("tv-mount", "tv-mount-helper", ("13700444023", "13700444024"), "楼下漏水", "打孔前探水电管线，避开开关插座的上下方"),
    ("tv-mount", "tv-mount-helper", ("13700444025", "13700444026"), "下坠", "挂架承重按电视重量留余量，伸缩挂架更要打牢"),
    ("tv-mount", "tv-mount-helper", ("13700444027", "13700444028"), "满地灰", "装完试挂、试机、调水平，灰尘收拾干净再走"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444029", "13700444030"), "没还", "钥匙交接有记录，结束时归还或请房主改密码"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444031", "13700444032"), "失联", "按约定的时间上门，每次在平台签到回报"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444033", "13700444034"), "冻裂", "水电气门窗漏水逐项查，开窗通风，异常先关阀断电"),
    ("vacant-home-care", "vacant-home-care-helper", ("13700444035", "13700444036"), "翻东西", "只拍检查项，不翻柜子、不拍私人物品"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
