"""TEAM-063 / NTF-063 / TEAM-055 / PAY-044 没有人会被提醒第二次（75 号 spec）。

四条探针，四条都是「闹钟只响一次」：

- 支出申请躺 90 天，审批人收到的「支出待审批」**始终是 1 条**
- 交付后还剩 2 小时就自动放款，发布方**没有收到第二句话**
- 预算池用到 96%，预警 **0 条**
- 大额提现一审通过 30 天后还是 `awaiting_second`，用户 **¥21000 一直冻着**

其中两条，沉默的代价是钱。
"""
from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from tests.conftest import JOB_HEADERS, auth, make_admin, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task


def _titles(client, user, title):
    rows = client.get("/api/v1/notifications?limit=100", headers=auth(user)).json()
    items = rows["items"] if isinstance(rows, dict) else rows
    return [n for n in items if n["title"] == title]


def _team_with_member(client, owner_phone: str, member_phone: str, limit: int = 1000):
    owner = register(client, owner_phone, "老板")
    member = register(client, member_phone, "员工")
    verify_user(client, owner, name="老板")
    tid = client.post("/api/v1/teams", json={"name": "催办队"},
                      headers=auth(owner)).json()["id"]
    client.post(f"/api/v1/teams/{tid}/members",
                json={"user_id": member["id"], "role": "member",
                      "spend_limit_cents": limit}, headers=auth(owner))
    return owner, member, tid


def _age_request(rid: int, hours: float):
    """把申请的创建时间往前推。"""
    with SessionLocal() as db:
        from app.modules.team.models import SpendRequest

        row = db.get(SpendRequest, rid)
        row.created_at = utcnow() - timedelta(hours=hours)
        db.commit()


