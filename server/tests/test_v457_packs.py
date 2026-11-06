"""SCN-320 / SCN-321 第七十轮场景发掘：淋浴房安装、智能马桶安装（430 号 spec，V457）。

- 「淋浴房安装」不要资质：只装有 3C 标志的钢化玻璃并贴防爆膜（强制性产品认证管理规定）、打孔不打穿防水层
  （住宅室内装饰装修管理办法第五条）、挡水坡向地漏、密封胶固化前不用水、五金拧紧装限位；
- 「智能马桶安装」不强制资质，新拉插座可加选电工证（安全生产法第三十条）：先量坑距、插座接地带漏保不拖插排、
  不伤防水层换新密封圈、角阀过滤器试水试电、拆旧写进报价。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091，含 PACK-093 逐个标签检查）离线试过。
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


def test_shower_pack_installs_only_certified_tempered_glass_with_film():
    d, problems = schema.validate(_load("shower-enclosure"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("3C" in f for f in a.forbidden) and any("打穿防水层" in f for f in a.forbidden)
    assert any("坡向地漏" in f for f in a.forbidden) and any("没固化" in f for f in a.forbidden)
    assert any("限位" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["淋浴房安装"]
    t = d.task_templates[0].description
    assert "3C" in t and "防爆膜" in t and "不打穿防水层" in t


def test_smart_toilet_pack_measures_first_and_wants_a_grounded_rcd_socket():
    d, problems = schema.validate(_load("smart-toilet-install"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("坑距" in f for f in a.forbidden) and any("插排拖线" in f for f in a.forbidden)
    assert any("防水层" in f for f in a.forbidden) and any("角阀" in f for f in a.forbidden)
    assert any("拆旧" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    cat = _categories()["智能马桶安装"]
    assert "required_cert" not in cat and cat["optional_certs"] == [ELECTRICIAN_CERT]
    t = d.task_templates[0].description
    assert "先量后装" in t and "不用插排拖线" in t and "换新密封圈" in t


@pytest.mark.parametrize("key", ["shower-enclosure", "smart-toilet-install"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_and_the_toilet_can_ask_for_an_electrician(client, requester):
    w = make_verified(client, "13600045701")
    for title, cat in (("主卫装钻石形淋浴房", "淋浴房安装"), ("换装智能马桶插座现成", "智能马桶安装")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text
    wired = _post(client, requester, title="智能马桶要新拉插座", description="卫生间没有插座", category="智能马桶安装",
                  task_certs=[ELECTRICIAN_CERT]).json()
    no = client.post(f"{API}/tasks/{wired['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and ELECTRICIAN_CERT in no.json()["detail"]["message"], no.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("shower-enclosure", "shower-enclosure-helper", ("13700457001", "13700457002"), "玻璃要看什么标志", "玻璃要有 3C 标志的钢化玻璃，装好贴防爆膜"),
    ("shower-enclosure", "shower-enclosure-helper", ("13700457003", "13700457004"), "打孔要注意什么", "打孔前探管线，不打穿防水层，孔里打胶封住"),
    ("shower-enclosure", "shower-enclosure-helper", ("13700457005", "13700457006"), "挡水条怎么装", "挡水条和底座找平、坡向地漏，洗完不积水"),
    ("shower-enclosure", "shower-enclosure-helper", ("13700457007", "13700457008"), "密封胶多久能用水", "玻璃和墙地之间打满防霉密封胶，固化前一天不用水"),
    ("shower-enclosure", "shower-enclosure-helper", ("13700457009", "13700457010"), "铰链要拧紧吗", "铰链滑轮拧紧装限位，交付时教用法、提醒别撞玻璃边角"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457011", "13700457012"), "坑距怎么量", "先量坑距和进水排污位置，型号对上再装"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457013", "13700457014"), "插座要接地吗", "插座要接地、带漏电保护、装防溅盒，不用插排拖线"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457015", "13700457016"), "密封圈要换吗", "不破坏地面防水层，法兰密封圈换新的、四周打胶"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457017", "13700457018"), "角阀要装吗", "进水装角阀和过滤器，通水通电试冲洗试加热不漏"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457019", "13700457020"), "旧马桶怎么处理", "拆旧马桶带不带走、收不收钱写进报价"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("shower-enclosure", "shower-enclosure-helper", ("13700457021", "13700457022"), "碎了一地", "玻璃要有 3C 标志的钢化玻璃，装好贴防爆膜"),
    ("shower-enclosure", "shower-enclosure-helper", ("13700457023", "13700457024"), "楼下天花板", "打孔前探管线，不打穿防水层，孔里打胶封住"),
    ("shower-enclosure", "shower-enclosure-helper", ("13700457025", "13700457026"), "一层水", "挡水条和底座找平、坡向地漏，洗完不积水"),
    ("shower-enclosure", "shower-enclosure-helper", ("13700457027", "13700457028"), "往下掉", "铰链滑轮拧紧装限位，交付时教用法、提醒别撞玻璃边角"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457029", "13700457030"), "差了十厘米", "先量坑距和进水排污位置，型号对上再装"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457031", "13700457032"), "麻手", "插座要接地、带漏电保护、装防溅盒，不用插排拖线"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457033", "13700457034"), "天花板都黄了", "不破坏地面防水层，法兰密封圈换新的、四周打胶"),
    ("smart-toilet-install", "smart-toilet-helper", ("13700457035", "13700457036"), "滋水", "进水装角阀和过滤器，通水通电试冲洗试加热不漏"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
