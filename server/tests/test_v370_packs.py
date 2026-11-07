"""SCN-232 / SCN-233 第二十八轮场景发掘：配音、私房烘焙与定制蛋糕（343 号 spec，V370）。

两个数据文件、两个新类目：「配音」不要资质；「私房烘焙」要食品经营许可（或小作坊登记）与健康证明两样都审核通过。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import BAKERY_CERT, HEALTH_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_voice_over_pack_never_clones_a_voice_and_keeps_ai_training_separate():
    d, problems = schema.validate(_load("voice-over"))
    assert d is not None and not problems, problems
    assert d.segment == "creator"
    a = d.assistants[0]
    assert {"money", "sign"} <= set(a.human_gates)
    assert any("克隆" in f for f in a.forbidden) and any("训练 AI" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["配音"]
    t = d.task_templates[0].description
    assert "不模仿某个具体的人" in t and "不得用录音训练 AI" in t


def test_home_bakery_pack_needs_licence_and_health_and_lists_allergens():
    d, problems = schema.validate(_load("home-bakery"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("食品经营许可" in f for f in a.forbidden) and any("过敏原" in f for f in a.forbidden)
    cat = _categories()["私房烘焙"]
    assert cat["required_cert"] == BAKERY_CERT and cat["extra_certs"] == [HEALTH_CERT]
    t = d.task_templates[0]
    assert "过敏" in t.description and "核对过敏原避开" in t.visit_checklist


@pytest.mark.parametrize("key", ["voice-over", "home-bakery"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def _approve(client, ops, w, name):
    app_id = apply_cert(client, w, name=name, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    r = client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件清晰，信息一致"},
                    headers=auth(ops))
    assert r.status_code == 200, r.text


def test_a_bakery_job_needs_both_the_licence_and_the_health_certificate(client, requester):
    ops = make_admin(client, "13600003701", "运营")
    t = _post(client, requester, title="六寸生日蛋糕", description="周六下午送到，孩子坚果过敏", category="私房烘焙").json()
    w = make_verified(client, "13600003702")
    apply = lambda: client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))   # noqa: E731
    no = apply()
    assert no.status_code == 400 and BAKERY_CERT in no.json()["detail"]["message"], no.text
    _approve(client, ops, w, BAKERY_CERT)
    half = apply()
    assert half.status_code == 400 and HEALTH_CERT in half.json()["detail"]["message"], "只有许可没有健康证明也不行"
    _approve(client, ops, w, HEALTH_CERT)
    assert apply().status_code == 201
    vo = _post(client, requester, title="短视频配音", description="三百字，自用", category="配音", is_remote=True)
    assert vo.status_code in (200, 201), vo.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("voice-over", "voice-over-helper", ("13900003761", "13900003762"), "客户要我照着某某明星的声音来", "不用 AI 克隆或模仿某个具体的人的声音"),
    ("voice-over", "voice-over-helper", ("13900003763", "13900003764"), "客户想拿我的录音去训练", "拿录音训练 AI 要单独写明、单独谈价"),
    ("voice-over", "voice-over-helper", ("13900003765", "13900003766"), "自用价的音被拿去投广告了", "先问用在哪，授权范围写进单子"),
    ("voice-over", "voice-over-helper", ("13900003767", "13900003768"), "文案改了好几遍都要重录吗", "念错免费重录，改了文案另算"),
    ("home-bakery", "home-bakery-helper", ("13900003769", "13900003770"), "没有许可证能在朋友圈卖蛋糕吗", "有证经营：食品经营许可或小作坊登记，加健康证明"),
    ("home-bakery", "home-bakery-helper", ("13900003771", "13900003772"), "孩子对坚果过敏", "每单写清配料与过敏原"),
    ("home-bakery", "home-bakery-helper", ("13900003773", "13900003774"), "夏天送蛋糕奶油化了", "奶油蛋糕冷藏配送，交代当天吃完"),
    ("home-bakery", "home-bakery-helper", ("13900003775", "13900003776"), "客户做到一半不要了", "取消与改款按制作进度写清"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("voice-over", "voice-over-helper", ("13900003777", "13900003778"), "能不能配得像谁谁", "不用 AI 克隆或模仿某个具体的人的声音"),
    ("voice-over", "voice-over-helper", ("13900003779", "13900003780"), "客户要把我的音频喂给大模型", "拿录音训练 AI 要单独写明、单独谈价"),
    ("home-bakery", "home-bakery-helper", ("13900003781", "13900003782"), "被人举报了怎么办", "有证经营：食品经营许可或小作坊登记，加健康证明"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
