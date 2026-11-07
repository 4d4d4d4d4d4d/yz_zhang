"""SCN-219 被发单拦截挡下时申请人工复核（336 号 spec，V363）。

拦截只看文字、会误拦。用户写一句说明，运营在后台看原文与说明：通过就放行这一段文字发一单，维持就写清理由。
只认同一个人、一字不差的同一段文字；通过只放行一单；运营不能处理自己提出的。
"""
import pytest

from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from app.modules.notification.models import Notification
from tests.conftest import auth, make_admin
from tests.test_multiday_slots import _post

API = "/api/v1"
R = f"{API}/tasks/errand-reviews"
A = f"{API}/admin/errand-reviews"
# 「代写」+「论文」挨着：拦截会当成代写学位论文；实际是给论文集写宣传文案
TITLE = "论文集出版宣传"
DESC = "帮我写论文集的新书推介文案，三百字，发公众号"


def _titles(user_id):
    with SessionLocal() as db:
        return [n.title for n in db.query(Notification).filter(Notification.user_id == user_id)]


def test_approved_review_lets_that_exact_text_through_once(client, requester):
    from tests.test_client_shape_alignment import _assert_shape

    ops1, ops2 = make_admin(client, "13600003631", "运营甲"), make_admin(client, "13600003632", "运营乙")
    blocked = _post(client, requester, title=TITLE, description=DESC, category="文案写作", is_remote=True)
    assert blocked.status_code == 400 and blocked.json()["detail"]["code"] == "academic_ghostwriting", blocked.text
    assert "申请人工复核" in blocked.json()["detail"]["message"], "提示里说清有复核这条路"
    assert blocked.json()["detail"]["review"] == "errand_review", "客户端据此显示「申请人工复核」"
    short = client.post(R, json={"title": TITLE, "description": DESC, "explanation": "误拦"}, headers=auth(requester))
    assert short.status_code == 400 and short.json()["detail"]["code"] == "errand_review_explanation_required"
    clean = client.post(R, json={"title": "周末理货", "description": "超市理货", "explanation": "这单没问题吧帮我看看"},
                        headers=auth(requester))
    assert clean.status_code == 400 and clean.json()["detail"]["code"] == "errand_review_not_blocked", "没被拦的不用申请"
    r = client.post(R, json={"title": TITLE, "description": DESC, "explanation": "是给已出版的论文集写宣传推介，不是代写论文"},
                    headers=auth(requester))
    assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["kind"] == "ghostwrite", r.text
    _assert_shape(r.json(), "ErrandReviewItem")
    rid = r.json()["id"]
    assert "有一条发单拦截的复核申请" in _titles(ops1["id"]), "通知运营"
    again = client.post(R, json={"title": TITLE, "description": DESC, "explanation": "再交一次看看会怎么样"},
                        headers=auth(requester))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "errand_review_pending"
    assert client.get(A, headers=auth(requester)).status_code == 403, "普通用户碰不到后台"
    assert client.post(f"{A}/{rid}/approve", json={}, headers=auth(requester)).status_code == 403
    listed = client.get(A, headers=auth(ops1))
    assert listed.status_code == 200 and listed.json()[0]["id"] == rid and listed.json()[0]["explanation"].startswith("是给")
    _assert_shape(listed.json()[0], "ErrandReviewAdminItem")
    still = _post(client, requester, title=TITLE, description=DESC, category="文案写作", is_remote=True)
    assert still.status_code == 400, "还没处理，照拦"
    ok = client.post(f"{A}/{rid}/approve", json={"note": "看过原文，是宣传文案"}, headers=auth(ops1))
    assert ok.status_code == 200 and ok.json()["status"] == "approved", ok.text
    _assert_shape(ok.json(), "ErrandReviewItem")
    assert "你的发单复核通过了" in _titles(requester["id"])
    assert client.post(f"{A}/{rid}/reject", json={"note": "改主意了不行"}, headers=auth(ops2)).status_code == 409, "处理过的不能再处理"
    from tests.test_certification import make_verified

    other = make_verified(client, "13600003636")
    assert _post(client, other, title=TITLE, description=DESC, category="文案写作", is_remote=True).status_code == 400, \
        "只认申请的那个人：别人发同一段文字照拦"
    tweaked = _post(client, requester, title=TITLE, description=DESC + "！", category="文案写作", is_remote=True)
    assert tweaked.status_code == 400, "改了一个字就是另一段文字"
    passed = _post(client, requester, title=TITLE, description=DESC, category="文案写作", is_remote=True)
    assert passed.status_code in (200, 201), passed.text
    mine = client.get(R, headers=auth(requester)).json()
    _assert_shape(mine[0], "ErrandReviewItem")
    assert mine[0]["task_id"] == passed.json()["id"], "放行记在这一单上"
    second = _post(client, requester, title=TITLE, description=DESC, category="文案写作", is_remote=True)
    assert second.status_code == 400, "只放行一单"
    renew = client.post(R, json={"title": TITLE, "description": DESC, "explanation": "又出了一本，再发一单宣传"},
                        headers=auth(requester))
    assert renew.status_code == 200, "用掉了的可以再申请"
    with SessionLocal() as db:
        actions = [a.action for a in db.query(AdminAudit).filter(AdminAudit.action.like("errand_review%"))]
    assert "errand_review_approve" in actions
    export = client.get(f"{API}/users/me/export", headers=auth(requester)).json()
    assert [r["explanation"] for r in export["errand_reviews"]][0].startswith("是给"), "复核申请进本人数据导出"
    assert "errand_reviews" not in client.get(f"{API}/users/me/export", headers=auth(other)).json(), "没申请过的导出与以前一样"


