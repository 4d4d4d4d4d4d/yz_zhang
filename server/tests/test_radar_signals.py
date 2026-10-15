"""SCN-108 场景雷达的两路新信号（153 号 spec）。

skill `scenario-discovery` 写着「雷达还没覆盖的（法律问答转律师的类别、客服没解决的工单类别）手动查聚合计数」——
手动查就是没人查。这里把它们接进雷达，并且守住同一条隐私线：只出粗主题与不同的人数，至少 3 个人。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.analytics.models import AnalyticsEvent
from app.modules.packs.topics import LEGAL_TOPICS, OTHER, SUPPORT_TOPICS, topic_of
from app.modules.support.models import Ticket
from tests.conftest import auth, make_admin, register

API = "/api/v1"


def _radar(client, admin, source):
    return {x["key"]: x for x in client.get(f"{API}/admin/packs/radar", headers=auth(admin)).json() if x["source"] == source}


def test_topic_of_picks_the_best_match_or_other():
    assert topic_of("房东不退押金怎么办", LEGAL_TOPICS) == "租房买房"
    assert topic_of("公司拖欠工资还不交社保", LEGAL_TOPICS) == "劳动用工"
    assert topic_of("外星法适用吗", LEGAL_TOPICS) == OTHER
    assert topic_of("提现三天没到账", SUPPORT_TOPICS) == "提现到账"


def test_unanswered_legal_questions_are_recorded_as_topic_only(client):
    u = register(client, "13800280001", "甲")
    r = client.post(f"{API}/legal/ask", json={"question": "房东不退押金还扣我房租怎么办"}, headers=auth(u))
    assert r.json()["refused_reason"] == "out_of_scope"
    client.post(f"{API}/legal/ask", json={"question": "平台上的电子合约有法律效力吗"}, headers=auth(u))   # 答得上的不记
    client.post(f"{API}/legal/ask", json={"question": "有人威胁我人身安全怎么办"}, headers=auth(u))      # 紧急的不记
    with SessionLocal() as db:
        rows = db.query(AnalyticsEvent).filter(AnalyticsEvent.name == "legal_unanswered").all()
        assert [(x.user_id, x.ref_type) for x in rows] == [(u["id"], "租房买房")]
        # 原文不落库：任何一列里都找不到问题里的字
        assert all("押金" not in (x.ref_type or "") for x in rows)


def test_legal_gap_needs_three_different_people(client):
    ops = make_admin(client, "13800280010", "运营")
    users = [register(client, f"1380028002{i}", f"人{i}") for i in range(4)]
    for u in users[:3]:
        client.post(f"{API}/legal/ask", json={"question": "离婚后孩子抚养费怎么算"}, headers=auth(u))
    for _ in range(3):   # 同一个人问三遍不算三个人
        client.post(f"{API}/legal/ask", json={"question": "我的作品被抄袭侵权了"}, headers=auth(users[3]))
    gaps = _radar(client, ops, "legal_gap")
    assert "婚姻家庭" in gaps and gaps["婚姻家庭"]["people"] == 3 and "知识产权" not in gaps
    assert "不存原文" in gaps["婚姻家庭"]["evidence"]
    with SessionLocal() as db:
        for row in db.query(AnalyticsEvent).filter(AnalyticsEvent.name == "legal_unanswered"):
            row.created_at = utcnow() - timedelta(days=31)
        db.commit()
    assert "婚姻家庭" not in _radar(client, ops, "legal_gap"), "超过 30 天的不算"


def test_support_gap_counts_overdue_or_escalated_tickets_by_topic(client):
    ops = make_admin(client, "13800280030", "运营")
    users = [register(client, f"1380028004{i}", f"人{i}") for i in range(5)]
    ids = []
    for u in users[:3]:
        ids.append(client.post(f"{API}/support/tickets", json={"subject": "提现一直没到账", "body": ""}, headers=auth(u)).json()["id"])
    fresh = client.post(f"{API}/support/tickets", json={"subject": "提现还没到", "body": ""}, headers=auth(users[3])).json()["id"]
    resolved = client.post(f"{API}/support/tickets", json={"subject": "提现到账慢", "body": ""}, headers=auth(users[4])).json()["id"]
    with SessionLocal() as db:
        now = utcnow()
        db.get(Ticket, ids[0]).created_at = now - timedelta(hours=30)              # 超时未结
        db.get(Ticket, ids[1]).created_at = now - timedelta(hours=30)
        db.get(Ticket, ids[2]).escalation_level = 1                                # 升级过
        db.get(Ticket, resolved).created_at = now - timedelta(hours=30)
        db.get(Ticket, resolved).status = "resolved"                              # 超时但已结、也没升级：不算
        db.commit()
    gaps = _radar(client, ops, "support_gap")
    assert gaps["提现到账"]["people"] == 3, "未超时的、按时结了的不算；超时与升级的都算"
    assert "提现一直没到账" not in str(gaps), "雷达上不出工单原文"
    with SessionLocal() as db:
        db.get(Ticket, ids[2]).escalation_level = 0
        db.commit()
    assert "提现到账" not in _radar(client, ops, "support_gap"), "不足 3 个不同的人就不出现"
    assert fresh
