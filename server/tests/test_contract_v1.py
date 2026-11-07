"""05 合约增强：SC-004 多里程碑分期 / SC-007 变更单"""
from .conftest import auth, topup
from .test_task_flow import publish_task


def _matched_contract(client, requester, worker, budget=100000):
    """报名成交但未签署，返回 contract_id 与 task。"""
    topup(client, requester, budget * 2)
    task = publish_task(client, requester, budget_cents=budget, title="装修项目", category="维修")
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    app_id = r.json()["id"]
    contract_id = client.post(
        f"/api/v1/applications/{app_id}/accept", headers=auth(requester)
    ).json()["contract_id"]
    return contract_id, task


def _sign_and_fund(client, requester, worker, contract_id):
    for u in (requester, worker):
        assert client.post(f"/api/v1/contracts/{contract_id}/sign", headers=auth(u)).status_code == 200
    assert client.post(f"/api/v1/contracts/{contract_id}/fund", headers=auth(requester)).status_code == 200


def test_sc004_default_single_milestone(client, requester, worker):
    contract_id, _ = _matched_contract(client, requester, worker)
    c = client.get(f"/api/v1/contracts/{contract_id}", headers=auth(requester)).json()
    assert len(c["milestones"]) == 1 and c["milestones"][0]["amount_cents"] == 100000


def test_sc004_define_milestones_conservation(client, requester, worker):
    contract_id, _ = _matched_contract(client, requester, worker)
    # 金额不守恒被拒
    r = client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 1}]},
        headers=auth(requester),
    )
    assert r.status_code == 400
    # 执行者不能定义
    r = client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "全部", "amount_cents": 100000}]},
        headers=auth(worker),
    )
    assert r.status_code == 400
    # 三期守恒成功
    r = client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [
            {"title": "拆旧", "amount_cents": 20000},
            {"title": "硬装", "amount_cents": 50000},
            {"title": "收尾", "amount_cents": 30000},
        ]},
        headers=auth(requester),
    )
    assert r.status_code == 200 and len(r.json()["milestones"]) == 3


def test_sc004_staged_delivery_and_release(client, requester, worker):
    contract_id, task = _matched_contract(client, requester, worker)
    client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 40000}, {"title": "尾期", "amount_cents": 60000}]},
        headers=auth(requester),
    )
    _sign_and_fund(client, requester, worker, contract_id)
    # 签署后不能重定义里程碑
    r = client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "x", "amount_cents": 100000}]},
        headers=auth(requester),
    )
    assert r.status_code == 409
    # 未交付不能放款
    r = client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept", headers=auth(requester))
    assert r.status_code == 409
    # 首期交付 → 放款：执行者收到 40000-8%
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept", headers=auth(requester))
    assert r.status_code == 200
    assert r.json()["released_cents"] == 40000 and r.json()["status"] == "funded"
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["available_cents"] == 40000 - 40000 * 800 // 10000
    # 尾期交付+放款 → 合约 released、任务自动闭环
    client.post(f"/api/v1/contracts/{contract_id}/milestones/2/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/contracts/{contract_id}/milestones/2/accept", headers=auth(requester))
    assert r.json()["status"] == "released"
    detail = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    assert detail["status"] == "completed"
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 0


def test_sc004_partial_release_then_cancel_uses_remaining(client, requester, worker):
    """部分放款后取消：规则只作用于剩余托管额。"""
    contract_id, task = _matched_contract(client, requester, worker)
    client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 40000}, {"title": "尾期", "amount_cents": 60000}]},
        headers=auth(requester),
    )
    _sign_and_fund(client, requester, worker, contract_id)
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/deliver", headers=auth(worker))
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept", headers=auth(requester))
    # 发布者取消：补偿 = 剩余 60000 的 20%
    r = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(requester))
    assert r.json()["executor_compensation_cents"] == 12000
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 0
    assert wr["available_cents"] == 200000 - 40000 - 12000  # 充值-首期-补偿


def test_sc007_change_order_increase_and_decrease(client, requester, worker):
    contract_id, task = _matched_contract(client, requester, worker)
    _sign_and_fund(client, requester, worker, contract_id)
    # 执行者提出加价到 120000
    r = client.post(
        f"/api/v1/contracts/{contract_id}/change-orders",
        json={"new_amount_cents": 120000, "reason": "增加阳台施工"},
        headers=auth(worker),
    )
    assert r.status_code == 201, r.text
    order_id = r.json()["id"]
    # 提案方不能自己接受
    r = client.post(f"/api/v1/contracts/{contract_id}/change-orders/{order_id}/accept", headers=auth(worker))
    assert r.status_code == 400
    # 有 pending 变更单时不能再提
    r = client.post(
        f"/api/v1/contracts/{contract_id}/change-orders",
        json={"new_amount_cents": 90000}, headers=auth(requester),
    )
    assert r.status_code == 409
    # 发布者接受 → 追加托管 20000、版本+1、任务预算同步
    r = client.post(f"/api/v1/contracts/{contract_id}/change-orders/{order_id}/accept", headers=auth(requester))
    c = r.json()
    assert c["amount_cents"] == 120000 and c["version"] == 2
    assert c["milestones"][0]["amount_cents"] == 120000
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 120000
    detail = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    assert detail["budget_cents"] == 120000
    # 再来一次减价到 110000 → 退差额
    r = client.post(
        f"/api/v1/contracts/{contract_id}/change-orders",
        json={"new_amount_cents": 110000, "reason": "取消部分项目"},
        headers=auth(requester),
    )
    order2 = r.json()["id"]
    client.post(f"/api/v1/contracts/{contract_id}/change-orders/{order2}/accept", headers=auth(worker))
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 110000


