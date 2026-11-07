"""CNT-023 / CNT-024 / CONC-066 关注列表、内容流里的关注状态，与那一页的查询次数（102 号 spec）。

V117 把「关注」从 toggle 改成了两个幂等动作，并给空间页补了读状态的接口。
剩下两件当时记进台账的：

- **CNT-024 内容流里的关注按钮没有状态**：永远写着「关注」；已关注的人点了
  没有任何变化（幂等），也没法从流里取消关注。
- **CNT-023 没有关注列表页**：只有计数。「这 42 个关注者是谁」答不出来。

做 CNT-024 时撞上一个既有的 N+1：内容流的 `_dump` 每条各查两次（作者、是否
点赞），一页 20 条就是 40 多次查询；照原样再加「是否关注作者」就是 60 多次。
所以列表接口改成一页三次查询，并用一条计数断言钉住它。
"""
import pytest
from sqlalchemy import event

from tests.conftest import auth, register


def _post(client, user, body):
    r = client.post("/api/v1/contents", json={"body": body}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------- CNT-024 内容流的关注状态
def test_cnt024_feed_tells_the_viewer_whether_they_follow_each_author(client):
    reader = register(client, "13800099001", "读者")
    followed = register(client, "13800099002", "关注了的作者")
    stranger = register(client, "13800099003", "没关注的作者")
    _post(client, followed, "我关注的人发的")
    _post(client, stranger, "陌生人发的")
    _post(client, reader, "我自己发的")
    client.put(f"/api/v1/users/{followed['id']}/follow", headers=auth(reader))

    feed = {c["body"]: c for c in client.get("/api/v1/feed", headers=auth(reader)).json()}
    assert feed["我关注的人发的"]["author_followed_by_viewer"] is True
    assert feed["陌生人发的"]["author_followed_by_viewer"] is False
    # 对自己没有「关注」这回事——None，不是 False（与 follow-stats 同一约定）
    assert feed["我自己发的"]["author_followed_by_viewer"] is None


def test_cnt024_single_content_view_carries_the_same_field(client):
    """详情接口走逐条查询那条路，字段与列表一致。"""
    reader = register(client, "13800099011", "读者")
    author = register(client, "13800099012", "作者")
    c = _post(client, author, "一条")
    client.put(f"/api/v1/users/{author['id']}/follow", headers=auth(reader))
    got = client.get(f"/api/v1/contents/{c['id']}", headers=auth(reader)).json()
    assert got["author_followed_by_viewer"] is True


# ------------------------------------------------- CONC-066 一页几次查询
def _count_queries(fn):
    from app.core.db import engine

    seen = []

    def before(conn, cursor, statement, *a, **k):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return len(seen)


def test_conc066_feed_query_count_does_not_grow_with_page_size(client):
    """一页 5 条与一页 20 条，查询次数一样。

    改造前每条两次（作者 + 是否点赞），20 条就是 40 多次；照原样再加
    「是否关注作者」就是 60 多次。**不是绝对数字，是「不随条数增长」**——
    绝对数字会因为鉴权、限流这些与这一页无关的东西变动，那会是假报警。
    """
    from app.core.db import SessionLocal
    from app.modules.account.models import User
    from app.modules.content.models import Content

    reader = register(client, "13800099021", "读者")
    # 这条量的是**读**，所以直接往库里放 20 个作者各一条——走 API 会撞上
    # 写路径的按 IP 限流（同一个测试里 40 次写），而那与要量的东西无关
    db = SessionLocal()
    try:
        for i in range(20):
            u = User(phone=f"138000991{i:02d}", nickname=f"作者{i}", password_hash="x")
            db.add(u)
            db.flush()
            db.add(Content(author_id=u.id, body=f"第 {i} 条", status="published",
                           visibility="public"))
        db.commit()
    finally:
        db.close()

    small = _count_queries(lambda: client.get("/api/v1/feed?limit=5", headers=auth(reader)))
    large = _count_queries(lambda: client.get("/api/v1/feed?limit=20", headers=auth(reader)))
    assert large == small, (
        f"一页 5 条用了 {small} 次查询，20 条用了 {large} 次——查询次数随条数增长（N+1）"
    )


# ------------------------------------------------- CNT-023 关注列表
@pytest.fixture()
def star(client):
    """一个公开的人，被四个人关注：一个公开、一个设了资料不公开、一个已注销、一个封禁。"""
    from app.core.db import SessionLocal
    from app.modules.account.models import User

    s = register(client, "13800099101", "被关注的人")
    fans = {name: register(client, f"1380009920{i}", name)
            for i, name in enumerate(("公开的粉丝", "隐身的粉丝", "注销的粉丝", "封禁的粉丝"))}
    for f in fans.values():
        client.put(f"/api/v1/users/{s['id']}/follow", headers=auth(f))
    client.patch("/api/v1/users/me", json={"privacy": {"profile_public": False}},
                 headers=auth(fans["隐身的粉丝"]))
    db = SessionLocal()
    try:
        db.get(User, fans["注销的粉丝"]["id"]).is_deleted = True
        db.get(User, fans["封禁的粉丝"]["id"]).is_banned = True
        db.commit()
    finally:
        db.close()
    return s, fans


def _names(resp):
    return [i["nickname"] for i in resp.json()["items"]]


def test_cnt023_others_see_only_publicly_listed_followers(client, star):
    """别人看到的粉丝列表里，只有资料公开、未封禁、未注销的人。

    **关注关系本身就是个人信息**：设了资料不公开的人，不该因为他关注了一个
    公开的人，就出现在那个人的粉丝列表里给所有人看。
    """
    s, _fans = star
    visitor = register(client, "13800099301", "路人")
    names = _names(client.get(f"/api/v1/users/{s['id']}/followers", headers=auth(visitor)))
    assert names == ["公开的粉丝"], names


def test_cnt023_the_owner_sees_all_living_followers(client, star):
    """本人看自己的粉丝：看得到设了不公开的人（他选择了关注你），看不到已注销的。"""
    s, _fans = star
    names = set(_names(client.get(f"/api/v1/users/{s['id']}/followers", headers=auth(s))))
    assert "公开的粉丝" in names and "隐身的粉丝" in names
    assert "注销的粉丝" not in names


def test_cnt023_a_private_persons_lists_are_not_visible_to_others(client):
    """资料不公开的人，他的社交圈也不公开——与公开资料页同一判断。"""
    private = register(client, "13800099401", "不公开的人")
    client.patch("/api/v1/users/me", json={"privacy": {"profile_public": False}},
                 headers=auth(private))
    visitor = register(client, "13800099402", "路人")
    for which in ("followers", "following"):
        r = client.get(f"/api/v1/users/{private['id']}/{which}", headers=auth(visitor))
        assert r.status_code == 403, f"{which}：{r.status_code} {r.text}"
        assert client.get(f"/api/v1/users/{private['id']}/{which}",
                          headers=auth(private)).status_code == 200, "本人自己都看不了"


def test_cnt023_list_carries_the_viewers_own_follow_state(client):
    """列表里每个人旁边的按钮要有状态：访问者自己关注了谁。"""
    owner = register(client, "13800099501", "主人")
    a = register(client, "13800099502", "甲")
    b = register(client, "13800099503", "乙")
    viewer = register(client, "13800099504", "访客")
    for u in (a, b):
        client.put(f"/api/v1/users/{u['id']}/follow", headers=auth(owner))
    client.put(f"/api/v1/users/{a['id']}/follow", headers=auth(viewer))

    items = {i["nickname"]: i for i in client.get(
        f"/api/v1/users/{owner['id']}/following", headers=auth(viewer)).json()["items"]}
    assert items["甲"]["viewer_following"] is True
    assert items["乙"]["viewer_following"] is False


def test_cnt023_pagination_does_not_repeat_or_skip(client):
    """游标分页：新的关注在前，翻页不重复、不漏人。"""
    owner = register(client, "13800099601", "主人")
    fans = [register(client, f"138000997{i:02d}", f"粉丝{i}") for i in range(7)]
    for f in fans:
        client.put(f"/api/v1/users/{owner['id']}/follow", headers=auth(f))

    seen, after = [], 0
    for _ in range(5):
        r = client.get(f"/api/v1/users/{owner['id']}/followers",
                       params={"after": after, "limit": 3}, headers=auth(owner)).json()
        seen += [i["nickname"] for i in r["items"]]
        if r["next_cursor"] is None:
            break
        after = r["next_cursor"]
    assert seen == [f"粉丝{i}" for i in reversed(range(7))], seen


def test_cnt023_anonymous_visitors_can_read_public_lists(client):
    """公开的人的列表，未登录也能看（与公开空间同一口径）；按钮状态为 None。"""
    owner = register(client, "13800099701", "公开的人")
    fan = register(client, "13800099702", "粉丝")
    client.put(f"/api/v1/users/{owner['id']}/follow", headers=auth(fan))
    r = client.get(f"/api/v1/users/{owner['id']}/followers")
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["viewer_following"] is None


def test_cnt023_list_responses_match_the_sdk_declarations(client):
    """两个列表接口返回 `_follow_list(...)`（调用而不是字面量），静态扫除读不到它们——
    所以在这里用真实响应与 SDK 声明比一遍（CLI-083 的棘轮因此不涨）。"""
    from tests.test_client_shape_alignment import _assert_inline_shape

    owner = register(client, "13800099801", "主人")
    fan = register(client, "13800099802", "粉丝")
    client.put(f"/api/v1/users/{owner['id']}/follow", headers=auth(fan))
    # 方法名要写成字面量：CLI-083 的扫描靠读这里的字符串来认「谁被真实响应比过」，
    # 传变量它就认不出来（第一版就是这么写的，棘轮照样涨了）
    followers = client.get(f"/api/v1/users/{owner['id']}/followers", headers=auth(owner)).json()
    _assert_inline_shape(followers, "followers")
    assert followers["items"], "列表为空，这条形状断言什么都没比"
    following = client.get(f"/api/v1/users/{fan['id']}/following", headers=auth(owner)).json()
    _assert_inline_shape(following, "following")
    assert following["items"], "列表为空，这条形状断言什么都没比"
