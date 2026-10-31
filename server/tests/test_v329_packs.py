"""SCN-175 / SCN-176 第十二轮场景发掘：数码维修与旧机回收、陪驾（302 号 spec，V329）。

交付物是两个数据文件、两个新类目；「陪驾」要审核通过的驾驶证（三年以上驾龄）——实习期上高速须由这样的人陪同。
"""
import pytest

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_device_pack_keeps_customer_data_behind_the_line():
    d, problems = schema.validate(_load("device-repair-recycle"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("相册" in f for f in a.forbidden) and any("不清数据" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["数码维修与回收"]
    recycle = {t.key: t for t in d.task_templates}["device-recycle"]
    assert "已恢复出厂" in recycle.visit_checklist and "已关闭查找" in recycle.visit_checklist


def test_driving_pack_and_category_need_a_three_year_licence():
    d, problems = schema.validate(_load("driving-companion"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("没有驾照" in f for f in a.forbidden) and any("疲劳" in f for f in a.forbidden)
    assert _categories()["陪驾"].get("required_cert") == "驾驶证（三年以上驾龄）"
    assert {t.category for t in d.task_templates} == {"陪驾"}


def test_only_licensed_companions_can_take_driving_orders(client, requester):
    t = _post(client, requester, title="实习期想上一次高速", description="自己的车，自动挡", category="陪驾").json()
    w = make_verified(client, "13600003291")
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"
    assert "驾驶证（三年以上驾龄）" in r.json()["detail"]["message"]
    fix = _post(client, requester, title="手机换屏", description="屏幕碎了", category="数码维修与回收").json()
    assert client.post(f"{API}/tasks/{fix['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("device-repair-recycle", "device-helper", ("13900003291", "13900003292"), "旧手机回收前数据怎么清干净", "旧机回收前：退出账号、关闭查找、加密后恢复出厂"),
    ("device-repair-recycle", "device-helper", ("13900003293", "13900003294"), "修手机时能看客户相册吗", "修手机电脑：不看相册聊天，解锁请客户自己输"),
    ("driving-companion", "driving-companion-helper", ("13900003295", "13900003296"), "实习期上高速陪同的人要什么条件", "实习期上高速：陪同的人要有三年以上驾龄"),
    ("driving-companion", "driving-companion-helper", ("13900003297", "13900003298"), "没驾照的人想找我陪练学车可以吗", "没驾照的人学车：去驾校，不接"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
