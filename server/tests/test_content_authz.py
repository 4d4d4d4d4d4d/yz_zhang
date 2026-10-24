"""SEC-060f 内容类对象级授权：两账号行为验（114 号 spec）。

V124 把 166 个带参端点全部写进了归属规则表，并对钱与身份那一批做了两账号行为验；
内容类（作品、评论、圈层）只有规则、没有人拿 B 的 token 去碰 A 的对象试过。
OWASP API1:2023（BOLA）的标准做法就是这个：**扫描器判断不了哪个对象该给谁**，
只能靠显式的归属判据加上「换一个账号、换一个 id」的测试。

第一次跑就红了三处（V139 之前）：
- `GET /contents/{id}` 只看「已发布」，不看可见性——别人设成**仅自己可见**的作品，
  任何登录用户按 id 就能读；「仅粉丝」「仅圈内」同样；
- `GET /contents/{id}/comments` **不要登录、不看状态、不看可见性**：草稿、已删除、仅自己可见的作品下面的评论，
  未登录也能读；
- 点赞与评论同样只看「已发布」：不是粉丝也能在「仅粉丝」的作品下面评论——评论本身就泄露了作品存在。
"""
import pytest

from tests.conftest import auth, register


@pytest.fixture()
def people(client):
    a = register(client, "13800170001", "作者")
    b = register(client, "13800170002", "路人")
    fan = register(client, "13800170003", "粉丝")
    peer = register(client, "13800170004", "圈友")
    r = client.put(f"/api/v1/users/{a['id']}/follow", headers=auth(fan))
    assert r.status_code in (200, 201), r.text
    circle = client.post("/api/v1/circles", json={"name": "写作圈", "kind": "interest"}, headers=auth(a)).json()
    assert client.post(f"/api/v1/circles/{circle['id']}/join", headers=auth(peer)).status_code == 200
    return {"a": a, "b": b, "fan": fan, "peer": peer, "circle": circle}


