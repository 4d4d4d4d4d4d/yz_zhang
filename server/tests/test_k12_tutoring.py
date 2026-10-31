"""SCN-143 不承接中小学学科类有偿家教（213 号 spec，V241）。

依据见 212 号 spec 第 1 节（教监管厅函〔2021〕8号）。发布（含草稿）时拦下，说清为什么、能走什么路；
非学科陪练、成人与大学生的辅导不受影响。
"""
import pytest

from app.modules.task.k12 import is_k12_subject_tutoring
from tests.conftest import auth
from tests.test_multiday_slots import _post

API = "/api/v1/tasks"


@pytest.mark.parametrize("text", [
    "给孩子找个数学家教，每周两次", "初二英语补课，上门", "小学三年级语文作文辅导", "儿子补物理，一对一",
    "高一化学培优", "小升初奥数辅导", "女儿 补英语 每周末"])
def test_k12_subject_tutoring_is_recognized(text):
    assert is_k12_subject_tutoring(text), text


@pytest.mark.parametrize("text", [
    "孩子钢琴陪练，每周一次", "孩子游泳辅导，周末", "成人英语口语辅导", "大学高数作业辅导", "帮忙接孩子放学", "给小学生做数学教具设计",
    "初中同学聚会策划"])
def test_others_are_not(text):
    assert not is_k12_subject_tutoring(text), text


def test_publishing_and_drafts_are_refused_with_the_reason(client, requester):
    for kw in ({"publish_now": True}, {"publish_now": False}):
        r = _post(client, requester, title="给孩子找数学家教", description="初二，每周两次上门", **kw)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "k12_subject_tutoring", kw
        assert "办学资质" in r.json()["detail"]["message"]
    ok = _post(client, requester, title="孩子钢琴陪练", description="每周一次，家长在场")
    assert ok.status_code in (200, 201), ok.text


def test_a_draft_edited_into_tutoring_cannot_be_published(client, requester):
    t = _post(client, requester, title="周末帮手", description="帮忙", publish_now=False).json()
    from app.core.db import SessionLocal
    from app.modules.task.models import Task

    with SessionLocal() as db:
        db.get(Task, t["id"]).description = "其实是给孩子补数学"
        db.commit()
    r = client.post(f"{API}/{t['id']}/publish", headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "k12_subject_tutoring"
