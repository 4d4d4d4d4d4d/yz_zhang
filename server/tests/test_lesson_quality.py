"""KB-063 经验质量过滤（324 号 spec，V351）：太短、没有具体信息的核验经验不进 agent 的提示词。

以前随手写的「不行」「不满意」也会被拼进下一单的系统提示词：对下一单没有指导价值，还占提示词的位置、带偏判断。
判据：理由或修正方向至少一处说得出「哪里不对」或「怎么改」——去掉标点空白后至少 6 个字，且不是一句空话。
"""
import pytest

from app.core.db import SessionLocal


@pytest.mark.parametrize("reason,revision,useful", [
    ("不行", "", False),
    ("不满意！！", "", False),
    ("质量差。", "", False),
    ("还可以吧", "", False),
    ("重做", "  ", False),
    ("没有拍完工照片", "", True),
    ("不行", "窗户要擦干净再拍照", True),
    ("卫生间地漏没清", "", True),
    ("不符合要求", "", False),
    # 标点凑够长度的不算具体
    ("不行！！！！！", "", False),
    ("差。。。 。。。", "", False),
    # 够 6 个字却仍然是空话
    ("做得不好请重做", "", False),
    ("完全不符合要求！", "", False),
    ("不是我想要的", "", False),
])
def test_what_counts_as_a_useful_lesson(reason, revision, useful):
    from app.modules.verify.service import lesson_useful

    assert lesson_useful(reason, revision) is useful


def test_vague_lessons_are_dropped_and_still_five_useful_ones_reach_the_agent(client):
    from app.modules.verify.models import VerificationLesson
    from app.modules.verify.service import LESSON_LIMIT, lessons_for, lessons_prompt

    with SessionLocal() as db:
        for i in range(LESSON_LIMIT):
            db.add(VerificationLesson(category="质量保洁", outcome="revised", criteria=[], reason=f"第{i}间卧室的踢脚线没擦"))
        for vague in ("不行", "不满意", "质量差", "一般", "重做", "差"):
            db.add(VerificationLesson(category="质量保洁", outcome="rejected", criteria=[], reason=vague))
        db.commit()
        rows = lessons_for(db, "质量保洁")
        prompt = lessons_prompt(rows)
    assert len(rows) == LESSON_LIMIT, "空话筛掉后仍凑够条数（新的空话不会把有用的旧经验挤出去）"
    assert all("踢脚线" in r.reason for r in rows)
    for vague in ("：不行", "：不满意", "：质量差", "：一般", "：重做"):
        assert vague not in prompt
