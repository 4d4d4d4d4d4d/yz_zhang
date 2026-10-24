"""SCN-161 防诈骗知识按通报定期更新（289 号 spec，V316）。

骗术常换：防诈骗那条知识写了有效期（按季度复核），到期前 30 天就进场景雷达，让运营赶在过期前
对照最新通报更新；已过期的照旧标「已过有效期」（V148），两句话分开说。
"""
from datetime import date, timedelta

from app.modules.packs import service
from tests.conftest import auth
from tests.test_packs import SEED, _def, _publish
from tests.test_v286_packs import _load

API = "/api/v1"


def _radar_evidence(client, a):
    radar = client.get(f"{API}/admin/packs/radar", headers=auth(a)).json()
    return [x["evidence"] for x in radar if x["source"] == "pack_gap" and x["key"] == "collab-basics"]


def test_knowledge_due_within_30_days_is_on_the_radar_before_it_expires(client, admins):
    today = date.today()
    ks = SEED["knowledge"]
    due = {**ks[0], "valid_until": (today + timedelta(days=service.EXPIRING_DAYS)).isoformat()}
    later = {**ks[1], "valid_until": (today + timedelta(days=service.EXPIRING_DAYS + 1)).isoformat()}
    gone = {**ks[2], "valid_until": (today - timedelta(days=1)).isoformat()}
    _publish(client, admins, _def(knowledge=[due, later, gone, *ks[3:]]))
    ev = _radar_evidence(client, admins[0])
    assert len(ev) == 1, ev
    assert f"1 条知识 30 天内到期：{due['title']}" in ev[0] and "对照最新通报或法规更新" in ev[0]
    assert later["title"] not in ev[0], "31 天后才到期的不提"
    assert f"1 条知识已过有效期：{gone['title']}" in ev[0], "过期的照旧单独说"
    assert ev[0].count(gone["title"]) == 1, "已过期的不再算「即将到期」"


def test_no_due_knowledge_means_no_signal(client, admins):
    far = [{**k, "valid_until": (date.today() + timedelta(days=200)).isoformat()} for k in SEED["knowledge"]]
    _publish(client, admins, _def(knowledge=far))
    assert _radar_evidence(client, admins[0]) == []


def test_anti_fraud_knowledge_carries_a_review_date_and_says_where_to_check():
    k = {x["key"]: x for x in _load("elder-phone-teaching")["knowledge"]}["anti-fraud"]
    assert k["valid_until"], "防诈骗知识要写有效期（按季度复核）"
    assert "最新通报" in k["source"] and "96110" in k["body"]
