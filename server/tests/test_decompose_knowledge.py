"""04 AI 分解 + 06 知识库：AI-DEC-010/011/020/030, TASK-036, KB-001/020/021"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund

PROJECT = {
    "title": "公司官网建设",
    "description": "响应式官网，含 CMS 后台",
    "category": "软件开发",
    "task_type": "project",
    "budget_cents": 1000000,
    "is_remote": True,
    "city": "上海",
    "publish_now": False,
}


def _propose(client, user, task_overrides=None):
    r = client.post("/api/v1/tasks", json={**PROJECT, **(task_overrides or {})}, headers=auth(user))
    assert r.status_code == 201, r.text
    task = r.json()
    r = client.post(f"/api/v1/tasks/{task['id']}/decompositions", headers=auth(user))
    assert r.status_code == 201, r.text
    return task, r.json()


def test_aidec010_template_decomposition_budget_conserved(client, requester):
    task, dec = _propose(client, requester)
    assert dec["source"] == "seed_template"
    assert len(dec["items"]) == 5  # 软件开发模板 5 阶段
    assert sum(i["budget_cents"] for i in dec["items"]) == PROJECT["budget_cents"]  # 预算守恒
    # DAG：联调测试依赖前端+后端
    assert dec["items"][4]["depends_on_idx"] == [2, 3]


def test_aidec011_edit_rejects_cycle_and_overbudget(client, requester):
    _task, dec = _propose(client, requester)
    # 依赖环被拒
    bad = [
        {"title": "A", "budget_cents": 100, "depends_on_idx": [1]},
        {"title": "B", "budget_cents": 100, "depends_on_idx": [0]},
    ]
    r = client.patch(f"/api/v1/decompositions/{dec['id']}", json={"items": bad}, headers=auth(requester))
    assert r.status_code == 400
    # 超预算被拒（AI-DEC-030）
    over = [{"title": "A", "budget_cents": 2000000, "depends_on_idx": []}]
    r = client.patch(f"/api/v1/decompositions/{dec['id']}", json={"items": over}, headers=auth(requester))
    assert r.status_code == 400


def test_aidec020_confirm_publishes_dag_in_order(client, requester):
    _task, dec = _propose(client, requester)
    r = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    assert r.status_code == 200, r.text
    children = r.json()["children"]
    # 无前置依赖的（需求梳理、后端依赖它所以不算）立即发布，其余 draft
    statuses = {c["title"].split(" - ")[1]: c["status"] for c in children}
    assert statuses["需求梳理与原型设计"] == "published"
    assert statuses["UI 视觉设计"] == "draft"
    assert statuses["联调测试与上线"] == "draft"


def test_tree_progress_and_auto_publish_successors(client, requester, worker):
    """子任务完成 → 后继自动发布 → 母任务进度聚合（TASK-036）。"""
    topup(client, requester, 2000000)
    task, dec = _propose(client, requester)
    # 简化为两步串行，便于走完整闭环
    items = [
        {"title": "第一步：设计", "budget_cents": 400000, "required_skills": [], "depends_on_idx": []},
        {"title": "第二步：实施", "budget_cents": 600000, "required_skills": [], "depends_on_idx": [0]},
    ]
    client.patch(f"/api/v1/decompositions/{dec['id']}", json={"items": items}, headers=auth(requester))
    r = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    step1, step2 = r.json()["children"]
    assert step1["status"] == "published" and step2["status"] == "draft"

    # 完成第一步
    match_and_fund(client, requester, worker, step1)
    client.post(f"/api/v1/tasks/{step1['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{step1['id']}/accept-delivery", headers=auth(requester))

    # AI-DEC-020：第二步自动发布
    detail = client.get(f"/api/v1/tasks/{step2['id']}", headers=auth(requester)).json()
    assert detail["status"] == "published"

    # 驾驶舱进度：400000/1000000 = 40%
    tree = client.get(f"/api/v1/tasks/{task['id']}/tree", headers=auth(requester)).json()
    assert tree["progress_pct"] == 40.0
    assert tree["all_children_completed"] is False


def test_kb001_completed_task_creates_knowledge_card_and_price_ref(client, requester, worker):
    """闭环 → 经验卡入库 → 估价参考可查（KB-001/021 数据飞轮）。"""
    topup(client, requester, 100000)
    r = client.post(
        "/api/v1/tasks",
        json={
            "title": "办公室保洁", "category": "保洁", "budget_cents": 30000,
            "city": "上海", "lat": 31.2, "lng": 121.4, "address_hint": "浦东",
        },
        headers=auth(requester),
    )
    task = r.json()
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    ref = client.get("/api/v1/knowledge/price-reference", params={"category": "保洁"}).json()
    assert ref["sample_size"] == 1 and ref["p50_cents"] == 30000
    cards = client.get("/api/v1/knowledge/cards", params={"category": "保洁"}).json()
    assert cards[0]["outcome"] == "completed"


def test_kb021_empty_category_returns_honest_no_data(client):
    ref = client.get("/api/v1/knowledge/price-reference", params={"category": "不存在类目"}).json()
    assert ref["sample_size"] == 0 and "message" in ref  # 不编造单点值
