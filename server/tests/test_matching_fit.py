"""SPACE-023（部分）推荐要看「和这一单有没有关系」。

V140 真浏览器演示：一单「咖啡店杯套设计」的推荐里，做过一单保洁、拿过五星的周师傅（68%）
排在**报了名、个人空间写着品牌与包装设计**的陈设计（59%）前面；理由还写着「技能部分匹配」——
而那单根本没写技能要求，0.5 是中性分，不是部分匹配。
"""
from tests.conftest import auth, register, topup, verify_user


def _space(client, user, headline):
    r = client.put("/api/v1/spaces/me", json={"revision": 0, "published": True, "headline": headline,
                                              "introduction": "", "items": []}, headers=auth(user))
    assert r.status_code == 200, r.text


def test_a_designer_who_applied_outranks_a_well_rated_cleaner_on_a_design_task(client, requester):
    from tests.test_task_flow import match_and_fund, publish_task

    cleaner = register(client, "13900018001", "周师傅")
    verify_user(client, cleaner, name="周师傅")
    designer = register(client, "13900018002", "陈设计")
    verify_user(client, designer, name="陈设计")
    _space(client, designer, "品牌与包装设计，做过 30 个小品牌")
    # 周师傅做成一单保洁、拿五星
    topup(client, requester, 50000)
    t = publish_task(client, requester)
    match_and_fund(client, requester, cleaner, t)
    client.post(f"/api/v1/tasks/{t['id']}/deliver", headers=auth(cleaner))
    client.post(f"/api/v1/tasks/{t['id']}/accept-delivery", headers=auth(requester))
    client.post(f"/api/v1/tasks/{t['id']}/reviews", json={"stars": 5}, headers=auth(requester))
    client.post(f"/api/v1/tasks/{t['id']}/reviews", json={"stars": 5}, headers=auth(cleaner))
    # 一单远程设计，陈设计报名
    d = client.post("/api/v1/tasks", json={"title": "咖啡店杯套设计", "description": "三款杯套", "category": "设计",
                                           "budget_cents": 150000, "is_remote": True, "ip_assignment": "assign"},
                    headers=auth(requester)).json()
    client.post(f"/api/v1/tasks/{d['id']}/applications", json={"message": "可以先出草图"}, headers=auth(designer))
    recs = client.get(f"/api/v1/tasks/{d['id']}/recommendations", headers=auth(requester)).json()
    ids = [r["user_id"] for r in recs]
    assert ids.index(designer["id"]) < ids.index(cleaner["id"])
    top = recs[ids.index(designer["id"])]
    assert "已报名这一单" in top["reasons"] and any("擅长「设计」" in x for x in top["reasons"])
    assert all("技能部分匹配" not in r["reasons"] for r in recs)   # 没写技能要求就不说部分匹配
    assert all(r["score"] <= 1 for r in recs)


def test_having_done_the_category_counts_more_than_saying_so(client, requester, worker):
    from tests.test_task_flow import match_and_fund, publish_task

    talker = register(client, "13900018003", "说得好")
    verify_user(client, talker, name="说得好")
    _space(client, talker, "保洁达人")
    topup(client, requester, 50000)
    t = publish_task(client, requester)
    match_and_fund(client, requester, worker, t)
    client.post(f"/api/v1/tasks/{t['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{t['id']}/accept-delivery", headers=auth(requester))
    t2 = publish_task(client, requester, title="再来一次深度保洁")
    recs = {r["user_id"]: r for r in client.get(f"/api/v1/tasks/{t2['id']}/recommendations",
                                                headers=auth(requester)).json()}
    assert any(x.startswith("做成过 1 单「保洁」") for x in recs[worker["id"]]["reasons"])
    assert any("擅长「保洁」" in x for x in recs[talker["id"]]["reasons"])
