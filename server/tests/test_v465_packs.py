"""SCN-327 / SCN-328 第七十三轮场景发掘：签证材料准备、门窗五金维修（438 号 spec，V465）。

- 「签证材料准备」不要资质：以使领馆官网最新清单为准；只用真实材料、不代签（刑法第二百八十条，发单拦截 437 号同一条线）；
  证件信息用完即删（个保法第六条）；预约递交由本人、不承诺出签（消保法第二十条）；按件报价写清签证费另付；
- 「门窗五金维修」不强制资质，到室外高处作业可加选高处作业证（安全生产法第三十条）：认窗型带对配件、
  推拉扇两人抬、外开扇系安全绳不探身、换密封条通排水孔、旧件给客户看试开关。
问法写测试之前都先用 scripts/pack_probe.py 离线试过；写完用 scripts/pack_mutate.py（PACK-094）做变异红验。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import HEIGHT_WORK_CERT
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_visa_pack_uses_only_real_materials_and_never_promises_a_visa():
    d, problems = schema.validate(_load("visa-docs-helper"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不看官网" in f for f in a.forbidden) and any("假流水" in f for f in a.forbidden)
    assert any("替客户签名" in f for f in a.forbidden) and any("不删" in f for f in a.forbidden)
    assert any("包过费" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["签证材料准备"]
    t = d.task_templates[0].description
    assert "官网最新清单" in t and "只用真实材料" in t and "删副本" in t
    # 包里说不做假流水，发单拦截也真的拦（437 号同一条线）
    assert restricted_errand("帮我做一份假流水办签证") == "forged_documents"


def test_window_pack_ties_the_outward_sash_and_shows_the_old_parts():
    d, problems = schema.validate(_load("door-window-repair"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不认窗型" in f for f in a.forbidden) and any("一个人拆" in f for f in a.forbidden)
    assert any("安全绳" in f for f in a.forbidden) and any("排水孔" in f for f in a.forbidden)
    assert any("旧件" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    cat = _categories()["门窗五金维修"]
    assert "required_cert" not in cat and cat["optional_certs"] == [HEIGHT_WORK_CERT]
    t = d.task_templates[0].description
    assert "两人抬" in t and "安全绳" in t and "试开关" in t


@pytest.mark.parametrize("key", ["visa-docs-helper", "door-window-repair"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_and_the_window_can_ask_for_height_work(client, requester):
    w = make_verified(client, "13600046501")
    for title, cat in (("申根签证材料整理", "签证材料准备"), ("推拉窗换滑轮", "门窗五金维修")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text
    high = _post(client, requester, title="十二楼外开窗换合页", description="要到室外", category="门窗五金维修",
                 task_certs=[HEIGHT_WORK_CERT]).json()
    no = client.post(f"{API}/tasks/{high['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and HEIGHT_WORK_CERT in no.json()["detail"]["message"], no.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("visa-docs-helper", "visa-docs-helper", ("13700465001", "13700465002"), "材料清单以什么为准", "以使领馆或签证中心官网的最新清单为准，按申请人情况逐项列"),
    ("visa-docs-helper", "visa-docs-helper", ("13700465003", "13700465004"), "流水不够怎么办", "材料只用真实的：不做假流水、假在职证明，表格由本人签名"),
    ("visa-docs-helper", "visa-docs-helper", ("13700465005", "13700465006"), "身份证信息怎么用", "护照、身份证、银行卡信息只用于这次申请，交付后删掉副本"),
    ("visa-docs-helper", "visa-docs-helper", ("13700465007", "13700465008"), "能保证出签吗", "预约、递交、录指纹由本人去，不承诺出签"),
    ("visa-docs-helper", "visa-docs-helper", ("13700465009", "13700465010"), "签证费包含吗", "按整理和翻译的件数报价，写清签证费另付、被拒怎么算"),
    ("door-window-repair", "door-window-helper", ("13700465011", "13700465012"), "配件怎么带", "先让客户拍照认清窗型和五金，带对型号的配件"),
    ("door-window-repair", "door-window-helper", ("13700465013", "13700465014"), "推拉门换滑轮", "推拉扇换滑轮要两个人抬，地上垫软的防玻璃磕碰"),
    ("door-window-repair", "door-window-helper", ("13700465015", "13700465016"), "外开窗换合页", "外开窗换合页执手在室内操作，窗扇系安全绳，人不探出窗外"),
    ("door-window-repair", "door-window-helper", ("13700465017", "13700465018"), "漏风怎么修", "漏风漏雨换密封条，通开排水孔"),
    ("door-window-repair", "door-window-helper", ("13700465019", "13700465020"), "旧件要给看吗", "按配件加工时报价，旧件给客户看，装好开关几次再走"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("visa-docs-helper", "visa-docs-helper", ("13700465021", "13700465022"), "白跑", "以使领馆或签证中心官网的最新清单为准，按申请人情况逐项列"),
    ("visa-docs-helper", "visa-docs-helper", ("13700465023", "13700465024"), "黑名单", "材料只用真实的：不做假流水、假在职证明，表格由本人签名"),
    ("visa-docs-helper", "visa-docs-helper", ("13700465025", "13700465026"), "盗用", "护照、身份证、银行卡信息只用于这次申请，交付后删掉副本"),
    ("visa-docs-helper", "visa-docs-helper", ("13700465027", "13700465028"), "打包票", "预约、递交、录指纹由本人去，不承诺出签"),
    ("door-window-repair", "door-window-helper", ("13700465029", "13700465030"), "跑两趟", "先让客户拍照认清窗型和五金，带对型号的配件"),
    ("door-window-repair", "door-window-helper", ("13700465031", "13700465032"), "掉轨", "推拉扇换滑轮要两个人抬，地上垫软的防玻璃磕碰"),
    ("door-window-repair", "door-window-helper", ("13700465033", "13700465034"), "探出去", "外开窗换合页执手在室内操作，窗扇系安全绳，人不探出窗外"),
    ("door-window-repair", "door-window-helper", ("13700465035", "13700465036"), "呼呼响", "漏风漏雨换密封条，通开排水孔"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
