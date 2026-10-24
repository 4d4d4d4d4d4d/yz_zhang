"""CLI-083b 再验一批调用点（312 号 spec，V339）。

这些 handler 返回变量或列表推导，静态读不出键（响应形状棘轮里的「未验证」）。这里用真实响应逐个与 SDK 声明比一遍，
棘轮随之收紧到新的值——**只许降不许升**，留着空位等于允许悄悄回涨。
"""
from tests.conftest import auth, make_admin, register
from tests.test_certification import make_verified
from tests.test_client_shape_alignment import _assert_inline_shape, _assert_shape
from tests.test_multiday_slots import _post

API = "/api/v1"


def test_task_side_calls_match_the_sdk(client, requester):
    t = _post(client, requester, title="改简历", description="两轮修改", category="求职辅导").json()
    w = make_verified(client, "13600003391")
    client.post(f"{API}/tasks/{t['id']}/applications", json={"message": "我们包就业"}, headers=auth(w))
    [row] = client.get(f"{API}/tasks/{t['id']}/applications", headers=auth(requester)).json()
    _assert_inline_shape(row, "listApplications")
    recs = client.get(f"{API}/tasks/{t['id']}/recommendations", headers=auth(requester)).json()
    assert recs, "要有推荐才验得到"
    for r in recs[:3]:
        _assert_shape(r, "Recommendation")
    tpl = client.get(f"{API}/task-templates?category=保洁", headers=auth(requester)).json()
    _assert_inline_shape(tpl, "taskTemplate")
    cancelled = client.post(f"{API}/tasks/{t['id']}/cancel", headers=auth(requester)).json()
    _assert_inline_shape(cancelled, "cancelTask")


def test_account_and_market_calls_match_the_sdk(client, requester):
    other = register(client, "13800339201", "被拉黑的人")
    client.post(f"{API}/users/{other['id']}/block", headers=auth(requester))
    [b] = client.get(f"{API}/users/me/blocks", headers=auth(requester)).json()
    _assert_inline_shape(b, "myBlocks")
    client.post(f"{API}/contents", json={"body": "一篇草稿", "title": "草稿", "publish": False}, headers=auth(requester))
    drafts = client.get(f"{API}/contents/mine?status=draft&limit=5", headers=auth(requester)).json()
    assert drafts, "要有一条草稿才验得到"
    _assert_shape(drafts[0], "ContentItem")      # myDrafts 的声明改成了 ContentItem[]（以前只写了三个字段）
    _post(client, requester, title="日常保洁", description="两小时", category="保洁")
    demand = client.get(f"{API}/knowledge/category-demand", headers=auth(requester)).json()
    assert demand
    _assert_inline_shape(demand[0], "categoryDemand")
    client.get(f"{API}/search?q=保洁", headers=auth(requester))
    client.get(f"{API}/search?q=保洁", headers=auth(other))
    client.get(f"{API}/search?q=保洁", headers=auth(make_verified(client, "13600003392")))
    trending = client.get(f"{API}/search/trending?limit=5", headers=auth(requester)).json()
    assert trending, "要有热词才验得到（静态扫描只认写了断言，不认断言跑没跑）"
    for x in trending:
        _assert_inline_shape(x, "trendingTerms")


def test_admin_category_update_matches_the_sdk(client):
    ops = make_admin(client, "13800339202")
    c = client.post(f"{API}/admin/categories", json={"name": "测试类目甲", "required_cert": "健康证明"}, headers=auth(ops)).json()
    plain = client.patch(f"{API}/admin/categories/{c['id']}?active=true", headers=auth(ops)).json()
    _assert_inline_shape(plain, "updateCategory")
    more = client.patch(f"{API}/admin/categories/{c['id']}?extra_certs=无犯罪记录证明", headers=auth(ops)).json()
    _assert_inline_shape(more, "updateCategory")
