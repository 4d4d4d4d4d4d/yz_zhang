"""SCN-199 / SCN-200 第十九轮场景发掘：水电小修、短视频剪辑（325 号 spec，V352）。

交付物是两个数据文件、两个新类目。「水电维修」要审核通过的低压电工作业操作证（电工作业属特种作业，持证上岗），
有效期按特种作业操作证同一条规则（必填、最长 6 年）；短视频剪辑的关口是素材、音乐、字体都要有授权。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_electrical_pack_needs_the_certificate_and_powers_off_first():
    d, problems = schema.validate(_load("home-electrical-plumbing"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("带电作业" in f for f in a.forbidden) and any("没有电工操作证" in f for f in a.forbidden)
    assert any("燃气" in f for f in a.forbidden) and any("私拉乱接" in f for f in a.forbidden)
    assert _categories()["水电维修"].get("required_cert") == "低压电工作业操作证"
    t = d.task_templates[0]
    assert "断电验电" in t.visit_checklist and "低压电工作业操作证" in t.description


def test_editing_pack_only_uses_licensed_music_footage_and_fonts():
    d, problems = schema.validate(_load("video-editing"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "sign"} <= set(a.human_gates), "创作者人群：钱与签署是人工关口"
    assert any("没有授权的音乐" in f for f in a.forbidden) and any("几秒以内不算侵权" in f for f in a.forbidden)
    assert any("水印" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["短视频剪辑"]
    assert "授权清单" in d.task_templates[0].description


def test_only_certified_electricians_take_repair_orders(client, requester):
    t = _post(client, requester, title="插座冒火花", description="客厅一个插座", category="水电维修").json()
    w = make_verified(client, "13600003521")
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"
    assert "低压电工作业操作证" in r.json()["detail"]["message"]
    edit = _post(client, requester, title="剪三条口播", description="竖屏", category="短视频剪辑", is_remote=True).json()
    assert client.post(f"{API}/tasks/{edit['id']}/applications", json={}, headers=auth(w)).status_code == 201


def test_electrician_certificate_must_carry_an_expiry_within_six_years(client):
    w = make_verified(client, "13600003522")
    r = apply_cert(client, w, name="低压电工作业操作证", expires_at=None)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_required"
    assert "低压电工作业操作证" in r.json()["detail"]["message"]
    r = apply_cert(client, w, name="低压电工作业操作证", expires_at=(utcnow() + timedelta(days=366 * 6 + 2)).isoformat())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_too_far"
    ok = apply_cert(client, w, name="低压电工作业操作证", expires_at=(utcnow() + timedelta(days=365 * 5)).isoformat())
    assert ok.status_code == 201, ok.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("home-electrical-plumbing", "electrical-helper", ("13900003521", "13900003522"), "换插座要先断电吗", "先断电、再验电、再动手"),
    ("home-electrical-plumbing", "electrical-helper", ("13900003523", "13900003524"), "总跳闸换个大点的空开行不行", "不私拉乱接，不靠加大空开了事"),
    ("home-electrical-plumbing", "electrical-helper", ("13900003525", "13900003526"), "客户让我顺手改一下燃气管", "燃气管道、燃气表不碰"),
    ("video-editing", "editing-helper", ("13900003527", "13900003528"), "客户给的参考视频里的BGM能直接用吗", "背景音乐要有授权：平台曲库只限在那个平台用"),
    ("video-editing", "editing-helper", ("13900003529", "13900003530"), "只用几秒的歌算不算侵权", "「几秒以内不算侵权」「不商用不算侵权」都没有依据"),
    ("video-editing", "editing-helper", ("13900003531", "13900003532"), "客户一直要改稿怎么办", "改稿轮数写进单子，超出走变更单"),
    # 人们真正会说的话：正文里没有这些词，靠标签接住
    ("home-electrical-plumbing", "electrical-helper", ("13900003533", "13900003534"), "电闸老掉闸", "不私拉乱接，不靠加大空开了事"),
    ("home-electrical-plumbing", "electrical-helper", ("13900003535", "13900003536"), "挪一下天然气", "燃气管道、燃气表不碰"),
    ("video-editing", "editing-helper", ("13900003537", "13900003538"), "流行歌曲做片头行吗", "背景音乐要有授权：平台曲库只限在那个平台用"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
