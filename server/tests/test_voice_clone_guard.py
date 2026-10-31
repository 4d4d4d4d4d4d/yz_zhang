"""SCN-234 发单拦下未经授权的 AI 声音克隆（344 号 spec，V371）。

能听出是谁的声音就受法律保护（《民法典》第一千零二十三条；2024 年全国首例 AI 生成声音人格权侵权案）。
只认「克隆 / 复刻 / 仿制」这类动词；克隆自己的声音、写明取得本人授权的、AI 旁白、真人按风格配音都放行。
误拦的走 V363 的人工复核。
"""
import pytest

from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_multiday_slots import _post

API = "/api/v1"


@pytest.mark.parametrize("text,kind", [
    ("用AI克隆周杰伦的声音唱生日歌", "voice_clone"), ("帮我复刻我前任的声音", "voice_clone"),
    ("声音克隆某主播带货", "voice_clone"), ("仿制老板的嗓音发语音", "voice_clone"),
    ("克隆我自己的声音做有声书", None), ("已取得本人授权书，复刻配音演员声音", None),
    ("经授权复刻主持人的声线", None), ("不克隆任何人的声音", None),
    ("AI生成的声音做旁白", None), ("语音合成的声音太机械", None), ("按风格来，不模仿某个具体的人", None),
    ("复刻一款经典蛋糕", None),                    # 没说声音
    # 之前几轮的边界照旧
    ("年检包过，不用上线", "fake_inspection"), ("本店不刷单", None), ("不想自己写，代写毕业论文", "ghostwrite"),
])
def test_what_the_voice_clone_guard_catches(text, kind):
    assert restricted_errand(text) == kind


def test_publishing_stops_unauthorized_cloning_and_points_to_the_honest_options(client, requester):
    r = _post(client, requester, title="生日惊喜", description="用AI克隆周杰伦的声音唱生日歌", category="配音", is_remote=True)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "voice_clone", r.text
    msg = r.json()["detail"]["message"]
    assert "「配音」单" in msg and "本人书面授权" in msg and "申请人工复核" in msg
    ok = _post(client, requester, title="有声书", description="克隆我自己的声音做有声书", category="配音", is_remote=True)
    assert ok.status_code in (200, 201), ok.text
    rv = client.post(f"{API}/tasks/errand-reviews", json={"title": "生日惊喜", "description": "用AI克隆周杰伦的声音唱生日歌",
                                                           "explanation": "其实是找真人模仿风格唱"}, headers=auth(requester))
    assert rv.status_code == 200 and rv.json()["kind_label"] == "克隆他人声音"
