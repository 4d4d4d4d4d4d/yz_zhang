"""SCN-267 / SCN-268 第四十四轮场景发掘：布艺沙发床垫清洗除螨、PPT 设计代做（375 号 spec，V402）。

两个新类目都不要资质：
- 「沙发床垫清洗」：先看面料标签、角落先试、不泡透、讲清晾干、不拿显微镜演示推销；
- 「PPT 设计」（创作者）：内容由甲方给不编数据、素材字体有商用授权、样张与改稿轮数写清、
  不代做作业与学位论文答辩稿（与发单拦截 SCN-210 同一条线）、客户资料不进作品集。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_sofa_pack_checks_the_fabric_and_never_soaks():
    d, problems = schema.validate(_load("sofa-mattress-cleaning"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("面料标签" in f for f in a.forbidden) and any("角落试" in f for f in a.forbidden)
    assert any("泡透" in f for f in a.forbidden) and any("显微镜" in f for f in a.forbidden)
    assert {"money", "publish"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["沙发床垫清洗"]
    t = d.task_templates[0].description
    assert "先在角落试清洁剂" in t and "不泡透" in t and "不推销产品" in t


def test_ppt_pack_licenses_assets_and_refuses_coursework_like_the_guard():
    d, problems = schema.validate(_load("ppt-design"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("没有授权" in f for f in a.forbidden) and any("编造数据" in f for f in a.forbidden)
    assert any("学位论文答辩稿" in f for f in a.forbidden) and any("作品集" in f for f in a.forbidden)
    assert any("改稿轮数" in f for f in a.forbidden)
    assert {"money", "sign", "publish"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["PPT 设计"]
    t = d.task_templates[0].description
    assert "先出 3 页样张" in t and "有商用授权" in t and "不放作品集" in t
    # 包里说不接的，发单拦截也真的拦（同一条线：SCN-210）
    assert restricted_errand("帮我代做毕业答辩PPT，学位论文答辩用") is not None


@pytest.mark.parametrize("key", ["sofa-mattress-cleaning", "ppt-design"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600040201")
    for title, cat in (("三人位布艺沙发清洗", "沙发床垫清洗"), ("融资路演 PPT 二十页", "PPT 设计")):
        t = _post(client, requester, title=title, description="下周前", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004901", "13900004902"), "洗涤标签上的 S 是什么意思", "先看面料和洗涤标签，不能水洗的不硬洗"),
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004903", "13900004904"), "绒面沙发洗完有水印怎么办", "清洁剂先在角落试一小块"),
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004905", "13900004906"), "床垫会不会洗得发霉", "只湿表面、边洗边吸，不把海绵和床垫芯泡透"),
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004907", "13900004908"), "洗完要开窗通风吗", "洗完开窗通风，讲清多久能坐能睡"),
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004909", "13900004910"), "要不要推荐除螨仪", "不拿显微镜、紫外灯演示吓唬人推销"),
    ("ppt-design", "ppt-design-helper", ("13900004911", "13900004912"), "16:9 还是 4:3", "先问清用途、比例和软件，再动手"),
    ("ppt-design", "ppt-design-helper", ("13900004913", "13900004914"), "数据不全能自己补吗", "内容和数据由甲方给，不编数据、不替他下结论"),
    ("ppt-design", "ppt-design-helper", ("13900004915", "13900004916"), "网上的图片能直接用吗", "图片、图标、字体用有商用授权的，记下出处"),
    ("ppt-design", "ppt-design-helper", ("13900004917", "13900004918"), "改稿轮数怎么约定", "先出样张定风格，改稿轮数写进约定"),
    ("ppt-design", "ppt-design-helper", ("13900004919", "13900004920"), "能放进作品集吗", "不代做作业和答辩稿；客户资料不进作品集"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004921", "13900004922"), "真皮的呢", "先看面料和洗涤标签，不能水洗的不硬洗"),
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004923", "13900004924"), "会掉色吗", "清洁剂先在角落试一小块"),
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004925", "13900004926"), "床垫一直不干", "只湿表面、边洗边吸，不把海绵和床垫芯泡透"),
    ("sofa-mattress-cleaning", "sofa-cleaning-helper", ("13900004927", "13900004928"), "一直咳嗽", "洗完开窗通风，讲清多久能坐能睡"),
    ("ppt-design", "ppt-design-helper", ("13900004929", "13900004930"), "做错了怎么办", "先问清用途、比例和软件，再动手"),
    ("ppt-design", "ppt-design-helper", ("13900004931", "13900004932"), "收到律师发函", "图片、图标、字体用有商用授权的，记下出处"),
    ("ppt-design", "ppt-design-helper", ("13900004933", "13900004934"), "改得没完没了", "先出样张定风格，改稿轮数写进约定"),
    ("ppt-design", "ppt-design-helper", ("13900004935", "13900004936"), "毕设能接吗", "不代做作业和答辩稿；客户资料不进作品集"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