def test_draft_then_publish_binds_the_pass_to_that_task(client, requester):
    ops1 = make_admin(client, "13600003633", "运营甲")
    rid = client.post(R, json={"title": TITLE, "description": DESC, "explanation": "论文集的宣传文案，不是代写论文"},
                      headers=auth(requester)).json()["id"]
    assert client.post(f"{A}/{rid}/approve", json={}, headers=auth(ops1)).status_code == 200
    dup = client.post(R, json={"title": TITLE, "description": DESC, "explanation": "通过了再申请一次会怎样"}, headers=auth(requester))
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "errand_review_approved", "通过了还没用：直接发就行"
    draft = _post(client, requester, title=TITLE, description=DESC, category="文案写作", is_remote=True, publish_now=False)
    assert draft.status_code in (200, 201), draft.text
    pub = client.post(f"{API}/tasks/{draft.json()['id']}/publish", headers=auth(requester))
    assert pub.status_code == 200, pub.text
    other = _post(client, requester, title=TITLE, description=DESC, category="文案写作", is_remote=True, publish_now=False)
    assert other.status_code == 400, "已经记在第一单上，第二单的草稿也不收"


def test_reject_needs_a_reason_and_ops_cannot_decide_their_own(client, requester):
    ops1, ops2 = make_admin(client, "13600003634", "运营甲"), make_admin(client, "13600003635", "运营乙")
    rid = client.post(R, json={"title": "刷单", "description": "店铺刷单一百单", "explanation": "就是想冲一下销量而已"},
                      headers=auth(requester)).json()["id"]
    no_reason = client.post(f"{A}/{rid}/reject", json={"note": "不"}, headers=auth(ops1))
    assert no_reason.status_code == 400 and no_reason.json()["detail"]["code"] == "errand_review_reason_required"
    rj = client.post(f"{A}/{rid}/reject", json={"note": "就是刷单，平台不能接"}, headers=auth(ops1))
    assert rj.status_code == 200 and rj.json()["status"] == "rejected" and rj.json()["decision_note"] == "就是刷单，平台不能接"
    assert "你的发单复核没有通过" in _titles(requester["id"])
    again = client.post(R, json={"title": "刷单", "description": "店铺刷单一百单", "explanation": "再申请一次试试看"},
                        headers=auth(requester))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "errand_review_rejected"
    assert "就是刷单，平台不能接" in again.json()["detail"]["message"], "说清为什么"
    assert _post(client, requester, title="刷单", description="店铺刷单一百单", is_remote=True).status_code == 400
    own = client.post(R, json={"title": "刷好评", "description": "写二十条好评", "explanation": "运营自己发单也被拦了"},
                      headers=auth(ops1)).json()["id"]
    me = client.post(f"{A}/{own}/approve", json={}, headers=auth(ops1))
    assert me.status_code == 403 and me.json()["detail"]["code"] == "errand_review_self", "不能处理自己提出的"
    assert client.post(f"{A}/{own}/reject", json={"note": "就是刷好评"}, headers=auth(ops2)).status_code == 200
    with SessionLocal() as db:
        assert db.query(AdminAudit).filter(AdminAudit.action == "errand_review_reject").count() == 2


def test_at_most_five_pending_and_old_callers_unchanged(client, requester):
    from app.modules.task.errand import assert_no_restricted_errand

    for i in range(5):
        r = client.post(R, json={"title": f"刷单{i}", "description": "x", "explanation": "测试同时在等的上限"},
                        headers=auth(requester))
        assert r.status_code == 200, r.text
    six = client.post(R, json={"title": "刷单6", "description": "x", "explanation": "测试同时在等的上限"}, headers=auth(requester))
    assert six.status_code == 409 and six.json()["detail"]["code"] == "errand_review_too_many"
    with pytest.raises(Exception) as e:
        assert_no_restricted_errand("帮我刷单")   # 不给 db 的老调用：照拦
    assert e.value.detail["code"] == "fake_review"
