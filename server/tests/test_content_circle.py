"""08 内容 + 09 圈层：CNT-001/006/010/020/021, CIR-001~007, TASK-008"""
from .conftest import auth, register, topup, verify_user


# ---------- 内容 ----------
def test_cnt001_post_and_blog_rules(client, requester):
    r = client.post("/api/v1/contents", json={"kind": "post", "body": "今天完成了一单保洁，客户很满意"},
                    headers=auth(requester))
    assert r.status_code == 201
    # 博客必须有标题
    r = client.post("/api/v1/contents", json={"kind": "blog", "body": "正文"}, headers=auth(requester))
    assert r.status_code == 400
    r = client.post("/api/v1/contents",
                    json={"kind": "blog", "title": "保洁入行指南", "body": "第一章…", "tags": ["保洁"]},
                    headers=auth(requester))
    assert r.status_code == 201


def test_cnt006_content_machine_review(client, requester):
    r = client.post("/api/v1/contents", json={"body": "有偿刷单联系我"}, headers=auth(requester))
    assert r.status_code == 400


def test_cnt020_like_toggle_and_comments(client, requester, worker):
    c = client.post("/api/v1/contents", json={"body": "接单日记"}, headers=auth(requester)).json()
    r = client.post(f"/api/v1/contents/{c['id']}/like", headers=auth(worker))
    assert r.json() == {"liked": True, "like_count": 1}
    r = client.post(f"/api/v1/contents/{c['id']}/like", headers=auth(worker))
    assert r.json()["liked"] is False  # 再点取消
    client.post(f"/api/v1/contents/{c['id']}/comments", json={"body": "写得好"}, headers=auth(worker))
    comments = client.get(f"/api/v1/contents/{c['id']}/comments").json()
    assert comments[0]["body"] == "写得好"
    # 评论同样过机审
    r = client.post(f"/api/v1/contents/{c['id']}/comments", json={"body": "来赌博"}, headers=auth(worker))
    assert r.status_code == 400


def test_cnt010_021_follow_and_following_feed(client, requester, worker):
    client.post("/api/v1/contents", json={"body": "A 的动态"}, headers=auth(requester))
    # worker 未关注 → following 流为空
    feed = client.get("/api/v1/feed", params={"scope": "following"}, headers=auth(worker)).json()
    assert feed == []
    # V117 起关注是幂等的 PUT，不再是 POST toggle
    r = client.put(f"/api/v1/users/{requester['id']}/follow", headers=auth(worker))
    assert r.json()["following"] is True
    feed = client.get("/api/v1/feed", params={"scope": "following"}, headers=auth(worker)).json()
    assert len(feed) == 1 and feed[0]["body"] == "A 的动态"
    stats = client.get(f"/api/v1/users/{requester['id']}/follow-stats").json()
    assert stats["followers"] == 1
    # 最新流可见公开内容
    latest = client.get("/api/v1/feed", headers=auth(worker)).json()
    assert any(c["body"] == "A 的动态" for c in latest)


def test_cnt005_linked_service_entry(client, requester):
    c = client.post(
        "/api/v1/contents",
        json={"body": "保洁前后对比图", "linked_category": "保洁", "tags": ["保洁"]},
        headers=auth(requester),
    ).json()
    assert c["linked_category"] == "保洁"  # 前端据此渲染"找我做同款"