# ------------------------------------------------- TEAM-063 审批催办与超时
def test_team063_a_request_left_lying_gets_chased(client):
    """躺过间隔的申请会被**再提醒一次**——改造前只有提交时那一条。"""
    owner, member, tid = _team_with_member(client, "13800101001", "13800101002")
    rid = client.post(f"/api/v1/teams/{tid}/spends",
                      json={"amount_cents": 500000, "purpose": "买设备"},
                      headers=auth(member)).json()["id"]
    assert len(_titles(client, owner, "支出待审批")) == 1
    _age_request(rid, settings.TEAM_APPROVAL_REMIND_HOURS + 1)

    r = client.post("/api/v1/teams/jobs/remind-approvals", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["reminded"] == 1
    chase = _titles(client, owner, "支出待审批催办")
    assert chase, "躺了一天多，审批人没有被再提醒一次"
    # 催办必须说**已经等了多久**：不说就只是同一条通知重发
    assert "已等待" in chase[0]["body"] and "小时" in chase[0]["body"]
    # 超时天数取自配置（V61/V90：文案里的数字不许是字面量）
    assert str(settings.TEAM_APPROVAL_TIMEOUT_DAYS) in chase[0]["body"]


def test_team063_requester_is_not_chased_about_his_own_request(client):
    """催办是给审批人的。发起人收到「等你审批」是纯噪音（V92 同一条）。"""
    owner, member, tid = _team_with_member(client, "13800101010", "13800101011")
    rid = client.post(f"/api/v1/teams/{tid}/spends",
                      json={"amount_cents": 500000, "purpose": "买设备"},
                      headers=auth(member)).json()["id"]
    _age_request(rid, settings.TEAM_APPROVAL_REMIND_HOURS + 1)
    client.post("/api/v1/teams/jobs/remind-approvals", headers=JOB_HEADERS)
    assert not _titles(client, member, "支出待审批催办")


def test_team063_chasing_repeats_by_interval_not_once(client):
    """「第二次提醒」如果也只有一次，三个月后还是同一个问题。"""
    owner, member, tid = _team_with_member(client, "13800101020", "13800101021")
    rid = client.post(f"/api/v1/teams/{tid}/spends",
                      json={"amount_cents": 500000, "purpose": "买设备"},
                      headers=auth(member)).json()["id"]
    _age_request(rid, settings.TEAM_APPROVAL_REMIND_HOURS + 1)
    client.post("/api/v1/teams/jobs/remind-approvals", headers=JOB_HEADERS)
    # 同一轮里再跑一次不该重复催（间隔没到）
    assert client.post("/api/v1/teams/jobs/remind-approvals",
                       headers=JOB_HEADERS).json()["reminded"] == 0
    assert len(_titles(client, owner, "支出待审批催办")) == 1

    # 再过一个间隔——必须催第二次
    with SessionLocal() as db:
        from app.modules.team.models import SpendRequest

        row = db.get(SpendRequest, rid)
        row.reminded_at = utcnow() - timedelta(hours=settings.TEAM_APPROVAL_REMIND_HOURS + 1)
        db.commit()
    assert client.post("/api/v1/teams/jobs/remind-approvals",
                       headers=JOB_HEADERS).json()["reminded"] == 1
    assert len(_titles(client, owner, "支出待审批催办")) == 2


def test_team063_request_expires_and_both_sides_are_told(client):
    """不能永远躺着：超时关闭，两端都要知道。

    往**后**兜（关闭、可重提），不往前兜（自动批准）——
    超时是「没有人看」的证据，不是「可以放行」的授权。
    """
    owner, member, tid = _team_with_member(client, "13800101030", "13800101031")
    rid = client.post(f"/api/v1/teams/{tid}/spends",
                      json={"amount_cents": 500000, "purpose": "买设备"},
                      headers=auth(member)).json()["id"]
    _age_request(rid, settings.TEAM_APPROVAL_TIMEOUT_DAYS * 24 + 1)

    r = client.post("/api/v1/teams/jobs/remind-approvals", headers=JOB_HEADERS)
    assert r.json()["expired"] == 1
    assert r.json()["reminded"] == 0, "同一轮里既催办又关闭，发起人会收到两条自相矛盾的通知"

    rows = client.get(f"/api/v1/teams/{tid}/spends", headers=auth(owner)).json()
    row = [x for x in rows if x["id"] == rid][0]
    assert row["status"] == "expired", "超时的申请还是 pending"
    assert _titles(client, member, "支出申请已超时关闭"), "发起人不知道自己白等了"
    assert _titles(client, owner, "支出申请已超时关闭"), "审批人列表里会留一条批不了的申请"
    # 关闭不动钱：可以原样重新发起
    assert client.post(f"/api/v1/teams/{tid}/spends",
                       json={"amount_cents": 500000, "purpose": "买设备"},
                       headers=auth(member)).status_code == 201


def test_team063_expired_request_cannot_be_approved_afterwards(client):
    """过期之后再批准就等于「超时自动批准」绕了个弯又回来了。"""
    owner, member, tid = _team_with_member(client, "13800101040", "13800101041")
    rid = client.post(f"/api/v1/teams/{tid}/spends",
                      json={"amount_cents": 500000, "purpose": "买设备"},
                      headers=auth(member)).json()["id"]
    _age_request(rid, settings.TEAM_APPROVAL_TIMEOUT_DAYS * 24 + 1)
    client.post("/api/v1/teams/jobs/remind-approvals", headers=JOB_HEADERS)

    r = client.post(f"/api/v1/teams/{tid}/spends/{rid}/decide",
                    json={"approve": True, "reason": ""}, headers=auth(owner))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "already_decided"


# ------------------------------------------------- NTF-063 自动放款前的最后一次提醒
def _delivered_task(client, requester, phone: str):
    worker = register(client, phone, "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    return worker, task


def _age_delivery(task_id: int, hours_left: float):
    """把交付时间推到「还剩 hours_left 小时就自动放款」。"""
    with SessionLocal() as db:
        from app.modules.task.models import Task

        t = db.get(Task, task_id)
        t.delivered_at = (utcnow() - timedelta(days=settings.AUTO_ACCEPT_DAYS)
                          + timedelta(hours=hours_left))
        db.commit()


def test_ntf063_last_call_before_money_moves(client, requester):
    """三天里一句「还有几小时」都没有，然后钱就放出去了。"""
    _worker, task = _delivered_task(client, requester, "13800101050")
    assert len(_titles(client, requester, "待验收提醒")) == 1
    _age_delivery(task["id"], 2)

    r = client.post("/api/v1/tasks/jobs/remind-acceptance", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["reminded"] == 1
    last = _titles(client, requester, "验收即将到期")
    assert last, "临放款前没有任何提醒"
    assert "小时" in last[0]["body"]
    # 要说清后果：放款不可撤回
    assert "不可撤回" in last[0]["body"]


def test_ntf063_reminder_is_idempotent_and_not_sent_after_the_fact(client, requester):
    """跑多少次只发一条；已经过线的不补发（钱都放了，那是噪音）。"""
    _worker, task = _delivered_task(client, requester, "13800101060")
    _age_delivery(task["id"], 2)
    client.post("/api/v1/tasks/jobs/remind-acceptance", headers=JOB_HEADERS)
    assert client.post("/api/v1/tasks/jobs/remind-acceptance",
                       headers=JOB_HEADERS).json()["reminded"] == 0
    assert len(_titles(client, requester, "验收即将到期")) == 1

    _worker2, task2 = _delivered_task(client, requester, "13800101061")
    _age_delivery(task2["id"], -1)          # 已经过线
    assert client.post("/api/v1/tasks/jobs/remind-acceptance",
                       headers=JOB_HEADERS).json()["reminded"] == 0


def test_ntf063_lead_time_follows_the_configured_days(client, requester, monkeypatch):
    """提前量按比例算，不写死小时数。

    `AUTO_ACCEPT_DAYS` 调成 1 天时，「到期前 18 小时」这种写死值
    会把提前量压到几乎没有——`remind_response` 犯过一次的错误。
    """
    _worker, task = _delivered_task(client, requester, "13800101070")
    # 同一句话——「还有 20 小时钱就放出去了」——在两种配置下结论不同：
    # 3 天窗口的提前量是 18 小时，20 小时还太早；12 天窗口的提前量是 72 小时，
    # 20 小时早该提醒了。写死小时数的实现两次都给同一个答案。
    _age_delivery(task["id"], 20)
    assert client.post("/api/v1/tasks/jobs/remind-acceptance",
                       headers=JOB_HEADERS).json()["reminded"] == 0

    monkeypatch.setattr(settings, "AUTO_ACCEPT_DAYS", 12)   # 提前量变 72 小时
    _age_delivery(task["id"], 20)           # 仍然是「还剩 20 小时」
    assert client.post("/api/v1/tasks/jobs/remind-acceptance",
                       headers=JOB_HEADERS).json()["reminded"] == 1


def test_ntf063_reminder_cannot_be_switched_off(client):
    """错过它就少一笔钱——所以它必须在必达表里（65 号的判定标准）。"""
    from app.modules.notification.service import MUST_REACH

    assert ("task", "验收即将到期") in MUST_REACH


# ------------------------------------------------- TEAM-055 预算池预警
def _pooled_team(client, owner_phone: str, budget: int):
    owner = register(client, owner_phone, "老板")
    verify_user(client, owner, name="老板")
    tid = client.post("/api/v1/teams", json={"name": "池子队"},
                      headers=auth(owner)).json()["id"]
    client.post(f"/api/v1/teams/{tid}/budget",
                json={"monthly_budget_cents": budget}, headers=auth(owner))
    return owner, tid


def _spend_pool(client, owner, tid: int, amount: int):
    """让 owner 自己走一遍「申请 → 执行」把池子花掉。

    owner 豁免个人额度（TEAM-051），所以这条路径不需要审批，
    但仍然会走到执行时的预算池判断——预警就挂在那里。
    """
    from app.modules.wallet import service as wsvc

    with SessionLocal() as db:
        acct = wsvc.get_or_create(db, tid)
        acct.available_cents += amount
        db.add(acct)
        db.commit()
    # owner 豁免个人额度（TEAM-051），所以这一笔在创建时就直接执行了——
    # 预警挂在执行那一步上，所以这条路径同样会走到它
    r = client.post(f"/api/v1/teams/{tid}/spends",
                    json={"amount_cents": amount, "purpose": "采购"},
                    headers=auth(owner))
    assert r.status_code == 201, r.text
    assert r.json()["needed_approval"] is False
    return r


def test_team055_owner_is_warned_before_the_pool_runs_dry(client):
    """到顶那一刻所有人一起被卡住，owner 的第一个信号不该是员工来问为什么。"""
    owner, tid = _pooled_team(client, "13800101080", 1000000)
    _spend_pool(client, owner, tid, 900000)              # 90% > 80% 预警线

    warn = _titles(client, owner, "预算池即将用尽")
    assert warn, "池子用到 90% 没有任何预警"
    # 三个数都要给：只说「快用完了」，收到的人还得自己去查一遍
    assert "9000.00" in warn[0]["body"] and "10000.00" in warn[0]["body"] \
        and "1000.00" in warn[0]["body"]


def test_team055_warning_is_once_per_month_but_resets_when_the_pool_changes(client):
    """一个月一次就够；而池子一改，这句话就不成立了，得重新算。"""
    owner, tid = _pooled_team(client, "13800101090", 1000000)
    _spend_pool(client, owner, tid, 850000)
    assert len(_titles(client, owner, "预算池即将用尽")) == 1
    _spend_pool(client, owner, tid, 50000)
    assert len(_titles(client, owner, "预算池即将用尽")) == 1, "同一个月重复预警"

    # 调高池子 → 标记清掉；再次逼近上限时必须有第二次预警
    client.post(f"/api/v1/teams/{tid}/budget",
                json={"monthly_budget_cents": 1100000}, headers=auth(owner))
    _spend_pool(client, owner, tid, 100000)              # 已用 100 万 / 110 万 = 91%
    assert len(_titles(client, owner, "预算池即将用尽")) == 2, \
        "调高预算后再次逼近上限，没有第二次预警——正是这一批要修的毛病本身"


def test_team055_no_pool_means_no_warning(client):
    """不设池（0）的团队没有「快用完」这回事——既有行为不变。"""
    owner = register(client, "13800101100", "老板")
    verify_user(client, owner, name="老板")
    tid = client.post("/api/v1/teams", json={"name": "无池队"},
                      headers=auth(owner)).json()["id"]
    _spend_pool(client, owner, tid, 900000)
    assert not _titles(client, owner, "预算池即将用尽")


# ------------------------------------------------- PAY-044 提现复核催办与超时兜底
def _awaiting_second(client, phone: str, admin_phone: str):
    amount = settings.WITHDRAW_DUAL_APPROVAL_CENTS + 100000
    u = register(client, phone, "提现的人")
    verify_user(client, u, name="提现")
    topup(client, u, amount + 1000000)
    client.put("/api/v1/wallet/payout-account",
               json={"kind": "bank", "account_no": f"6222{phone[-8:]}11", "holder_name": "提现"},
               headers=auth(u))
    rid = client.post("/api/v1/wallet/withdraw", json={"amount_cents": amount},
                      headers=auth(u)).json()["request_id"]
    admin = make_admin(client, admin_phone)
    client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    return u, admin, rid, amount


def _age_withdraw(rid: int, hours: float):
    with SessionLocal() as db:
        from app.modules.wallet.models import WithdrawRequest

        row = db.get(WithdrawRequest, rid)
        row.created_at = utcnow() - timedelta(hours=hours)
        if row.first_approved_at:
            row.first_approved_at = utcnow() - timedelta(hours=hours)
        db.commit()


def test_pay044_stuck_second_approval_chases_the_admins(client):
    """一审通过后没人来确认，申请会停在那儿，而用户的钱是冻着的。"""
    _u, admin, rid, _amount = _awaiting_second(client, "13800101110", "13800101119")
    _age_withdraw(rid, settings.WITHDRAW_REVIEW_REMIND_HOURS + 1)

    r = client.post("/api/v1/wallet/jobs/remind-second-approval", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["reminded"] == 1
    chase = _titles(client, admin, "提现复核待处理")
    assert chase, "卡了一天多，没有任何人被提醒"
    # 收到的人必须知道自己是第二个：否则他会以为「已经有人在处理了」
    assert "另一位" in chase[0]["body"]
    assert str(settings.WITHDRAW_REVIEW_TIMEOUT_DAYS) in chase[0]["body"]


def test_pay044_timeout_refunds_the_user_and_never_pays_out(client):
    """超时兜底**只往可逆方向兜**：退回可用余额，绝不自动放款。

    往前兜会把 V99 刚立的四眼原则一笔抹掉——只要拖过超时天数，
    一个人的批准就等于两个人的批准，而攻击者需要做的只是**等**。
    """
    u, admin, rid, amount = _awaiting_second(client, "13800101120", "13800101129")
    before = client.get("/api/v1/wallet", headers=auth(u)).json()
    assert before["frozen_cents"] == amount
    _age_withdraw(rid, settings.WITHDRAW_REVIEW_TIMEOUT_DAYS * 24 + 1)

    r = client.post("/api/v1/wallet/jobs/remind-second-approval", headers=JOB_HEADERS)
    assert r.json()["closed"] == 1

    after = client.get("/api/v1/wallet", headers=auth(u)).json()
    assert after["frozen_cents"] == 0, "钱还冻着"
    assert after["available_cents"] == before["available_cents"] + amount

    # 钱**没有流出平台**：不许出现 withdraw 流水
    rows = client.get("/api/v1/wallet/ledger", headers=auth(u)).json()
    kinds = [x["kind"] for x in (rows["items"] if isinstance(rows, dict) else rows)]
    assert "withdraw" not in kinds, "超时兜底把钱打出去了——四眼原则被「等」绕过了"
    assert "withdraw_refund" in kinds

    assert _titles(client, u, "提现申请已超时关闭"), "用户不知道自己的申请没了"
    # 资金五不变量不因超时关闭而破
    assert client.post("/api/v1/admin/jobs/reconcile",
                       headers=auth(admin)).json()["ok"] is True


def test_pay044_timeout_close_leaves_an_audit_row(client):
    """一笔动了钱的操作，不能因为没有操作人就不留痕。"""
    _u, admin, rid, _amount = _awaiting_second(client, "13800101130", "13800101139")
    _age_withdraw(rid, settings.WITHDRAW_REVIEW_TIMEOUT_DAYS * 24 + 1)
    client.post("/api/v1/wallet/jobs/remind-second-approval", headers=JOB_HEADERS)

    rows = client.get("/api/v1/admin/audit-log?action=withdraw_timeout_close&limit=10",
                      headers=auth(admin)).json()
    assert rows, "超时关闭没有留下审计行"
    assert rows[0]["target_id"] == rid


def test_pay044_timeout_cannot_be_asked_to_pay_out(client):
    """代码层面也要拦住：`timeout=True` 不许配 `approve=True`。

    这条规则写在 spec 里不够——下一个人改这段代码时读的是代码。
    """
    from app.modules.wallet import service as wsvc

    _u, _admin, rid, _amount = _awaiting_second(client, "13800101140", "13800101149")
    with SessionLocal() as db:
        from app.modules.wallet.models import WithdrawRequest

        req = db.get(WithdrawRequest, rid)
        with pytest.raises(ValueError):
            wsvc.decide_withdraw(db, req, approve=True, admin_id=None, timeout=True)


def test_pay044_a_pending_request_nobody_looked_at_is_also_chased(client):
    """从来没人看过的那些同样会卡住用户的钱——不只是一审后的。"""
    amount = settings.LARGE_WITHDRAW_CENTS + 1000
    u = register(client, "13800101150", "提现的人")
    verify_user(client, u, name="提现")
    topup(client, u, amount + 100000)
    client.put("/api/v1/wallet/payout-account",
               json={"kind": "bank", "account_no": "6222020000101150", "holder_name": "提现"},
               headers=auth(u))
    rid = client.post("/api/v1/wallet/withdraw", json={"amount_cents": amount},
                      headers=auth(u)).json()["request_id"]
    admin = make_admin(client, "13800101159")
    _age_withdraw(rid, settings.WITHDRAW_REVIEW_REMIND_HOURS + 1)

    assert client.post("/api/v1/wallet/jobs/remind-second-approval",
                       headers=JOB_HEADERS).json()["reminded"] == 1
    body = _titles(client, admin, "提现复核待处理")[0]["body"]
    assert "冻结" in body, "催办没说清用户的钱正冻着——那是这件事的紧迫性所在"