def _post(client, user, **kw):
    body = {"kind": "post", "body": "今天的作品", **kw}
    r = client.post("/api/v1/contents", json=body, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def _comment(client, author, content_id, text="我先评一条"):
    r = client.post(f"/api/v1/contents/{content_id}/comments", json={"body": text}, headers=auth(author))
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------ 读
@pytest.mark.parametrize("visibility, allowed", [
    ("public", {"a", "b", "fan", "peer"}),
    ("followers", {"a", "fan"}),
    ("circle", {"a", "peer"}),
    ("private", {"a"}),
])
def test_who_can_open_a_published_work_by_id(client, people, visibility, allowed):
    extra = {"circle_id": people["circle"]["id"]} if visibility == "circle" else {}
    c = _post(client, people["a"], visibility=visibility, **extra)
    for who in ("a", "b", "fan", "peer"):
        r = client.get(f"/api/v1/contents/{c['id']}", headers=auth(people[who]))
        assert (r.status_code == 200) == (who in allowed), f"{visibility}：{who} 得到 {r.status_code}"
        if r.status_code != 200:
            assert r.status_code == 404, "看不见就是不存在：403 会告诉别人这个 id 上确实有东西"


def test_comments_follow_the_work_they_hang_under(client, people):
    """评论不是一个独立的公开资源：作品看不见，它下面的评论也看不见；未登录一律不给。"""
    c = _post(client, people["a"], visibility="private")
    _comment(client, people["a"], c["id"], "只写给自己的备注")
    url = f"/api/v1/contents/{c['id']}/comments"
    assert client.get(url).status_code in (401, 403), "未登录一律不给"
    assert client.get(url, headers=auth(people["b"])).status_code == 404
    mine = client.get(url, headers=auth(people["a"]))
    assert mine.status_code == 200 and mine.json()[0]["body"] == "只写给自己的备注"


def test_comments_under_a_draft_or_a_removed_work_are_not_readable(client, people):
    pub = _post(client, people["a"])
    _comment(client, people["b"], pub["id"])
    assert client.delete(f"/api/v1/contents/{pub['id']}", headers=auth(people["a"])).status_code == 200
    assert client.get(f"/api/v1/contents/{pub['id']}/comments", headers=auth(people["b"])).status_code == 404
    draft = _post(client, people["a"], publish=False)
    assert client.get(f"/api/v1/contents/{draft['id']}/comments", headers=auth(people["b"])).status_code == 404


def test_someone_elses_draft_is_invisible(client, people):
    d = _post(client, people["a"], publish=False)
    assert client.get(f"/api/v1/contents/{d['id']}", headers=auth(people["b"])).status_code == 404
    assert client.get(f"/api/v1/contents/{d['id']}", headers=auth(people["a"])).status_code == 200


# ------------------------------------------------------------------ 写
@pytest.mark.parametrize("visibility", ["followers", "private"])
def test_you_cannot_comment_or_like_what_you_cannot_see(client, people, visibility):
    c = _post(client, people["a"], visibility=visibility)
    r = client.post(f"/api/v1/contents/{c['id']}/comments", json={"body": "路过"}, headers=auth(people["b"]))
    assert r.status_code == 404
    assert client.post(f"/api/v1/contents/{c['id']}/like", headers=auth(people["b"])).status_code == 404
    mine = client.get(f"/api/v1/contents/{c['id']}", headers=auth(people["a"])).json()
    assert mine["comment_count"] == 0 and mine["like_count"] == 0


def test_a_follower_can_interact_with_a_followers_only_work(client, people):
    c = _post(client, people["a"], visibility="followers")
    assert client.post(f"/api/v1/contents/{c['id']}/like", headers=auth(people["fan"])).status_code == 200
    _comment(client, people["fan"], c["id"], "写得好")


def test_outsider_cannot_edit_publish_or_delete_someone_elses_work(client, people):
    a, b = people["a"], people["b"]
    pub = _post(client, a, title="原标题")
    draft = _post(client, a, publish=False)
    assert client.patch(f"/api/v1/contents/{pub['id']}", json={"title": "被改了"}, headers=auth(b)).status_code == 403
    assert client.post(f"/api/v1/contents/{draft['id']}/publish", headers=auth(b)).status_code in (403, 404)
    assert client.delete(f"/api/v1/contents/{pub['id']}", headers=auth(b)).status_code == 403
    after = client.get(f"/api/v1/contents/{pub['id']}", headers=auth(a)).json()
    assert after["title"] == "原标题" and after["status"] == "published"
    assert client.get(f"/api/v1/contents/{draft['id']}", headers=auth(a)).json()["status"] == "draft"


def test_a_followers_only_work_shows_up_in_the_authors_list_for_followers(client, people):
    """「谁看得见」只有一个判据：按 id 读与按作者列，结论必须一样。"""
    c = _post(client, people["a"], visibility="followers")
    ids = lambda who: {x["id"] for x in client.get(  # noqa: E731
        f"/api/v1/users/{people['a']['id']}/contents", headers=auth(people[who])).json()}
    assert c["id"] in ids("fan") and c["id"] in ids("a")
    assert c["id"] not in ids("b")


# ------------------------------------------------------------------ 圈层
def test_only_circle_admins_approve_or_remove_members(client, people):
    a, peer, b = people["a"], people["peer"], people["b"]
    approval = client.post("/api/v1/circles", json={"name": "审核圈", "kind": "interest", "join_policy": "approval"},
                           headers=auth(a)).json()
    client.post(f"/api/v1/circles/{approval['id']}/join", headers=auth(b))
    cid = approval["id"]
    assert client.post(f"/api/v1/circles/{cid}/members/{b['id']}/approve", headers=auth(peer)).status_code == 403
    assert client.post(f"/api/v1/circles/{cid}/members/{b['id']}/approve", headers=auth(b)).status_code == 403
    circle = people["circle"]["id"]
    assert client.post(f"/api/v1/circles/{circle}/members/{peer['id']}/remove", headers=auth(b)).status_code == 403
    members = {m["user_id"] for m in client.get(f"/api/v1/circles/{circle}/members", headers=auth(a)).json()}
    assert peer["id"] in members


def test_circle_feed_tasks_and_stats_need_membership(client, people):
    circle = people["circle"]["id"]
    _post(client, people["peer"], visibility="circle", circle_id=circle)
    for path in ("feed", "tasks"):
        assert client.get(f"/api/v1/circles/{circle}/{path}", headers=auth(people["b"])).status_code == 403
        assert client.get(f"/api/v1/circles/{circle}/{path}", headers=auth(people["peer"])).status_code == 200
    assert client.get(f"/api/v1/circles/{circle}/stats", headers=auth(people["peer"])).status_code == 403
    assert client.get(f"/api/v1/circles/{circle}/stats", headers=auth(people["a"])).status_code == 200
