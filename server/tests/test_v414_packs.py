"""SCN-278 / SCN-279 第四十九轮场景发掘：会议录音整理纪要、旧家具翻新（387 号 spec，V414）。

两个新类目都不要资质：
- 「会议纪要」：录音要让与会的人知道（偷录的不接）、决定与讨论分开写、人名数字拿不准的标出来、只用于这一单交付后删除、AI 初稿逐段核对；
- 「家具翻新」：先认清实木贴皮板材、背面试色、环保木器漆通风干透、先铺保护收粉尘、开裂松动先修结构不承诺如新。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_minutes_pack_refuses_covert_recordings_and_keeps_decisions_honest():
    d, problems = schema.validate(_load("meeting-minutes"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("偷录" in f for f in a.forbidden) and any("讨论写成已经决定" in f for f in a.forbidden)
    assert any("自己猜" in f for f in a.forbidden) and any("放进别的工具" in f for f in a.forbidden)
    assert any("AI" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["会议纪要"]
    t = d.task_templates[0].description
    assert "与会的人都知道在录" in t and "决定事项单列" in t and "交付后删除" in t


def test_refinish_pack_knows_the_material_and_never_promises_like_new():
    d, problems = schema.validate(_load("furniture-refinish"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不认材质" in f for f in a.forbidden) and any("不试色" in f for f in a.forbidden)
    assert any("不通风" in f for f in a.forbidden) and any("跟新的一样" in f for f in a.forbidden)
    assert any("保护" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["家具翻新"]
    t = d.task_templates[0]
    assert "背面试色" in t.description and "环保木器漆" in t.description and t.visits_planned == 2


@pytest.mark.parametrize("key", ["meeting-minutes", "furniture-refinish"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600041401")
    for title, cat in (("整理周例会纪要", "会议纪要"), ("旧餐桌翻新改色", "家具翻新")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("meeting-minutes", "meeting-minutes-helper", ("13900005401", "13900005402"), "录音要让大家知道吗", "录音要让与会的人知道，偷录的不接"),
    ("meeting-minutes", "meeting-minutes-helper", ("13900005403", "13900005404"), "谁负责什么时候完", "把决定和讨论分开写：谁负责、什么时候完"),
    ("meeting-minutes", "meeting-minutes-helper", ("13900005405", "13900005406"), "人名数字拿不准怎么办", "人名、数字、专有名词拿不准的标出来请对方确认"),
    ("meeting-minutes", "meeting-minutes-helper", ("13900005407", "13900005408"), "录音和纪要能给别人吗", "录音和纪要只用于这一单，交付后删除"),
    ("meeting-minutes", "meeting-minutes-helper", ("13900005409", "13900005410"), "AI 转写要核对吗", "AI 转写和初稿要逐段对着录音核对，交付时说清"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005411", "13900005412"), "实木贴皮板材怎么分", "先认清实木、贴皮还是板材，再定怎么翻新"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005413", "13900005414"), "颜色先在背面试吗", "颜色先在背面或底下试一小块"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005415", "13900005416"), "用什么漆", "用环保木器漆，开窗通风，干透再用"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005417", "13900005418"), "打磨的粉尘怎么办", "地面墙面先铺保护，打磨粉尘收干净"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005419", "13900005420"), "开裂松动怎么修", "开裂松动先修结构；不承诺跟新的一样"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("meeting-minutes", "meeting-minutes-helper", ("13900005421", "13900005422"), "列行动项吗", "把决定和讨论分开写：谁负责、什么时候完"),
    ("meeting-minutes", "meeting-minutes-helper", ("13900005423", "13900005424"), "张冠李戴了", "人名、数字、专有名词拿不准的标出来请对方确认"),
    ("meeting-minutes", "meeting-minutes-helper", ("13900005425", "13900005426"), "涉及商业秘密", "录音和纪要只用于这一单，交付后删除"),
    ("meeting-minutes", "meeting-minutes-helper", ("13900005427", "13900005428"), "机器转写的", "AI 转写和初稿要逐段对着录音核对，交付时说清"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005429", "13900005430"), "怎么看是不是实木", "先认清实木、贴皮还是板材，再定怎么翻新"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005431", "13900005432"), "偏红了", "颜色先在背面或底下试一小块"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005433", "13900005434"), "满屋灰", "地面墙面先铺保护，打磨粉尘收干净"),
    ("furniture-refinish", "furniture-refinish-helper", ("13900005435", "13900005436"), "椅子快散架了", "开裂松动先修结构；不承诺跟新的一样"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
