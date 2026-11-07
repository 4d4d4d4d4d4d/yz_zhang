"""NTF-068 公告按类目定向（238 号 spec，V265）。

159 号能按城市、人群定向，「跑腿类接单规则调整」仍然发给了所有接单的人，包括只做设计的。
现在可以再叠一个类目：近 180 天在这个类目发过单 / 报过名的人。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.admin.models import AdminAudit
from app.modules.task.models import Application, Category, Task
from tests.conftest import auth, register
from tests.test_announcement_targeting import URL, _inbox, _ops, _people


def _categories(*names):
    with SessionLocal() as db:
        for n in names:
            if db.query(Category).filter(Category.name == n).first() is None:
                db.add(Category(name=n))
        db.commit()


def test_category_narrows_preview_and_send_and_stacks_with_audience(client):
    _categories("跑腿", "设计")
    ops = _ops(client)
    sh, bj, old = _people(client)            # 上海发单的在「跑腿」发单，北京接单的报了名；很久没来的 400 天前发过
    designer = register(client, "13800320014", "做设计的")
    with SessionLocal() as db:
        t = Task(creator_id=designer["id"], title="logo", description="", category="设计", budget_cents=10000,
                 status="published", visibility="public")
        db.add(t)
        db.flush()
        stale = Task(creator_id=old["id"], title="很久以前", description="", category="设计", budget_cents=1, status="published",
                     visibility="public")
        db.add(stale)
        db.flush()
        db.add(Application(task_id=stale.id, applicant_id=bj["id"], created_at=utcnow() - timedelta(days=400)))
        db.commit()
    run = client.post(f"{URL}/preview", json={"title": "跑腿规则调整", "body": "x", "category": "跑腿"}, headers=auth(ops)).json()
    assert run["audience"] == 2 and run["category"] == "跑腿", "跑腿类发过单或报过名的两个人"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(run, "AnnouncementPreview")
    wk = client.post(f"{URL}/preview", json={"title": "跑腿接单须知", "body": "x", "category": "跑腿", "audience": "workers"},
                     headers=auth(ops)).json()
    assert wk["audience"] == 1
    pub = client.post(f"{URL}/preview", json={"title": "设计发单须知", "body": "x", "category": "设计", "audience": "publishers"},
                      headers=auth(ops)).json()
    assert pub["audience"] == 2, "设计类近 180 天发过单的：做设计的 + 很久没来的（他的设计单是新发的）"
    dw = client.post(f"{URL}/preview", json={"title": "设计接单须知", "body": "x", "category": "设计", "audience": "workers"},
                     headers=auth(ops)).json()
    assert dw["audience"] == 0 and any("这个类目近 180 天没人" in w for w in dw["warnings"]), "400 天前报的名不算"
    r = client.post(URL, json={"title": "跑腿规则调整", "body": "下周起", "category": "跑腿", "audience": "workers"}, headers=auth(ops))
    assert r.status_code == 200 and r.json()["delivered"] == 1
    assert [n["title"] for n in _inbox(client, bj)] == ["跑腿规则调整"] and _inbox(client, sh) == [] and _inbox(client, designer) == []
    d = client.post(URL, json={"title": "设计发单须知", "body": "x", "category": "设计", "audience": "publishers"}, headers=auth(ops))
    assert d.json()["delivered"] == 2, "送达也按类目：上海在跑腿发单的人不该收到设计类的公告"
    assert _inbox(client, sh) == [] and [n["title"] for n in _inbox(client, designer)] == ["设计发单须知"]
    rows = client.get(URL, headers=auth(ops)).json()
    assert rows[0]["category"] == "设计" and rows[1]["category"] == "跑腿"
    _assert_shape(rows[0], "AnnouncementRow")
    with SessionLocal() as db:
        details = [a.detail for a in db.query(AdminAudit).filter(AdminAudit.action == "announcement_send")]
        assert any("类目「跑腿」" in x for x in details) and any("类目「设计」" in x for x in details)


def test_unknown_category_is_refused_and_empty_means_no_limit(client):
    _categories("跑腿")
    ops = _ops(client)
    _people(client)
    bad = client.post(f"{URL}/preview", json={"title": "x 公告", "body": "x", "category": "跑腿腿"}, headers=auth(ops))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "announcement_bad_category"
    assert client.post(URL, json={"title": "x 公告", "body": "x", "category": "跑腿腿"}, headers=auth(ops)).status_code == 400
    allp = client.post(f"{URL}/preview", json={"title": "全体公告", "body": "x"}, headers=auth(ops)).json()
    assert allp["category"] == "" and allp["audience"] >= 3


def test_ntf070_several_categories_are_a_union_and_only_echoed_when_more_than_one(client):
    """NTF-070（246 号 spec）「也发给」别的类目：几个类目取并集；只选一个时响应与 V265 一样。"""
    _categories("跑腿", "设计", "家政")
    ops = _ops(client)
    sh, bj, old = _people(client)
    designer = register(client, "13800320024", "做设计的")
    with SessionLocal() as db:
        db.add(Task(creator_id=designer["id"], title="logo", description="", category="设计", budget_cents=10000,
                    status="published", visibility="public"))
        db.commit()
    one = client.post(f"{URL}/preview", json={"title": "跑腿规则", "body": "x", "category": "跑腿", "categories": []}, headers=auth(ops)).json()
    assert "categories" not in one and one["audience"] == 2
    both = client.post(f"{URL}/preview", json={"title": "规则调整", "body": "x", "category": "跑腿", "categories": ["设计", "跑腿"]},
                       headers=auth(ops)).json()
    assert both["categories"] == ["跑腿", "设计"] and both["audience"] == 3, "跑腿两人 + 设计一人；重复的类目只算一次"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(both, "AnnouncementPreview")
    bad = client.post(f"{URL}/preview", json={"title": "规则调整", "body": "x", "categories": ["设计", "没这个"]}, headers=auth(ops))
    assert bad.json()["detail"]["code"] == "announcement_bad_category", "每个类目都要是平台上有的"
    assert client.post(f"{URL}/preview", json={"title": "x 公告", "body": "x", "categories": ["设计"] * 11}, headers=auth(ops)).status_code == 422
    r = client.post(URL, json={"title": "规则调整", "body": "下周起", "category": "设计", "categories": ["跑腿"], "audience": "publishers"},
                    headers=auth(ops))
    assert r.json()["delivered"] == 2, "设计类发单的 + 跑腿类发单的（上海那位）"
    assert [n["title"] for n in _inbox(client, designer)] == ["规则调整"] and [n["title"] for n in _inbox(client, sh)] == ["规则调整"]
    assert _inbox(client, bj) == []
    rows = client.get(URL, headers=auth(ops)).json()
    assert rows[0]["categories"] == ["设计", "跑腿"]
    _assert_shape(rows[0], "AnnouncementRow")
    with SessionLocal() as db:
        assert any("类目「设计、跑腿」" in a.detail for a in db.query(AdminAudit).filter(AdminAudit.action == "announcement_send"))


def test_ntf071_read_rate_split_by_category(client):
    """NTF-071（252 号 spec）多类目公告按类目拆开看阅读率；一个人同时属于两类时两边都算，另报重叠人数。"""
    from app.modules.notification.models import Notification

    _categories("跑腿", "设计")
    ops = _ops(client)
    sh, bj, old = _people(client)                     # 上海：跑腿发单；北京：跑腿报名
    designer = register(client, "13800320034", "做设计的")
    with SessionLocal() as db:
        db.add(Task(creator_id=designer["id"], title="logo", description="", category="设计", budget_cents=10000,
                    status="published", visibility="public"))
        db.add(Task(creator_id=sh["id"], title="海报", description="", category="设计", budget_cents=10000,
                    status="published", visibility="public"))       # 上海那位也在设计类发过单：两类都算
        db.commit()
    single = client.post(URL, json={"title": "单类目", "body": "x", "category": "跑腿"}, headers=auth(ops)).json()
    r = client.post(URL, json={"title": "多类目", "body": "x", "category": "跑腿", "categories": ["设计"]}, headers=auth(ops)).json()
    assert r["delivered"] == 3
    with SessionLocal() as db:
        for uid in (sh["id"], designer["id"]):
            db.query(Notification).filter(Notification.user_id == uid, Notification.announcement_id == r["id"]).one().is_read = True
        db.commit()
    v = client.get(f"{URL}/{r['id']}/read-by-category", headers=auth(ops)).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(v, "AnnouncementReadByCategory")
    rows = {x["category"]: x for x in v["categories"]}
    assert (rows["跑腿"]["delivered"], rows["跑腿"]["read"], rows["跑腿"]["read_rate"]) == (2, 1, 0.5)
    assert (rows["设计"]["delivered"], rows["设计"]["read"], rows["设计"]["read_rate"]) == (2, 2, 1.0)
    assert v["overlap"] == 1, "上海那位两类都算"
    s = client.get(f"{URL}/{single['id']}/read-by-category", headers=auth(ops)).json()
    assert [x["category"] for x in s["categories"]] == ["跑腿"]
    plain = client.post(URL, json={"title": "不限类目", "body": "x"}, headers=auth(ops)).json()
    p = client.get(f"{URL}/{plain['id']}/read-by-category", headers=auth(ops)).json()
    assert p["categories"] == [] and "没有按类目定向" in p["note"]
    assert client.get(f"{URL}/999999/read-by-category", headers=auth(ops)).status_code == 404
    other = register(client, "13800320035", "路人")
    assert client.get(f"{URL}/{r['id']}/read-by-category", headers=auth(other)).status_code == 403
