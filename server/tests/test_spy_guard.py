"""SCN-271 发单拦下偷看、调取他人通信记录与定位、跟踪他人（379 号 spec，V406）。

行踪轨迹、通信内容都是个人信息，未经同意获取属于侵犯个人信息，情节严重的触犯刑法（《刑法》第二百五十三条之一）。
378 号（数据恢复包）上线时发现：「恢复老公手机里删掉的聊天记录」「定位老婆的手机」一条都不拦。
对象必须是「另一个人」（配偶、恋人、前任、同事、别人、他的 / 她的……）；自己的设备、自己的数据不算；
自己是被定位、被监控的一方、请人排查拆除的放行；否定说法放行；误拦走 V363 的人工复核。
"""
import pytest

from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_multiday_slots import _post

API = "/api/v1"


@pytest.mark.parametrize("text,kind", [
    ("帮我恢复老公手机里删掉的聊天记录", "covert_spying"), ("查一下前任的微信聊天记录", "covert_spying"),
    ("怀疑老公出轨，查一下他的聊天记录", "covert_spying"), ("导出女朋友的通话记录", "covert_spying"),
    ("定位老婆的手机", "covert_spying"), ("定位他的手机", "covert_spying"), ("想知道男朋友每天的行踪", "covert_spying"),
    ("我想看看她的位置", "covert_spying"), ("在老婆车上装个定位器", "covert_spying"), ("偷拍邻居", "covert_spying"),
    ("监听同事的电话", "covert_spying"),
    ("老婆的聊天记录帮我导出来", "covert_spying"),   # 对象在前、动作在后
    # 放行：自己的、被监控的一方、和隐私无关、否定说法
    ("恢复我自己手机里误删的聊天记录", None), ("帮我导出我自己的微信聊天记录", None),
    ("怀疑老公在我车上装了定位器，帮我排查", None), ("我手机被定位了，帮我检查", None), ("帮我排查车上有没有定位器", None),
    ("帮老婆的手机恢复出厂设置", None), ("帮我老公的手机换屏", None), ("给他的手机贴膜", None), ("帮他寄快递", None),
    ("老公位置在外地，帮他寄快递", None), ("不查老公聊天记录", None),
    # 之前几轮的边界照旧
    ("帮我把车的里程调回五万公里", "odometer_fraud"), ("用AI克隆周杰伦的声音唱生日歌", "voice_clone"), ("本店不刷单", None),
])
def test_what_the_spying_guard_catches(text, kind):
    assert restricted_errand(text) == kind


def test_publishing_stops_spying_and_points_to_data_recovery_and_review(client, requester):
    r = _post(client, requester, title="恢复聊天记录", description="帮我恢复老公手机里删掉的聊天记录", category="数据恢复")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "covert_spying", r.text
    msg = r.json()["detail"]["message"]
    assert "「数据恢复」单" in msg and "排查" in msg and "申请人工复核" in msg
    ok = _post(client, requester, title="恢复照片", description="恢复我自己手机里误删的聊天记录和照片", category="数据恢复")
    assert ok.status_code in (200, 201), ok.text
    rv = client.post(f"{API}/tasks/errand-reviews", json={"title": "恢复聊天记录", "description": "帮我恢复老公手机里删掉的聊天记录",
                                                           "explanation": "老公本人同意并会到场，手机是他的"}, headers=auth(requester))
    assert rv.status_code == 200 and rv.json()["kind_label"] == "偷看定位他人"


def test_the_recovery_pack_and_the_guard_draw_the_same_line():
    """378 号的数据恢复包说「别人的设备没授权不碰」；发单拦截也真的拦（同一条线）。"""
    from tests.test_v286_packs import _load

    a = _load("data-recovery")["assistants"][0]
    assert any("别人的设备" in f for f in a["forbidden"])
    assert restricted_errand("帮我恢复老公手机里删掉的聊天记录") == "covert_spying"
