"""SC-007 变更单：三层都缺，不只是缺个按钮（70 号 spec）。

服务端做得很完整——改价、差额**多退少补**、版本 +1、任务预算同步，
还有多轮随机改价的资金守恒测试。而整条路对用户不存在，
而且缺的**不只是按钮**：

| 层 | 改造前 |
|---|---|
| 提案 / 接受 / 拒绝的入口 | 两端都没有 |
| **列出**变更单的接口 | **服务端根本没有** —— 对方拿不到 order_id |
| 通知对方有变更单待处理 | 没有 |

三层是叠在一起的：**只补按钮不补列表，按钮点不了；
补了列表不补通知，没人知道该去看。**

没有变更单的实际后果：任务范围一变，双方只剩取消（按违约规则算补偿）
或发起纠纷——**一件本该是「好商量」的事，产品逼着他们走对抗路径。**
"""
from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from tests.conftest import auth, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task


def notices(user_id: int, title: str | None = None) -> list[Notification]:
    with SessionLocal() as db:
        q = db.query(Notification).filter(Notification.user_id == user_id)
        if title:
            q = q.filter(Notification.title == title)
        return q.all()


def _funded(client, requester, phone: str):
    worker = register(client, phone, "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 300000)
    topup(client, worker, 100000)
    task = publish_task(client, requester)
    contract_id = match_and_fund(client, requester, worker, task)
    return worker, task, contract_id


# --------------------------------------------------- SC-007 列表接口
def test_sc007_counterparty_can_list_the_change_order(client, requester):
    """改造前**没有这个接口**：提案建得出来，对方拿不到 `order_id`。"""
    worker, _task, cid = _funded(client, requester, "13800096001")
    r = client.post(f"/api/v1/contracts/{cid}/change-orders",
                    json={"new_amount_cents": 30000, "reason": "加了两个房间"},
                    headers=auth(requester))
    assert r.status_code == 201, r.text

    rows = client.get(f"/api/v1/contracts/{cid}/change-orders", headers=auth(worker)).json()
    assert len(rows) == 1, "对方列不出变更单"
    assert rows[0]["new_amount_cents"] == 30000
    assert rows[0]["reason"] == "加了两个房间", "事由是对方判断要不要接受的依据"


def test_sc007_can_decide_matches_the_server_admission(client, requester):
    """`can_decide` 与 `accept_change` 的准入同源：提案人自己不能接受。

    客户端**不重写**这个判断——第二份实现必然抄漏（UI-075 / TEAM-021 同一条）。
    """
    worker, _task, cid = _funded(client, requester, "13800096010")
    oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                      json={"new_amount_cents": 30000, "reason": "加两间"},
                      headers=auth(requester)).json()["id"]

    mine = client.get(f"/api/v1/contracts/{cid}/change-orders", headers=auth(requester)).json()
    theirs = client.get(f"/api/v1/contracts/{cid}/change-orders", headers=auth(worker)).json()
    assert mine[0]["can_decide"] is False, "提案人自己看到了「可裁决」"
    assert theirs[0]["can_decide"] is True

    # 判断与真实准入一致：提案人真的接受不了
    bad = client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(requester))
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "not_counterparty"


# --------------------------------------------------- SC-007 通知
def test_sc007_counterparty_is_told_a_change_order_is_waiting(client, requester):
    """没有通知，对方就不知道该去合约页看一眼。"""
    worker, task, cid = _funded(client, requester, "13800096020")
    client.post(f"/api/v1/contracts/{cid}/change-orders",
                json={"new_amount_cents": 30000, "reason": "加了两个房间"},
                headers=auth(requester))

    got = notices(worker["id"], "收到合约变更单")
    assert got, "对方没被告知有变更单待处理"
    body = got[-1].body
    assert "¥300.00" in body, f"通知里没说改成多少钱：{body}"
    assert "加了两个房间" in body, "通知里没带上事由"
    assert task["title"] in body


