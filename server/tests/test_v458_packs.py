"""SCN-322 / SCN-323 第七十一轮场景发掘：远程电脑协助、电动晾衣架安装（431 号 spec，V458）。

- 「远程电脑协助」不要资质：客户发起连接、结束关掉无人值守；不翻无关文件（个保法第六条）；
  不要验证码不让转账、提醒远程退款骗局（反电信网络诈骗法）；改动前先备份；解决不了按约定不收；
- 「电动晾衣架安装」不强制资质，新拉线路可加选电工证（安全生产法第三十条）：打进楼板不只挂龙骨、
  打孔前探线管、断电防潮接线、试升降遇阻停、清灰交代保修。
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


def test_remote_pack_leaves_no_backdoor_and_never_asks_for_codes():
    d, problems = schema.validate(_load("remote-pc-help"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("无人值守" in f for f in a.forbidden) and any("无关的文件" in f for f in a.forbidden)
    assert any("验证码" in f for f in a.forbidden) and any("不备份" in f for f in a.forbidden)
    assert any("全额收费" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["远程电脑协助"]
    t = d.task_templates[0].description
    assert "客户发起连接" in t and "不要验证码" in t and "先备份" in t


def test_rack_pack_anchors_into_the_slab_and_stops_on_obstruction():
    d, problems = schema.validate(_load("clothes-rack-install"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("吊顶龙骨" in f for f in a.forbidden) and any("探管线" in f for f in a.forbidden)
    assert any("防潮" in f for f in a.forbidden) and any("试升降" in f for f in a.forbidden)
    assert any("清灰" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    cat = _categories()["电动晾衣架安装"]
    assert "required_cert" not in cat and cat["optional_certs"] == [ELECTRICIAN_CERT]
    t = d.task_templates[0].description
    assert "打进楼板" in t and "探管线" in t and "遇阻停" in t


@pytest.mark.parametrize("key", ["remote-pc-help", "clothes-rack-install"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_and_the_rack_can_ask_for_an_electrician(client, requester):
    w = make_verified(client, "13600045801")
    for title, cat in (("电脑开机蓝屏远程看看", "远程电脑协助"), ("阳台装手摇晾衣架", "电动晾衣架安装")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text
    wired = _post(client, requester, title="电动晾衣架要新拉线", description="阳台没有插座", category="电动晾衣架安装",
                  task_certs=[ELECTRICIAN_CERT]).json()
    no = client.post(f"{API}/tasks/{wired['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and ELECTRICIAN_CERT in no.json()["detail"]["message"], no.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("remote-pc-help", "remote-pc-helper", ("13700458001", "13700458002"), "无人值守要关吗", "每次由客户发起连接、看着屏幕，结束后断开并关掉无人值守"),
    ("remote-pc-help", "remote-pc-helper", ("13700458003", "13700458004"), "能看我的文件吗", "只处理客户说的问题，不翻与问题无关的文件"),
    ("remote-pc-help", "remote-pc-helper", ("13700458005", "13700458006"), "要验证码吗", "不要验证码、支付密码，不让客户转账，碰到「远程退款」先提醒是骗局"),
    ("remote-pc-help", "remote-pc-helper", ("13700458007", "13700458008"), "删文件前要备份吗", "改系统设置、删文件前先备份，说清会改什么"),
    ("remote-pc-help", "remote-pc-helper", ("13700458009", "13700458010"), "没修好收钱吗", "按次或按时长报价，解决不了按事先约定不收或少收"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458011", "13700458012"), "吊顶能装晾衣架吗", "吊顶下面要用长螺栓打进混凝土楼板，不只挂在龙骨上"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458013", "13700458014"), "打孔要注意什么", "打孔前探楼板里的电线管和水管"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458015", "13700458016"), "电动的怎么接电", "接电先断电，接头防潮，新拉线路持电工证"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458017", "13700458018"), "能挂多重", "按说明的承重用，装好试升降，遇阻要能自动停"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458019", "13700458020"), "装完要交代什么", "装完清理粉尘，交代遥控、限位和保修"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("remote-pc-help", "remote-pc-helper", ("13700458021", "13700458022"), "随时连进来", "每次由客户发起连接、看着屏幕，结束后断开并关掉无人值守"),
    ("remote-pc-help", "remote-pc-helper", ("13700458023", "13700458024"), "银行卡被刷", "不要验证码、支付密码，不让客户转账，碰到「远程退款」先提醒是骗局"),
    ("remote-pc-help", "remote-pc-helper", ("13700458025", "13700458026"), "全没了", "改系统设置、删文件前先备份，说清会改什么"),
    ("remote-pc-help", "remote-pc-helper", ("13700458027", "13700458028"), "白折腾", "按次或按时长报价，解决不了按事先约定不收或少收"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458029", "13700458030"), "整个掉下来", "吊顶下面要用长螺栓打进混凝土楼板，不只挂在龙骨上"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458031", "13700458032"), "整层跳闸", "打孔前探楼板里的电线管和水管"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458033", "13700458034"), "短路", "接电先断电，接头防潮，新拉线路持电工证"),
    ("clothes-rack-install", "clothes-rack-helper", ("13700458035", "13700458036"), "夹到", "按说明的承重用，装好试升降，遇阻要能自动停"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
