"""KB-097 子类参考价也按发布方去重（275 号 spec，V303）。

V293 只改了按类目取价那条路；按子类取（cluster_id）同样会被一家刷屏带偏。口径与 266 号一样：原字段不变，另给去重后的数。
"""
from app.core.db import SessionLocal
from app.modules.task.models import Task
from tests.test_knowledge_clusters import _card, _run, _threshold, semantic  # noqa: F401 —— semantic 是 fixture


def _task(creator, price):
    with SessionLocal() as db:
        t = Task(creator_id=creator, title="t", description="", category="跑腿", budget_cents=price, status="completed", city="杭州")
        db.add(t)
        db.commit()
        return t.id


def test_cluster_price_is_also_deduped_by_publisher(client, semantic):  # noqa: F811
    _threshold()
    for _ in range(4):
        _card(price=5000, task_id=_task(951, 5000))
    _card(price=20000, task_id=_task(952, 20000))
    _card(price=22000, task_id=_task(953, 22000))
    _card(price=90000, outcome="disputed", task_id=_task(954, 90000))   # 经过纠纷的不算行情（与 p50 同一口径）
    _run(client)
    cid = client.get("/api/v1/knowledge/clusters", params={"category": "跑腿"}).json()["items"][0]["id"]
    pr = client.get("/api/v1/knowledge/price-reference", params={"category": "跑腿", "cluster_id": cid}).json()
    assert (pr["sample_size"], pr["p50_cents"]) == (6, 5000), "原字段不变"
    assert (pr["publishers"], pr["p50_by_publisher_cents"], pr["concentrated"]) == (3, 20000, True)
    assert "6 单里有 4 单来自同一位发布方" in pr["note"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(pr, "PriceReference")
