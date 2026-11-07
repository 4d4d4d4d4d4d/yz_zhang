"""SCN-185 发单与报价里出现「保 offer、包就业、保过」时提示（311 号 spec，V338）。

录用、录取、考试结果由对方机构决定，谁也保证不了。平台不拦，只提示：发单时在说明体检里提醒，报名留言里写了的在发单人
看到的报名列表上标出来。前面几个字里有「不 / 没 / 无」的不算。
"""
import pytest

from app.modules.task.promises import APPLICATION_FLAG, PROMISE_HINT, has_result_promise
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post

API = "/api/v1"


@pytest.mark.parametrize("text", ["签保offer套餐", "包就业，不就业全退", "考证保过", "100% 录取", "保证拿到offer", "承诺上岸"])
def test_result_promises_are_recognized(text):
    assert has_result_promise(text), text


@pytest.mark.parametrize("text", ["不保 offer，只改简历", "绝不承诺包过", "没有包就业这回事", "保洁两小时", "包装搬运",
                                  "保存好资料", "不过退款", "照真实经历写"])
def test_ordinary_or_negated_text_is_not(text):
    assert not has_result_promise(text), text


def test_the_draft_check_warns_the_publisher(client, requester):
    r = client.post(f"{API}/profiles/task-draft", json={"title": "找人辅导求职，要求保offer", "category": "求职辅导",
                                                        "budget_cents": 50000}, headers=auth(requester)).json()
    assert {"kind": "result_promise", "text": PROMISE_HINT} in r["risks"]
    ok = client.post(f"{API}/profiles/task-draft", json={"title": "改简历两轮，不保 offer", "category": "求职辅导",
                                                         "budget_cents": 50000}, headers=auth(requester)).json()
    assert all(x["kind"] != "result_promise" for x in ok["risks"])


def test_applications_promising_results_are_flagged_for_the_publisher_only(client, requester):
    t = _post(client, requester, title="改简历", description="两轮修改", category="求职辅导").json()
    a = make_verified(client, "13600003381")
    b = make_verified(client, "13600003382")
    ra = client.post(f"{API}/tasks/{t['id']}/applications", json={"message": "我们团队包就业，拿不到全退"}, headers=auth(a))
    rb = client.post(f"{API}/tasks/{t['id']}/applications", json={"message": "改两轮，不保 offer"}, headers=auth(b))
    assert ra.status_code == 201 and rb.status_code == 201, "不拦"
    rows = {x["applicant_id"]: x for x in client.get(f"{API}/tasks/{t['id']}/applications", headers=auth(requester)).json()}
    assert rows[a["id"]]["promise_flag"] == APPLICATION_FLAG
    assert "promise_flag" not in rows[b["id"]], "没承诺的不出这个字段"
