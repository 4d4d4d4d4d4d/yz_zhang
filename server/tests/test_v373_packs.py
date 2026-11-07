"""SCN-237 / SCN-238 第三十轮场景发掘：上门办宴席、网店客服外包（346 号 spec，V373）。

两个数据文件、两个新类目：「上门宴席」要审核通过的健康证明；「网店客服」不要资质。
宴席：按当地规定报备、健康证上岗、原料留票据、每样菜留样；客服：用子账号、买家信息不带走、话术真实、花钱的事交店主。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import HEALTH_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_banquet_pack_reports_big_feasts_and_keeps_samples():
    d, problems = schema.validate(_load("banquet-chef"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不报备" in f for f in a.forbidden) and any("不留样" in f for f in a.forbidden)
    assert any("野生菌" in f for f in a.forbidden) and any("身体不适" in f for f in a.forbidden)
    assert _categories()["上门宴席"]["required_cert"] == HEALTH_CERT
    t = d.task_templates[0]
    assert "按当地规定提前报备" in t.description and "每样菜留样贴日期" in t.visit_checklist


def test_store_cs_pack_uses_sub_accounts_and_never_takes_buyer_data():
    d, problems = schema.validate(_load("online-store-cs"))
    assert d is not None and not problems, problems
    assert d.segment == "studio"
    a = d.assistants[0]
    assert any("主账号密码" in f for f in a.forbidden) and any("买家信息" in f for f in a.forbidden)
    assert any("退款赔付" in f for f in a.forbidden) and "sign" in a.human_gates
    assert "required_cert" not in _categories()["网店客服"]
    t = d.task_templates[0].description
    assert "子账号" in t and "不加私人微信" in t and "交店主决定" in t


@pytest.mark.parametrize("key", ["banquet-chef", "online-store-cs"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_only_a_reviewed_health_certificate_can_cook_a_banquet(client, requester):
    ops = make_admin(client, "13600003721", "运营")
    t = _post(client, requester, title="寿宴二十桌", description="周日中午，村里祠堂", category="上门宴席").json()
    w = make_verified(client, "13600003722")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and HEALTH_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=HEALTH_CERT, expires_at=(utcnow() + timedelta(days=300)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "体检合格，在有效期内"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    cs = _post(client, requester, title="夜班客服", description="晚八点到十二点", category="网店客服", is_remote=True)
    assert cs.status_code in (200, 201), cs.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("banquet-chef", "banquet-chef-helper", ("13900003811", "13900003812"), "办三十桌要不要去村里登记", "人多的宴席按当地规定提前报备"),
    ("banquet-chef", "banquet-chef-helper", ("13900003813", "13900003814"), "帮厨今天发烧了能上吗", "厨师帮厨持健康证明，身体不适不上岗"),
    ("banquet-chef", "banquet-chef-helper", ("13900003815", "13900003816"), "主家想吃野生菌", "原料正规渠道买、留票据，高风险菜不做"),
    ("banquet-chef", "banquet-chef-helper", ("13900003817", "13900003818"), "有客人吃完拉肚子了", "每样菜留样冷藏 48 小时"),
    ("online-store-cs", "store-cs-helper", ("13900003819", "13900003820"), "店主要把主账号密码给我", "用店主开的子账号，不要主账号密码"),
    ("online-store-cs", "store-cs-helper", ("13900003821", "13900003822"), "能不能把买家加到我微信上", "买家信息留在店铺里，不导出、不加私人微信"),
    ("online-store-cs", "store-cs-helper", ("13900003823", "13900003824"), "能说全网最低吗", "话术真实：不说全网最低、不编发货时间、不搞好评返现"),
    ("online-store-cs", "store-cs-helper", ("13900003825", "13900003826"), "买家要退款我能直接退吗", "退款、赔付、改价交店主拍板"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("banquet-chef", "banquet-chef-helper", ("13900003827", "13900003828"), "大师傅今天不舒服", "厨师帮厨持健康证明，身体不适不上岗"),
    ("banquet-chef", "banquet-chef-helper", ("13900003829", "13900003830"), "便宜肉行不行", "原料正规渠道买、留票据，高风险菜不做"),
    ("online-store-cs", "store-cs-helper", ("13900003831", "13900003832"), "跟店主共用账号行吗", "用店主开的子账号，不要主账号密码"),
    ("online-store-cs", "store-cs-helper", ("13900003833", "13900003834"), "能跟买家保证正品吗", "话术真实：不说全网最低、不编发货时间、不搞好评返现"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
