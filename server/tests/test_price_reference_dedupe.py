"""KB-064 经验卡去重：参考价按发布方去重（266 号 spec，V293）。

同一位发布方反复发同类任务，参考价的中位数就成了「他一个人的价」：五单里四单是同一家公司按 ¥50 发的，
中位价就是 ¥50，而另外几位发布方的成交都在 ¥200 上下。原来的 sample_size / p50 不变，
另给按发布方去重后的数，并在一位发布方占了一半以上样本时写明。
"""
from app.core.db import SessionLocal
from app.modules.knowledge.models import KnowledgeCard
from app.modules.task.models import Task

API = "/api/v1/knowledge/price-reference"


def _card(db, creator: int | None, price: int, category="跑腿", city="杭州"):
    tid = None
    if creator is not None:
        t = Task(creator_id=creator, title="t", description="", category=category, budget_cents=price, status="completed", city=city)
        db.add(t)
        db.flush()
        tid = t.id
    db.add(KnowledgeCard(source_task_id=tid, category=category, city=city, title=f"{category}·{city}",
                         price_actual_cents=price, outcome="completed"))


def test_one_heavy_publisher_is_counted_once(client):
    with SessionLocal() as db:
        for _ in range(5):
            _card(db, 901, 5000)              # 同一家反复发的 ¥50
        _card(db, 902, 20000)
        _card(db, 903, 22000)
        _card(db, None, 18000)               # 找不到来源任务的：各算一位（不合成一个「无名氏」）
        _card(db, None, 18000)
        db.commit()
    r = client.get(API, params={"category": "跑腿", "city": "杭州"}).json()
    assert (r["sample_size"], r["p50_cents"], r["min_cents"], r["max_cents"]) == (9, 5000, 5000, 22000), "原来的字段不变"
    assert (r["publishers"], r["p50_by_publisher_cents"]) == (5, 18000), "五位发布方各一个样本：5000/18000/18000/20000/22000 的中位"
    assert r["top_publisher_share"] == round(5 / 9, 3) and r["concentrated"] is True
    assert "9 单里有 5 单来自同一位发布方" in r["note"] and "¥180.00" in r["note"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r, "PriceReference")


def test_spread_out_samples_say_nothing_and_a_publisher_median_is_its_own_median(client):
    with SessionLocal() as db:
        _card(db, 911, 10000, category="保洁")
        _card(db, 911, 70000, category="保洁")   # 同一位发了两单：先取他自己的中位 40000（不是第一单的 10000）
        _card(db, 912, 30000, category="保洁")
        _card(db, 913, 50000, category="保洁")
        db.commit()
    r = client.get(API, params={"category": "保洁", "city": "杭州"}).json()
    assert (r["sample_size"], r["publishers"], r["p50_by_publisher_cents"]) == (4, 3, 40000)
    assert r["top_publisher_share"] == 0.5 and r["concentrated"] is False and r["note"] == "", "正好一半不算集中"
    with SessionLocal() as db:
        for _ in range(2):
            _card(db, 921, 9000, category="搬家")
        db.commit()
    small = client.get(API, params={"category": "搬家", "city": "杭州"}).json()
    assert small["top_publisher_share"] == 1.0 and small["concentrated"] is False, "样本太少（不到 3 单）不下结论"
    none = client.get(API, params={"category": "没有这个类目"}).json()
    assert none["sample_size"] == 0 and "publishers" not in none, "没有样本时与以前一样"
