"""端到端主闭环（01 号 spec 第 3 节）：

注册实名 → 发布母任务 → AI 分解 → 确认生成子任务树 → 按依赖发布
→ 推荐人选 → 报名成交 → 合约双签托管 → IM 沟通 → 执行交付
→ 验收放款(抽佣) → 后继子任务自动发布 → 全部闭环 → 母任务验收
→ 双向评价 → 信用更新 → 经验入库 → 估价参考反哺
"""
from .conftest import auth, register, topup, verify_user


def _skills(client, user, skills, lat=31.23, lng=121.47):
    client.patch(
        "/api/v1/users/me",
        json={"skills": skills, "lat": lat, "lng": lng, "city": "上海"},
        headers=auth(user),
    )


def test_full_platform_closed_loop(client):
    # ---- 1. 三个角色：发布者 + 两名执行者 ----
    boss = register(client, "13811110001", "创业者老王")
    verify_user(client, boss, "王老板")
    designer = register(client, "13811110002", "设计师小美")
    verify_user(client, designer, "刘小美")
    _skills(client, designer, ["产品设计", "UI设计"])
    coder = register(client, "13811110003", "程序员小刚")
    verify_user(client, coder, "陈小刚")
    _skills(client, coder, ["前端开发", "后端开发", "测试"])
    topup(client, boss, 2000000)  # 2 万元

    # ---- 2. 发布母任务（项目型，不直接发布，先分解） ----
    r = client.post(
        "/api/v1/tasks",
        json={
            "title": "奶茶店小程序", "description": "点单小程序含后台管理系统",
            "category": "软件开发", "task_type": "project",
            "budget_cents": 1000000, "is_remote": True, "city": "上海",
            "publish_now": False,
        },
        headers=auth(boss),
    )
    parent = r.json()

    # ---- 3. AI 分解（模板命中）→ 编辑 → 确认 ----
    dec = client.post(f"/api/v1/tasks/{parent['id']}/decompositions", headers=auth(boss)).json()
    assert dec["source"] == "seed_template" and len(dec["items"]) == 5
    # 用户把 5 步精简为 2 步（人机协同：AI 只出草稿）
    items = [
        {"title": "设计稿", "description": "原型+UI", "required_skills": ["UI设计"],
         "budget_cents": 300000, "depends_on_idx": []},
        {"title": "开发上线", "description": "前后端+部署", "required_skills": ["前端开发"],
         "budget_cents": 700000, "depends_on_idx": [0]},
    ]
    client.patch(f"/api/v1/decompositions/{dec['id']}", json={"items": items}, headers=auth(boss))
    children = client.post(
        f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(boss)
    ).json()["children"]
    design_task, dev_task = children
    assert design_task["status"] == "published" and dev_task["status"] == "draft"

    # ---- 4. AI 推荐人选：设计任务首推设计师 ----
    recs = client.get(
        f"/api/v1/tasks/{design_task['id']}/recommendations", headers=auth(boss)
    ).json()
    assert recs[0]["user_id"] == designer["id"]

    # ---- 5. 设计师报名 → 成交 → 合约双签 → 托管 ----
    app_id = client.post(
        f"/api/v1/tasks/{design_task['id']}/applications",
        json={"message": "作品集见主页"}, headers=auth(designer),
    ).json()["id"]
    contract_id = client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(boss)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{contract_id}/sign", headers=auth(boss))
    client.post(f"/api/v1/contracts/{contract_id}/sign", headers=auth(designer))
    client.post(f"/api/v1/contracts/{contract_id}/fund", headers=auth(boss))
    assert client.get("/api/v1/wallet", headers=auth(boss)).json()["escrow_cents"] == 300000

    # ---- 6. 任务会话沟通 + 进度 + 交付 + 验收放款 ----
    conv = [c for c in client.get("/api/v1/conversations", headers=auth(designer)).json()
            if c["task_id"] == design_task["id"]][0]
    client.post(f"/api/v1/conversations/{conv['id']}/messages",
                json={"content": "初稿周三给你"}, headers=auth(designer))
    client.post(f"/api/v1/tasks/{design_task['id']}/progress",
                json={"content": "原型完成"}, headers=auth(designer))
    client.post(f"/api/v1/tasks/{design_task['id']}/deliver", headers=auth(designer))
    client.post(f"/api/v1/tasks/{design_task['id']}/accept-delivery", headers=auth(boss))
    assert client.get("/api/v1/wallet", headers=auth(designer)).json()["available_cents"] == 276000  # -8%

    # ---- 7. AI-DEC-020：开发子任务自动发布，推进闭环 ----
    assert client.get(f"/api/v1/tasks/{dev_task['id']}", headers=auth(boss)).json()["status"] == "published"
    app_id = client.post(
        f"/api/v1/tasks/{dev_task['id']}/applications", json={}, headers=auth(coder)
    ).json()["id"]
    contract_id = client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(boss)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{contract_id}/sign", headers=auth(boss))
    client.post(f"/api/v1/contracts/{contract_id}/sign", headers=auth(coder))
    client.post(f"/api/v1/contracts/{contract_id}/fund", headers=auth(boss))
    client.post(f"/api/v1/tasks/{dev_task['id']}/deliver", headers=auth(coder))
    client.post(f"/api/v1/tasks/{dev_task['id']}/accept-delivery", headers=auth(boss))

    # ---- 8. 母任务驾驶舱：100%，可整体收口 ----
    tree = client.get(f"/api/v1/tasks/{parent['id']}/tree", headers=auth(boss)).json()
    assert tree["progress_pct"] == 100.0 and tree["all_children_completed"] is True

    # ---- 9. 双向评价 → 信用/评分更新 ----
    client.post(f"/api/v1/tasks/{design_task['id']}/reviews", json={"stars": 5}, headers=auth(boss))
    client.post(f"/api/v1/tasks/{design_task['id']}/reviews", json={"stars": 5}, headers=auth(designer))
    prof = client.get(f"/api/v1/users/{designer['id']}").json()
    assert prof["tasks_completed"] == 1 and prof["credit_score"] > 100 and prof["rating_avg"] == 5.0

    # ---- 10. 知识库飞轮：子任务经验卡 + 估价参考可查 ----
    ref = client.get("/api/v1/knowledge/price-reference", params={"category": "软件开发"}).json()
    assert ref["sample_size"] >= 2  # 两个子任务闭环入库
    cards = client.get("/api/v1/knowledge/cards", params={"category": "软件开发"}).json()
    assert len(cards) >= 2

    # ---- 11. 平台佣金入账（SC-009 分账） ----
    from app.core.db import SessionLocal
    from app.modules.wallet.service import PLATFORM_USER_ID, get_or_create

    with SessionLocal() as db:
        platform = get_or_create(db, PLATFORM_USER_ID)
        assert platform.available_cents == (300000 + 700000) * 800 // 10000

    # ---- 12. 资金守恒审计：老王支出 = 设计师+程序员收入 + 平台佣金 ----
    boss_w = client.get("/api/v1/wallet", headers=auth(boss)).json()
    designer_w = client.get("/api/v1/wallet", headers=auth(designer)).json()
    coder_w = client.get("/api/v1/wallet", headers=auth(coder)).json()
    total = boss_w["available_cents"] + designer_w["available_cents"] + coder_w["available_cents"]
    assert total + 80000 == 2000000  # 佣金 8 万分，其余在三方钱包，分毫不差
