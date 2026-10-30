"""SCN-221 发单拦截按类别统计复核结果进场景雷达（340 号 spec，V367）。

复核结果散在一条条记录里，词表该不该改没有依据。雷达按拦截类别看近 30 天处理过的复核：通过的来自至少
3 个不同的人、且占一半以上，就报「可能拦得太宽」。只出类别、条数与人数，不出原文与说明。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.task.errand import errand_fingerprint
from app.modules.task.models import ErrandReview
from tests.conftest import auth, make_admin

API = "/api/v1"


def _review(user_id: int, kind: str, status: str, days_ago: int = 1, title: str = "论文集宣传"):
    with SessionLocal() as db:
        db.add(ErrandReview(user_id=user_id, kind=kind, title=title, description="私密的说明原文", explanation="我的理由原文",
                            fingerprint=errand_fingerprint(f"{title}{user_id}"), status=status, decision_note="",
                            decided_at=utcnow() - timedelta(days=days_ago)))
        db.commit()


def _radar(client, admin):
    return {x["key"]: x for x in client.get(f"{API}/admin/packs/radar", headers=auth(admin)).json() if x["source"] == "errand_gap"}


def test_a_guard_category_approved_often_by_three_people_shows_up_without_any_text(client):
    from tests.test_client_shape_alignment import _assert_shape

    ops = make_admin(client, "13600003671", "运营")
    for uid in (901, 902, 903):
        _review(uid, "ghostwrite", "approved")
    _review(904, "ghostwrite", "rejected")
    _review(905, "ghostwrite", "approved", days_ago=40)          # 30 天以前的不算
    _review(906, "ghostwrite", "pending")                        # 在等的不算
    for uid in (911, 912, 913):
        _review(uid, "fake_review", "approved")
    for uid in (914, 915, 916, 917):
        _review(uid, "fake_review", "rejected")                  # 通过的不到一半：拦得对
    for uid in (921, 922):
        _review(uid, "rx", "approved")                           # 不到 3 个人：不出现
    _review(921, "rx", "approved")
    gaps = _radar(client, ops)
    assert set(gaps) == {"代写学位论文代考"}, gaps
    g = gaps["代写学位论文代考"]
    _assert_shape(g, "RadarSignal")
    assert g["people"] == 3 and "处理了 4 条，通过 3 条（75%" in g["evidence"] and "维持 1 条" in g["evidence"]
    assert "原文" not in g["title"] and "私密" not in g["evidence"] and "我的理由" not in g["evidence"], "只出类别与人数"
