"""SCN-145 写单时就提醒：说明里提到孩子，告诉发单人该勾哪一项；学科类家教先说会被拒（215 号 spec，V243）。

两端发布页的「边写边提示」（任务画像草稿，126 号 spec）原来只说「涉及未成年人：平台要求额外核验」，发单人不知道下一步。
"""
from tests.conftest import auth

API = "/api/v1/profiles/task-draft"


def _risks(client, u, title, description=""):
    r = client.post(API, json={"title": title, "description": description, "category": "跑腿", "budget_cents": 20000,
                               "is_remote": False}, headers=auth(u))
    assert r.status_code == 200, r.text
    return {x["kind"]: x["text"] for x in r.json()["risks"]}


def test_mentioning_a_child_says_what_to_tick(client, requester):
    risks = _risks(client, requester, "孩子钢琴陪练", "每周六下午")
    assert "勾选「服务对象是未成年人」" in risks["minor"] and "无犯罪记录证明" in risks["minor"]
    assert "k12" not in risks


def test_subject_tutoring_is_flagged_before_publishing(client, requester):
    risks = _risks(client, requester, "给孩子找数学家教", "初二，每周两次")
    assert "不承接" in risks["k12"] and "办学资质" in risks["k12"]
    assert "minor" not in _risks(client, requester, "周末帮忙搬家")
