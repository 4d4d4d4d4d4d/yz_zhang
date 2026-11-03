"""SCN-257 / SCN-258 第三十九轮场景发掘：智能门锁安装、家用充电桩安装（365 号 spec，V391）。

「智能门锁安装」不要资质：指纹密码由主人自己录、机械钥匙不留不配、默认密码清掉；
「充电桩安装」动电，要审核通过的低压电工作业操作证（复用 ELECTRICIAN_CERT，已在高风险全抽名单里）。
"""
from datetime import timedelta

import pytest

from app.modules.account import cert_spot
from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import ELECTRICIAN_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_lock_pack_keeps_credentials_and_keys_with_the_owner():
    d, problems = schema.validate(_load("smart-lock-install"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("自己的指纹" in f for f in a.forbidden) and any("机械钥匙" in f for f in a.forbidden)
    assert any("默认密码" in f for f in a.forbidden) and "share_personal" in a.human_gates
    assert "required_cert" not in _categories()["智能门锁安装"]
    t = d.task_templates[0].description
    assert "我自己录" in t and "默认密码清掉" in t and "全部交给我" in t


def test_charger_pack_needs_an_electrician_and_never_runs_flying_leads():
    d, problems = schema.validate(_load("ev-charger-install"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("私拉飞线" in f for f in a.forbidden) and any("漏电保护" in f for f in a.forbidden)
    assert any("没有电工证" in f for f in a.forbidden) and any("报装" in f for f in a.forbidden)
    assert _categories()["充电桩安装"]["required_cert"] == ELECTRICIAN_CERT
    assert ELECTRICIAN_CERT in cert_spot.high_risk_certs()
    t = d.task_templates[0].description
    assert "专用回路" in t and "不私拉飞线" in t


@pytest.mark.parametrize("key", ["smart-lock-install", "ev-charger-install"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_only_a_reviewed_electrician_can_install_a_charger(client, requester):
    ops = make_admin(client, "13600039101", "运营")
    t = _post(client, requester, title="地库装 7 千瓦充电桩", description="产权车位，报装已办", category="充电桩安装").json()
    w = make_verified(client, "13600039102")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and ELECTRICIAN_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=ELECTRICIAN_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件可查"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    lock = _post(client, requester, title="防盗门换智能锁", description="门厚 7 厘米", category="智能门锁安装")
    assert lock.status_code in (200, 201), lock.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("smart-lock-install", "smart-lock-helper", ("13900004401", "13900004402"), "防盗门要扩孔吗", "先量门、看锁体，能不能直接换说清楚"),
    ("smart-lock-install", "smart-lock-helper", ("13900004403", "13900004404"), "指纹由谁来录", "管理员密码、指纹、门卡由主人自己录"),
    ("smart-lock-install", "smart-lock-helper", ("13900004405", "13900004406"), "应急钥匙给几把", "机械钥匙全部当面交给主人，不留不配不拍"),
    ("smart-lock-install", "smart-lock-helper", ("13900004407", "13900004408"), "出厂默认密码要改吗", "出厂默认密码一律清掉"),
    ("smart-lock-install", "smart-lock-helper", ("13900004409", "13900004410"), "装完要试一下哪些", "装完逐项试，讲清电池怎么换"),
    ("ev-charger-install", "ev-charger-helper", ("13900004411", "13900004412"), "物业不同意能先装吗", "物业同意、供电报装先办好"),
    ("ev-charger-install", "ev-charger-helper", ("13900004413", "13900004414"), "要用多粗的线", "从电表拉专用回路，配漏电保护和合适的线径"),
    ("ev-charger-install", "ev-charger-helper", ("13900004415", "13900004416"), "客户想从楼道插座拉线", "不从插座、楼道私拉飞线"),
    ("ev-charger-install", "ev-charger-helper", ("13900004417", "13900004418"), "装完要不要测接地", "装完测接地、试充一次，讲清用电安全"),
    ("ev-charger-install", "ev-charger-helper", ("13900004419", "13900004420"), "没电工证能接吗", "持低压电工证上岗"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("smart-lock-install", "smart-lock-helper", ("13900004421", "13900004422"), "锁装不上", "先量门、看锁体，能不能直接换说清楚"),
    ("smart-lock-install", "smart-lock-helper", ("13900004423", "13900004424"), "钥匙少给了", "机械钥匙全部当面交给主人，不留不配不拍"),
    ("smart-lock-install", "smart-lock-helper", ("13900004425", "13900004426"), "门锁不上了", "装完逐项试，讲清电池怎么换"),
    ("ev-charger-install", "ev-charger-helper", ("13900004427", "13900004428"), "线发烫了", "从电表拉专用回路，配漏电保护和合适的线径"),
    ("ev-charger-install", "ev-charger-helper", ("13900004429", "13900004430"), "用拖线板行不行", "不从插座、楼道私拉飞线"),
    ("ev-charger-install", "ev-charger-helper", ("13900004431", "13900004432"), "桩有焦味", "装完测接地、试充一次，讲清用电安全"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