# ---------- 圈层 ----------
def _circle(client, user, **overrides):
    payload = {"name": "上海保洁互助圈", "kind": "skill", "skill_tag": "保洁", **overrides}
    r = client.post("/api/v1/circles", json=payload, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def test_cir001_create_with_group_chat(client, requester):
    c = _circle(client, requester)
    assert c["member_count"] == 1 and c["my_role"] == "owner"
    assert c["conversation_id"]  # CIR-006 自带群聊
    # 能力圈必须绑技能
    r = client.post("/api/v1/circles", json={"name": "X圈", "kind": "skill"}, headers=auth(requester))
    assert r.status_code == 400


def test_cir003_join_open_vs_approval_and_credit_gate(client, requester, worker):
    open_c = _circle(client, requester)
    r = client.post(f"/api/v1/circles/{open_c['id']}/join", headers=auth(worker))
    assert r.json()["status"] == "active"
    # approval 制 + 信用门槛
    gated = _circle(client, requester, name="高手圈", join_policy="approval", min_credit=150)
    r = client.post(f"/api/v1/circles/{gated['id']}/join", headers=auth(worker))
    assert r.status_code == 403  # 信用不足
    normal = _circle(client, requester, name="审核圈", join_policy="approval")
    r = client.post(f"/api/v1/circles/{normal['id']}/join", headers=auth(worker))
    assert r.json()["status"] == "pending"
    # 圈主审批
    r = client.post(f"/api/v1/circles/{normal['id']}/members/{worker['id']}/approve", headers=auth(requester))
    assert r.json()["status"] == "active"
    members = client.get(f"/api/v1/circles/{normal['id']}/members", headers=auth(requester)).json()
    assert len(members) == 2


def test_cir004_circle_feed_members_only(client, requester, worker):
    c = _circle(client, requester)
    client.post("/api/v1/contents", json={"body": "圈内专享攻略", "circle_id": c["id"]}, headers=auth(requester))
    # 非成员：发帖与看帖都被拒
    outsider = register(client, "13400000001")
    r = client.post("/api/v1/contents", json={"body": "蹭帖", "circle_id": c["id"]}, headers=auth(outsider))
    assert r.status_code == 403
    r = client.get(f"/api/v1/circles/{c['id']}/feed", headers=auth(outsider))
    assert r.status_code == 403
    # 成员可见，且公共 feed 不含圈层内容
    client.post(f"/api/v1/circles/{c['id']}/join", headers=auth(worker))
    feed = client.get(f"/api/v1/circles/{c['id']}/feed", headers=auth(worker)).json()
    assert len(feed) == 1
    public = client.get("/api/v1/feed", headers=auth(worker)).json()
    assert all(item["body"] != "圈内专享攻略" for item in public)


def test_cir005_circle_task_board_hidden_from_square(client, requester, worker):
    c = _circle(client, requester)
    client.post(f"/api/v1/circles/{c['id']}/join", headers=auth(worker))
    r = client.post(
        "/api/v1/tasks",
        json={"ip_assignment": "assign", "title": "圈内保洁单", "category": "保洁", "budget_cents": 10000,
              "is_remote": True, "visibility": "circle", "circle_id": c["id"]},
        headers=auth(requester),
    )
    assert r.status_code == 201, r.text
    task = r.json()
    # 广场不可见
    square = client.get("/api/v1/tasks").json()
    assert all(t["id"] != task["id"] for t in square)
    # 圈层任务板可见
    board = client.get(f"/api/v1/circles/{c['id']}/tasks", headers=auth(worker)).json()
    assert board[0]["id"] == task["id"]
    # 非成员发圈层任务被拒
    outsider = register(client, "13400000002")
    verify_user(client, outsider, "赵六")
    r = client.post(
        "/api/v1/tasks",
        json={"ip_assignment": "assign", "title": "蹭圈任务", "category": "保洁", "budget_cents": 10000,
              "is_remote": True, "visibility": "circle", "circle_id": c["id"]},
        headers=auth(outsider),
    )
    assert r.status_code == 403


def test_cir006_circle_group_chat_syncs_membership(client, requester, worker):
    c = _circle(client, requester)
    client.post(f"/api/v1/circles/{c['id']}/join", headers=auth(worker))
    r = client.post(
        f"/api/v1/conversations/{c['conversation_id']}/messages",
        json={"content": "欢迎新成员"}, headers=auth(requester),
    )
    assert r.status_code == 201
    msgs = client.get(f"/api/v1/conversations/{c['conversation_id']}/messages", headers=auth(worker)).json()
    assert msgs[0]["content"] == "欢迎新成员"
    # 移出成员后群聊不可见（CIR-007）
    client.post(f"/api/v1/circles/{c['id']}/members/{worker['id']}/remove", headers=auth(requester))
    r = client.get(f"/api/v1/conversations/{c['conversation_id']}/messages", headers=auth(worker))
    assert r.status_code == 403


def test_cir002_recommendation_by_skill_and_city(client, requester, worker):
    _circle(client, requester)  # 保洁能力圈
    _circle(client, requester, name="北京跑腿圈", kind="local", city="北京", skill_tag="")
    client.patch("/api/v1/users/me", json={"skills": ["保洁"], "city": "上海"}, headers=auth(worker))
    recs = client.get("/api/v1/circles", params={"recommended": True}, headers=auth(worker)).json()
    names = [c["name"] for c in recs]
    assert "上海保洁互助圈" in names and "北京跑腿圈" not in names


# ---------- CNT-022 关注要幂等，而且状态要读得到 ----------
def test_cnt022_follow_is_idempotent_so_a_retry_does_not_undo_it(client, requester, worker):
    """重复关注仍然是已关注。

    改造前这里是一个 `POST` toggle：手机上双击一下、或者弱网下客户端自动
    重试一次，用户刚关注的人就被**取消关注**了——而他看到的是自己点了
    两次「关注」。探针实测：第一次 `{"following": True}`，第二次
    `{"following": False}`。
    """
    target = requester["id"]
    for _ in range(3):
        r = client.put(f"/api/v1/users/{target}/follow", headers=auth(worker))
        assert r.status_code == 200 and r.json()["following"] is True

    stats = client.get(f"/api/v1/users/{target}/follow-stats").json()
    # 唯一约束挡住了重复行；真正要钉的是**计数没有被点成 3**
    assert stats["followers"] == 1

    for _ in range(3):
        r = client.delete(f"/api/v1/users/{target}/follow", headers=auth(worker))
        assert r.status_code == 200 and r.json()["following"] is False
    assert client.get(f"/api/v1/users/{target}/follow-stats").json()["followers"] == 0


def test_cnt022_the_old_toggle_is_gone(client, requester, worker):
    """旧的 `POST` toggle 必须不存在。

    留着它比删掉更糟：两个动作并存时，下一个人会从两个里挑一个用，
    而挑到 toggle 的那一半界面会继续出现「想关注却取消了」。
    """
    r = client.post(f"/api/v1/users/{requester['id']}/follow", headers=auth(worker))
    assert r.status_code == 405, "POST 还能用，说明 toggle 没真正下线"


def test_cnt022_viewer_can_read_whether_they_follow(client, requester, worker):
    """「我是否已关注他」必须读得到——没有它，按钮只能猜。

    匿名时是 `None` 而**不是 `False`**：「没登录所以不知道」与「登录了但
    没关注」是两件事，合成一个 `False` 会给游客画一个点下去才发现要先
    登录的按钮。
    """
    target = requester["id"]
    anon = client.get(f"/api/v1/users/{target}/follow-stats").json()
    assert anon["viewer_following"] is None

    before = client.get(f"/api/v1/users/{target}/follow-stats", headers=auth(worker)).json()
    assert before["viewer_following"] is False
    client.put(f"/api/v1/users/{target}/follow", headers=auth(worker))
    after = client.get(f"/api/v1/users/{target}/follow-stats", headers=auth(worker)).json()
    assert after["viewer_following"] is True


def test_cnt022_stats_following_is_a_count_not_my_state(client, requester, worker):
    """`following` 是计数，`viewer_following` 才是我的状态——同名不同义是个陷阱。

    这一条钉的是**键名**：响应里既有「他关注了多少人」的 `following`，
    又有「我是否已关注他」的布尔。客户端把前者当后者读时，
    计数非零就会永远显示「已关注」，而计数为零时又显示「关注」——
    一个随别人关注了几个人而变化的按钮。
    """
    third = register(client, "13900052001", "丙")
    verify_user(client, third, "王丙")
    # requester 关注了 1 个人，而 worker 没有关注 requester
    client.put(f"/api/v1/users/{third['id']}/follow", headers=auth(requester))

    stats = client.get(f"/api/v1/users/{requester['id']}/follow-stats",
                       headers=auth(worker)).json()
    assert stats["following"] == 1, "这个键是「他关注了多少人」"
    assert stats["viewer_following"] is False, "而我并没有关注他"


def test_cnt022_cannot_follow_yourself_either_way(client, requester):
    """关注自己两个动作都要拒——只拦一个等于没拦。"""
    me = requester["id"]
    assert client.put(f"/api/v1/users/{me}/follow", headers=auth(requester)).status_code == 400
    assert client.delete(f"/api/v1/users/{me}/follow", headers=auth(requester)).status_code == 400
    # 自己的页面上不该出现关注按钮，所以状态是 None 而不是 False
    stats = client.get(f"/api/v1/users/{me}/follow-stats", headers=auth(requester)).json()
    assert stats["viewer_following"] is None


def test_cnt022_optional_auth_never_grants_anything(client, requester, worker):
    """可选鉴权只用来认人，不许用来放权。

    `get_optional_user` 把「token 无效 / 会话吊销 / 账号被封」统一降级成匿名。
    这在只读的公开接口上是对的，但**绝不能**让它变成一条绕过鉴权的路：
    坏 token 读 follow-stats 应当拿到匿名结果，而写动作必须照样被拒。
    """
    bad = {"Authorization": "Bearer not-a-real-token"}
    stats = client.get(f"/api/v1/users/{requester['id']}/follow-stats", headers=bad)
    assert stats.status_code == 200 and stats.json()["viewer_following"] is None
    # 同一个坏 token 去写，必须 4xx——降级成匿名不等于放进来
    assert client.put(f"/api/v1/users/{requester['id']}/follow", headers=bad).status_code >= 400