def test_sc007_change_rejected_after_release_started(client, requester, worker):
    contract_id, _ = _matched_contract(client, requester, worker)
    client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 40000}, {"title": "尾期", "amount_cents": 60000}]},
        headers=auth(requester),
    )
    _sign_and_fund(client, requester, worker, contract_id)
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/deliver", headers=auth(worker))
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept", headers=auth(requester))
    r = client.post(
        f"/api/v1/contracts/{contract_id}/change-orders",
        json={"new_amount_cents": 200000}, headers=auth(worker),
    )
    assert r.status_code == 409  # 已开始放款不可整体改价


# ---------- SC-013 整单验收与分期并存：把设计意图钉下来 ----------
def test_sc013_whole_order_release_pays_only_the_remaining(client, requester, worker):
    """分期合约上整单验收，放的是**剩余**托管，不重复付已放的期。

    `release()` 的 docstring 写着「整体验收放款：放出全部剩余托管
    （已分期放款的部分不重复）」——也就是说这条路**是有意设计的**，
    不是漏掉了分期判断。V113 的探针发现它存在时，72 号台账记成
    「没有测试说明这是不是设计」（SC-013）：**「没人说过」与「有意为之」
    看起来一样**，而看起来一样的东西迟早会被人当成缺陷改掉。

    这一条就是那句话。它同时钉住两件事：
    - 已放过的期不会被再付一次（否则就是平台多付钱）；
    - 剩下的期**会**被一次付掉——这是整单验收的含义，不是 bug。
    """
    contract_id, task = _matched_contract(client, requester, worker)
    client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 40000},
                        {"title": "尾期", "amount_cents": 60000}]},
        headers=auth(requester),
    )
    _sign_and_fund(client, requester, worker, contract_id)

    c = client.get(f"/api/v1/contracts/{contract_id}", headers=auth(requester)).json()
    first = c["milestones"][0]
    # 先走分期：交付并放款第一期
    assert client.post(f"/api/v1/contracts/{contract_id}/milestones/{first['idx']}/deliver",
                       headers=auth(worker)).status_code == 200
    assert client.post(f"/api/v1/contracts/{contract_id}/milestones/{first['idx']}/accept",
                       headers=auth(requester)).status_code == 200

    before = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]

    # 再走整单：执行方整单交付、发布方整单验收
    assert client.post(f"/api/v1/tasks/{task['id']}/deliver",
                       headers=auth(worker)).status_code == 200
    assert client.post(f"/api/v1/tasks/{task['id']}/accept-delivery",
                       headers=auth(requester)).status_code == 200

    after = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    c2 = client.get(f"/api/v1/contracts/{contract_id}", headers=auth(requester)).json()
    # 只放了尾期的 60000（扣佣金与代扣后到账），不是把首期再付一遍
    assert c2["released_cents"] == 100000, f"释放总额应等于合约金额：{c2['released_cents']}"
    gained = after - before
    assert 0 < gained < 60000, f"这一步到账应在尾期金额之内（扣佣金与税）：{gained}"


def test_sc013_undelivered_stages_are_paid_by_whole_order_acceptance(client, requester, worker):
    """整单验收**会**付掉没交付的期——这是它的含义，而不是漏判。

    为什么要专门钉这一条：分期验收那条路有 `milestone.status != "delivered"
    → 拒绝` 的保护，整单这条路没有。两条路的保护强度不同，**而这是有意的**：
    整单验收是发布方说「我认了，全付」，那是他的钱和他的判断。

    服务端这条路本身是**自洽的**：放款之后它把所有未放的期一并标成
    `released`，不会留下「钱付了、期还是 pending」那种自相矛盾的数据。
    （我原本以为会留下 pending，是测试把我纠正了——写断言之前的猜测
    不如跑一遍。）

    真正缺的因此只剩**客户端的决定点**（见 93 号 spec）：按钮上不能只写
    「验收通过（放款）」。发布方当初定三期，正是为了不一次付完；
    在一个不提里程碑的按钮上一次放掉全部，他失去的是自己设置的那道保护。
    所以两端在还有未放期时必须说清「这一下会放掉剩余 N 期、共 X 元」。
    """
    contract_id, task = _matched_contract(client, requester, worker)
    client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "一期", "amount_cents": 30000},
                        {"title": "二期", "amount_cents": 30000},
                        {"title": "三期", "amount_cents": 40000}]},
        headers=auth(requester),
    )
    _sign_and_fund(client, requester, worker, contract_id)
    # 一期都没交付就整单交付 + 整单验收
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    assert client.post(f"/api/v1/tasks/{task['id']}/accept-delivery",
                       headers=auth(requester)).status_code == 200

    c = client.get(f"/api/v1/contracts/{contract_id}", headers=auth(requester)).json()
    assert c["released_cents"] == 100000
    # 三期一并标成 released：服务端不留「钱付了、期还 pending」的矛盾数据
    assert [m["status"] for m in c["milestones"]] == ["released"] * 3
