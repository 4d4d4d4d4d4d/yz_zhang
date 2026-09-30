"""NTF-002 推送通道 与 KB-011/022 向量检索（42 号 spec）。

这两条都是**注释里写了要做、却一直没做**的降级实现：

    notification/service.py:1  「生产追加 APNs/FCM/短信通道」
    knowledge/service.py:102   「生产为向量检索 + LLM 生成，此处关键词匹配」

第一条的代价是具体的：被诉方的答辩期 48 小时，逾期即缺席裁决。
用户不主动打开 App，一条只存在于站内的答辩提醒和没有提醒差别不大——
V63 补了「会提醒」，这一批补的是「提醒真的到得了人」。
"""
import pytest

from app.core.db import SessionLocal
from app.core.config import settings
from app.modules.notification.models_device import DeviceToken
from app.vendors import registry

from .conftest import JOB_HEADERS, auth, register


@pytest.fixture()
def sandbox_push(monkeypatch):
    monkeypatch.setattr(settings, "PUSH_PROVIDER", "sandbox")
    registry.reset()
    yield
    registry.reset()


def drain(client):
    r = client.post("/api/v1/events/jobs/drain", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- NTF-002 设备令牌 ----------
def test_ntf002_device_registration_is_idempotent(client):
    """App 每次启动都会注册；攒出重复行的后果是同一条通知推四遍。"""
    u = register(client, "13966600001", "有设备的人")
    for _ in range(3):
        r = client.put("/api/v1/notifications/devices",
                       json={"token": "tok-aaaaaaaa", "platform": "ios"}, headers=auth(u))
        assert r.status_code == 200, r.text

    db = SessionLocal()
    assert db.query(DeviceToken).filter(DeviceToken.user_id == u["id"]).count() == 1
    db.close()


def test_ntf002_same_device_new_account_moves_the_token(client):
    """换账号登录同一台设备：令牌必须改归属。

    不改的话，新用户的通知会推给上一个用户——在共用手机的场景里这是
    实打实的隐私泄露。
    """
    a = register(client, "13966600002", "前一个人")
    b = register(client, "13966600003", "后一个人")
    client.put("/api/v1/notifications/devices",
               json={"token": "tok-shared0", "platform": "android"}, headers=auth(a))
    client.put("/api/v1/notifications/devices",
               json={"token": "tok-shared0", "platform": "android"}, headers=auth(b))

    db = SessionLocal()
    row = db.get(DeviceToken, "tok-shared0")
    db.close()
    assert row.user_id == b["id"], "令牌还挂在上一个账号上，通知会推错人"


def test_ntf002_notification_actually_reaches_the_device(client, sandbox_push):
    """站内信是「记录」，推送是「触达」——这条验的是后者真的发生了。"""
    u = register(client, "13966600004", "收推送的人")
    client.put("/api/v1/notifications/devices",
               json={"token": "tok-live0001", "platform": "ios"}, headers=auth(u))

    from app.modules.notification.service import notify

    db = SessionLocal()
    notify(db, u["id"], "system", "测试通知", "正文")
    db.commit()
    db.close()

    drain(client)     # 推送走发件箱，由 drain 补做
    from app.vendors.models import VendorCall

    db = SessionLocal()
    calls = db.query(VendorCall).filter(VendorCall.kind == "push").all()
    db.close()
    assert calls, "通知发出去了，但从来没有调用过推送通道"


def test_ntf002_invalid_tokens_get_revoked(client, sandbox_push):
    """设备卸载后令牌永久失效；不清理就会年复一年推给不存在的设备，而通道按量计费。"""
    u = register(client, "13966600005", "卸载了的人")
    client.put("/api/v1/notifications/devices",
               json={"token": "expired-token01", "platform": "ios"}, headers=auth(u))

    from app.modules.notification.service import notify

    db = SessionLocal()
    notify(db, u["id"], "system", "测试", "正文")
    db.commit()
    db.close()
    drain(client)

    db = SessionLocal()
    row = db.get(DeviceToken, "expired-token01")
    db.close()
    assert row.revoked is True


def test_ntf002_push_failure_never_breaks_the_business_transaction(client, monkeypatch):
    """推送必须走发件箱：同步打第三方会把一次网络抖动变成一笔交易失败。"""
    from app.vendors.base import VendorError

    class Exploding:
        name, delivers = "boom", True

        def send(self, *a, **k):
            raise VendorError("push_upstream", "网关挂了", retryable=True)

    monkeypatch.setitem(registry._REGISTRY, "push", {"boom": Exploding})
    monkeypatch.setattr(settings, "PUSH_PROVIDER", "boom")
    registry.reset()
    try:
        u = register(client, "13966600006", "倒霉的人")
        client.put("/api/v1/notifications/devices",
                   json={"token": "tok-doomed01", "platform": "ios"}, headers=auth(u))
        # 充值会发通知；推送炸了也不能让充值失败
        r = client.post("/api/v1/wallet/topup", json={"amount_cents": 10000}, headers=auth(u))
        assert r.status_code == 200, r.text
        assert client.get("/api/v1/wallet", headers=auth(u)).json()["available_cents"] == 10000
    finally:
        registry.reset()


def test_ntf002_no_provider_is_honest_about_it(client):
    """缺省不发推送时**不假装成功**——面板与验收脚本要看得见它没接。"""
    from app.modules.notification.service import push_to_devices

    db = SessionLocal()
    out = push_to_devices(db, {"user_id": 1, "title": "x", "body": "y"})
    db.close()
    assert out["delivered"] == 0 and out["reason"] == "no_push_provider"


# ---------- KB-011/022 向量检索 ----------
def test_kb011_reindex_then_search_uses_vectors(client):
    from app.modules.knowledge.models import FaqEntry

    db = SessionLocal()
    db.add(FaqEntry(question="提现多久到账", answer="1 个工作日内到账",
                    keywords=["提现", "到账"]))
    db.add(FaqEntry(question="怎么发布任务", answer="在发布页填写标题与预算",
                    keywords=["发布", "任务"]))
    db.commit()
    db.close()

    r = client.post("/api/v1/knowledge/jobs/reindex", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["reindexed"] >= 2

    u = register(client, "13966600007", "提问的人")
    got = client.get("/api/v1/knowledge/search?q=提现到账要多久&kind=faq",
                     headers=auth(u)).json()
    assert got["degraded"] is False, "建过索引了还退化成关键词，说明索引没被用上"
    assert got["results"], got
    assert "提现" in got["results"][0]["text"]


def test_kb022_search_is_honest_about_not_being_semantic(client):
    """缺省 embedding 是词袋哈希，不是语义模型。

    一个悄悄退化成关键词的「语义检索」比没有更糟——你不会去修它。
    所以 `semantic` 必须如实为 False。
    """
    u = register(client, "13966600008", "较真的人")
    got = client.get("/api/v1/knowledge/search?q=任何问题&kind=faq", headers=auth(u)).json()
    assert got["semantic"] is False
    assert got["model"] == settings.EMBEDDING_MODEL


def test_kb011_reindex_is_incremental_not_a_full_rerun(client):
    """全表重跑在真实模型下是要花钱的。"""
    from app.modules.knowledge.models import FaqEntry

    db = SessionLocal()
    db.add(FaqEntry(question="一个问题", answer="一个答案", keywords=["问题"]))
    db.commit()
    db.close()
    # 库里本来就有种子 FAQ，所以断言的是**不变量**而不是某个绝对数字：
    # 第一次把没索引的都补上，第二次一条都不该再跑
    first = client.post("/api/v1/knowledge/jobs/reindex", headers=JOB_HEADERS).json()["reindexed"]
    assert first >= 1
    assert client.post("/api/v1/knowledge/jobs/reindex", headers=JOB_HEADERS).json()["reindexed"] == 0


def test_kb011_switching_models_triggers_rebuild(client, monkeypatch):
    """换模型后旧向量不可比：两个模型的向量做余弦会得到毫无意义的相似度。"""
    from app.modules.knowledge.models import FaqEntry

    db = SessionLocal()
    db.add(FaqEntry(question="问题", answer="答案", keywords=[]))
    db.commit()
    db.close()
    client.post("/api/v1/knowledge/jobs/reindex", headers=JOB_HEADERS)

    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "another-model-v2")
    registry.reset()
    try:
        out = client.post("/api/v1/knowledge/jobs/reindex", headers=JOB_HEADERS).json()
        assert out["reindexed"] >= 1, "换了模型却没有重建索引"
        assert out["model"] == "another-model-v2"
    finally:
        registry.reset()


def test_kb022_unindexed_search_degrades_and_says_so(client):
    """没建索引时退化为词面命中，但**明确标注** degraded。"""
    from app.modules.knowledge.models import FaqEntry

    db = SessionLocal()
    db.add(FaqEntry(question="没索引的问题", answer="没索引的答案", keywords=[]))
    db.commit()
    db.close()
    u = register(client, "13966600009", "早到的人")
    got = client.get("/api/v1/knowledge/search?q=没索引的问题&kind=faq",
                     headers=auth(u)).json()
    assert got["degraded"] is True
    assert got["results"]
