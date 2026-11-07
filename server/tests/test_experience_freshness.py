"""KB-062 经验的时效（323 号 spec，V350）：近 12 个月的经验优先，一年以前的降权并写明年月。

以前一年前的核验结论、一年前验证过的做法，和上周的在提示词、拆解、助手引用里分不出先后。现在：
- 喂给 agent 的核验经验只取近 12 个月的，每条标上年月；
- 拆解第一层套的经验单元，近 12 个月还有样本的排在前面（哪怕一年以前的那条「已验证」）；
- 场景包助手引用经验时，一年以前的排在后面，出处写明「一年以前的经验，价格与做法可能已过时」。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow


def _unit(db, title: str, category: str, *, seen_days_ago: int, validated: bool, steps=None):
    from app.modules.knowledge.models import KnowledgeCluster, ReusableUnit

    c = KnowledgeCluster(category=category, label=title, last_sample_at=utcnow() - timedelta(days=seen_days_ago))
    db.add(c)
    db.flush()
    u = ReusableUnit(cluster_id=c.id, kind="procedure", title=title, content={"summary": title, "steps": steps or []},
                     applicability={"category": category}, validation={"status": "validated" if validated else "unvalidated"},
                     reuse_license=True, created_by=0, created_at=utcnow() - timedelta(days=seen_days_ago))
    db.add(u)
    db.flush()
    return u


def test_agents_only_get_lessons_from_the_last_twelve_months_with_their_month(client):
    from app.modules.verify.models import VerificationLesson
    from app.modules.verify.service import lessons_for, lessons_prompt

    with SessionLocal() as db:
        old = VerificationLesson(category="时效保洁", outcome="revised", criteria=[], reason="一年多前：没拍完工照片",
                                 created_at=utcnow() - timedelta(days=400))
        new = VerificationLesson(category="时效保洁", outcome="rejected", criteria=[], reason="上周：漏擦了窗户",
                                 created_at=utcnow() - timedelta(days=7))
        db.add_all([old, new])
        db.commit()
        rows = lessons_for(db, "时效保洁")
        assert [r.reason for r in rows] == ["上周：漏擦了窗户"], "一年以前的不再喂"
        prompt = lessons_prompt(rows)
    assert f"（{(utcnow() - timedelta(days=7)):%Y-%m}）：上周：漏擦了窗户" in prompt, prompt


def test_decomposition_prefers_a_fresh_procedure_over_a_year_old_validated_one(client):
    from app.modules.knowledge.units import best_procedure, is_stale

    with SessionLocal() as db:
        old = _unit(db, "老做法", "时效装修", seen_days_ago=400, validated=True)
        new = _unit(db, "新做法", "时效装修", seen_days_ago=30, validated=False)
        assert is_stale(db, old) and not is_stale(db, new)
        # 单元是一年多前提炼的，但子类上个月还有新样本：算新（看的是最近一次样本，不是提炼日期）
        alive = _unit(db, "老单元新样本", "时效装修二", seen_days_ago=10, validated=True)
        alive.created_at = utcnow() - timedelta(days=500)
        db.flush()
        assert not is_stale(db, alive)
        assert best_procedure(db, "时效装修", "上海", 10000).id == new.id, "近 12 个月的排前面"
        new.status = "retired"
        db.flush()
        assert best_procedure(db, "时效装修", "上海", 10000).id == old.id, "只剩一年以前的也照用（不是删掉）"
        db.rollback()


def test_pack_citations_put_old_experience_last_and_say_it_may_be_outdated(client):
    from app.modules.packs.service import _experience_citations

    with SessionLocal() as db:
        _unit(db, "防水闭水验收做法甲", "时效防水", seen_days_ago=500, validated=True, steps=["闭水验收", "闭水 48 小时"])
        _unit(db, "防水闭水验收做法乙", "时效防水", seen_days_ago=20, validated=True, steps=["闭水验收"])
        cites = _experience_citations(db, "防水闭水验收做法", k=2)
        db.rollback()
    titles = [c["title"] for c in cites]
    assert titles == ["防水闭水验收做法乙", "防水闭水验收做法甲"], titles
    old_month = f"{(utcnow() - timedelta(days=500)):%Y-%m}"
    assert f"最近一次是 {old_month}，一年以前的经验，价格与做法可能已过时" in cites[1]["source"]
    assert "过时" not in cites[0]["source"]
