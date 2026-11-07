"""KB-094 报价助手与任务画像改用去重后的中位价（271 号 spec，V299）。

V293 只在「查参考价」那句话里提示。报价助手（V150）建议报多少、任务画像说预算偏高还是偏低，
仍拿原始中位比——一家公司按 ¥50 刷了五单，报价助手就劝人照 ¥50 报。样本集中时改用去重后的中位，不集中时一字不变。
"""
from app.core.db import SessionLocal
from app.modules.gig.service import quote
from app.modules.profiles.service import task_profile
from tests.test_price_reference_dedupe import _card


def _seed(category):
    with SessionLocal() as db:
        for _ in range(5):
            _card(db, 931, 5000, category=category)
        _card(db, 932, 20000, category=category)
        _card(db, 933, 22000, category=category)
        _card(db, None, 18000, category=category)
        _card(db, None, 18000, category=category)
        db.commit()


def test_quote_and_profile_use_the_deduped_median_when_one_publisher_dominates(client):
    _seed("代排队")
    with SessionLocal() as db:
        q = quote(db, "代排队", "杭州", 10000)
        p = task_profile(db, {"title": "帮排队", "category": "代排队", "city": "杭州", "budget_cents": 8000})
    assert (q["p50_cents"], q["reference_cents"], q["concentrated"]) == (5000, 18000, True), "原字段不变，另给对照用的中位"
    assert q["suggested_cents"] == 18000, "预算 ¥100 低于去重后的中位：建议按 ¥180 报，而不是被刷屏的 ¥50"
    assert any("按发布方去重后，5 位发布方的中位是 ¥180.00" in b for b in q["basis"])
    assert any("比中位低 45%" in b for b in q["basis"]), "对照也按去重后的中位"
    price = p["price"]
    assert (price["p50_cents"], price["reference_cents"], price["position"]) == (5000, 18000, "below_median")
    assert p["size"] == "small", "¥80 不到去重后中位的一半算小单（按被刷屏的 ¥50 会算中等）"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape({**q, "task_id": None}, "GigQuote")          # task_id 由接口那一层补上
    _assert_shape(price, "TaskProfilePrice")


def test_spread_out_samples_keep_the_old_numbers(client):
    with SessionLocal() as db:
        for pub, price in ((941, 10000), (942, 20000), (943, 30000)):
            _card(db, pub, price, category="代送花")
        db.commit()
        q = quote(db, "代送花", "杭州", 15000)
        p = task_profile(db, {"title": "送花", "category": "代送花", "city": "杭州", "budget_cents": 15000})
    assert "concentrated" not in q and "reference_cents" not in q
    assert q["suggested_cents"] == 20000 and any("比中位低 25%" in b for b in q["basis"])
    assert "concentrated" not in p["price"] and p["price"]["position"] == "below_median"