def test_sc007_proposer_is_told_the_outcome(client, requester):
    """提案人是等着这个答复才能决定下一步的人——接受与拒绝都要告诉他。"""
    worker, _task, cid = _funded(client, requester, "13800096030")
    oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                      json={"new_amount_cents": 30000, "reason": "加两间"},
                      headers=auth(requester)).json()["id"]
    client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))

    got = notices(requester["id"], "变更单处理结果")
    assert got, "提案人不知道自己的变更单被处理了"
    assert "已被接受" in got[-1].body


def test_sc007_rejection_also_notifies(client, requester):
    worker, _task, cid = _funded(client, requester, "13800096040")
    oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                      json={"new_amount_cents": 30000, "reason": "加两间"},
                      headers=auth(requester)).json()["id"]
    client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/reject", headers=auth(worker))
    assert "被拒绝" in notices(requester["id"], "变更单处理结果")[-1].body


def test_sc007_change_notices_are_not_must_reach(client):
    """**不**进必达表：变更单不会因为没人看就自动生效，金额也不会自己变，
    对方随时能在合约页看到它。V90 那张表的标准是拿来做减法的
    （TEAM-062 同一条判断）。"""
    from app.modules.notification.service import MUST_REACH

    for title in ("收到合约变更单", "变更单处理结果"):
        assert ("contract", title) not in MUST_REACH


# --------------------------------------------------- 钱真的跟着动
def test_sc007_accepting_tops_up_escrow_and_keeps_money_conserved(client, requester):
    """加价被接受 → 差额自动补托管；对账不变量不破。"""
    worker, task, cid = _funded(client, requester, "13800096050")
    before = client.get("/api/v1/wallet", headers=auth(requester)).json()
    oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                      json={"new_amount_cents": 30000, "reason": "加两间"},
                      headers=auth(requester)).json()["id"]
    client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))

    after = client.get("/api/v1/wallet", headers=auth(requester)).json()
    diff = 30000 - 20000
    assert after["escrow_cents"] == before["escrow_cents"] + diff
    assert after["available_cents"] == before["available_cents"] - diff
    # 任务预算同步（TASK-025）
    assert client.get(f"/api/v1/tasks/{task['id']}",
                      headers=auth(requester)).json()["budget_cents"] == 30000

    from tests.conftest import make_admin

    admin = make_admin(client, "13800096059")
    assert client.post("/api/v1/admin/jobs/reconcile", headers=auth(admin)).json()["ok"] is True


# --------------------------------------------------- SC-004 分期
def test_sc004_milestones_can_only_be_defined_before_both_signatures(client, requester):
    """窗口只在双签前——而此前**没有任何端能定义分期**，
    于是生产环境里每一份合约都只有一期，网页上那张分期表
    （渲染条件 `length > 1`）是一段跑不到的代码。
    """
    worker = register(client, "13800096060", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 300000)
    task = publish_task(client, requester)
    app_id = client.post(f"/api/v1/tasks/{task['id']}/applications",
                         json={"message": "我可以做"}, headers=auth(worker)).json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept",
                      headers=auth(requester)).json()["contract_id"]

    # 双签前：可以定义
    ok = client.post(f"/api/v1/contracts/{cid}/milestones",
                     json={"items": [{"title": "第一期", "amount_cents": 8000},
                                     {"title": "第二期", "amount_cents": 12000}]},
                     headers=auth(requester))
    assert ok.status_code == 200, ok.text
    assert len(ok.json()["milestones"]) == 2

    # 合计不等于合约金额：服务端拒，且理由说清差多少
    bad = client.post(f"/api/v1/contracts/{cid}/milestones",
                      json={"items": [{"title": "第一期", "amount_cents": 8000}]},
                      headers=auth(requester))
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "amount_mismatch"

    # 双签后：锁定，改价要走变更单
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(worker))
    locked = client.post(f"/api/v1/contracts/{cid}/milestones",
                         json={"items": [{"title": "一期", "amount_cents": 20000}]},
                         headers=auth(requester))
    assert locked.status_code == 409
    assert locked.json()["detail"]["code"] == "milestones_locked"
