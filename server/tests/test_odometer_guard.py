"""SCN-243 发单拦下帮人篡改里程表（351 号 spec，V378）。

调表卖车是欺诈（《消费者权益保护法》第五十五条）。「调 / 改……里程 / 公里数 / 码表」与「里程……调回 / 改小 / 清零」
直接算；俚语「调表 / 改表」只在说到车时算（调手表不算）；「警惕 / 查 / 有没有 / 怀疑」这类识别说法、否定说法放行。
误拦的走 V363 的人工复核。
"""
import pytest

from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_multiday_slots import _post

API = "/api/v1"


@pytest.mark.parametrize("text,kind", [
    ("帮我把车的里程调回五万公里", "odometer_fraud"), ("二手车调表，表显改小", "odometer_fraud"),
    ("车子公里数调小一点", "odometer_fraud"), ("码表清零", "odometer_fraud"), ("帮我调表，车明天卖", "odometer_fraud"),
    ("篡改里程再出手", "odometer_fraud"),
    ("帮我调表，手表慢了五分钟", None),                 # 没说车：调手表
    ("帮我看二手车，警惕调表", None), ("查一下这台车有没有调表", None), ("怀疑调表，帮我核对里程", None),
    ("不调表、不改里程", None), ("仪表盘维修", None), ("改装车灯", None), ("核对里程与维保记录", None),
    # 之前几轮的边界照旧
    ("用AI克隆周杰伦的声音唱生日歌", "voice_clone"), ("年检包过，不用上线", "fake_inspection"), ("本店不刷单", None),
])
def test_what_the_odometer_guard_catches(text, kind):
    assert restricted_errand(text) == kind


def test_publishing_stops_odometer_tampering_and_points_to_inspection(client, requester):
    r = _post(client, requester, title="卖车前处理", description="帮我把车的里程调回五万公里", category="跑腿")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "odometer_fraud", r.text
    msg = r.json()["detail"]["message"]
    assert "「二手车陪验」单" in msg and "申请人工复核" in msg
    ok = _post(client, requester, title="陪看二手车", description="查一下这台车有没有调表", category="二手车陪验")
    assert ok.status_code in (200, 201), ok.text
    rv = client.post(f"{API}/tasks/errand-reviews", json={"title": "卖车前处理", "description": "帮我把车的里程调回五万公里",
                                                           "explanation": "仪表坏了换新表，要恢复成真实里程"}, headers=auth(requester))
    assert rv.status_code == 200 and rv.json()["kind_label"] == "篡改里程表"
