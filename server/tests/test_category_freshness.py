"""KB-062b 经验时效窗口按类目可配（327 号 spec，V354）：运营在后台按类目调，默认 12 个月。

V350 定了统一的 365 天；可有的行业一季度一变（装修材料价、平台规则），有的几年不变（翻译、家教）。现在：
- 运营在「城市与类目」按类目设 30~3650 天，填 0 回到默认；改动进审计；
- 喂给 agent 的核验经验、经验单元「新 / 旧」的判断都按这个类目自己的窗口；
- 没设的类目照旧 365 天。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.task.models import Category
from tests.conftest import auth, make_admin

API = "/api/v1"


def _new_category(client, ops, name: str) -> int:
    r = client.post(f"{API}/admin/categories", json={"name": name}, headers=auth(ops))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_ops_set_a_window_per_category_and_can_reset_it(client):
    ops = make_admin(client, "13800335401")
    cid = _new_category(client, ops, "时效窗口装修")
    r = client.patch(f"{API}/admin/categories/{cid}?experience_fresh_days=90", headers=auth(ops))
    assert r.status_code == 200 and r.json()["experience_fresh_days"] == 90, r.text
    listed = {c["name"]: c for c in client.get(f"{API}/categories").json()}
    assert listed["时效窗口装修"]["experience_fresh_days"] == 90
    for bad in (29, 3651, -1):
        r = client.patch(f"{API}/admin/categories/{cid}?experience_fresh_days={bad}", headers=auth(ops))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "fresh_days_out_of_range", bad
    back = client.patch(f"{API}/admin/categories/{cid}?experience_fresh_days=0", headers=auth(ops)).json()
    assert "experience_fresh_days" not in back, "填 0 回到默认"
    with SessionLocal() as db:
        assert db.get(Category, cid).experience_fresh_days is None, "库里存的是空（默认），不是 0"
    assert "experience_fresh_days" not in {c["name"]: c for c in client.get(f"{API}/categories").json()}["时效窗口装修"]
    other = client.patch(f"{API}/admin/categories/{cid}?active=true", headers=auth(ops)).json()
    assert "experience_fresh_days" not in other, "没传就不动"
    from app.modules.admin.models import AdminAudit

    with SessionLocal() as db:
        details = [a.detail for a in db.query(AdminAudit).filter(AdminAudit.action == "category_fresh_days",
                                                                AdminAudit.target_id == cid)]
    assert details == ["时效窗口装修：默认 → 90", "时效窗口装修：90 → 默认"], "两次改动都进审计，写明前后"


def test_lessons_and_units_follow_the_category_window(client):
    from app.modules.knowledge.models import KnowledgeCluster, ReusableUnit
    from app.modules.knowledge.units import fresh_days_for, is_stale
    from app.modules.verify.models import VerificationLesson
    from app.modules.verify.service import lessons_for

    ops = make_admin(client, "13800335402")
    cid = _new_category(client, ops, "时效窗口快变")
    client.patch(f"{API}/admin/categories/{cid}?experience_fresh_days=60", headers=auth(ops))
    with SessionLocal() as db:
        assert fresh_days_for(db, "时效窗口快变") == 60 and fresh_days_for(db, "没设窗口的类目") == 365
        db.add_all([
            VerificationLesson(category="时效窗口快变", outcome="revised", criteria=[], reason="三个月前：瓷砖缝没勾",
                               created_at=utcnow() - timedelta(days=90)),
            VerificationLesson(category="时效窗口快变", outcome="revised", criteria=[], reason="上周：踢脚线没装平",
                               created_at=utcnow() - timedelta(days=7)),
        ])
        c = KnowledgeCluster(category="时效窗口快变", label="x", last_sample_at=utcnow() - timedelta(days=90))
        db.add(c)
        db.flush()
        u = ReusableUnit(cluster_id=c.id, kind="procedure", title="三个月前的做法", content={}, applicability={},
                         validation={}, reuse_license=True, created_by=0)
        db.add(u)
        db.commit()
        assert [r.reason for r in lessons_for(db, "时效窗口快变")] == ["上周：踢脚线没装平"], "按类目的 60 天"
        assert is_stale(db, u), "单元没写适用类目时看子类的类目"
        row = db.get(Category, cid)
        row.experience_fresh_days = None
        db.commit()
        assert len(lessons_for(db, "时效窗口快变")) == 2, "回到默认 365 天"
        assert not is_stale(db, u)
