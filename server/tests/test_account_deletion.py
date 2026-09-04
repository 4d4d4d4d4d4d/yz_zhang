"""ACCDEL-010~032 账号注销的资金与个人信息闭环（35 号 spec）。

注销是全站唯一一个「用户主动把自己永久锁在门外」的操作：
`is_deleted` 置位、手机号改写、全部会话吊销，此后登录态 403、密码登录 400。
闸门放行一次，就等于永久锁门一次——所以它错一次的代价是不可逆的。

探针实测的三个洞：

    WITHDRAW:   200 {'status': 'pending_review', 'available_cents': 0, 'frozen_cents': 1500000}
    DEACTIVATE: 200 {'deleted': True}                       # ← ¥15,000 冻结着也放行
    PAYOUT ACCOUNT AFTER DELETE: ('6222021234567890123', '张三')   # ← 卡号原样留下
    USER AFTER DELETE: real_name=''                         # ← 同一个姓名却被清了
"""
import re

import pytest

from app.core.db import SessionLocal
from app.modules.account.deletion import (
    PAYOUT_DISPOSITION,
    USER_DISPOSITION,
    Disposition,
)
from app.modules.account.models import User
from app.modules.wallet.models import PayoutAccount, WalletAccount

from .conftest import auth, register, topup, verify_user


def deactivate(client, user):
    return client.post("/api/v1/users/me/deactivate", headers=auth(user))


def make_user(client, phone, nickname="老王", name="张三"):
    u = register(client, phone, nickname)
    verify_user(client, u, name=name)
    r = client.put("/api/v1/wallet/payout-account",
                   json={"kind": "bank", "account_no": "6222021234567890123",
                         "holder_name": name}, headers=auth(u))
    assert r.status_code == 200, r.text
    return u


# ---------- ACCDEL-010/011 资金闸门看三态，不是一态 ----------
def test_accdel010_pending_withdrawal_review_blocks_deactivation(client):
    """一笔进了人审的大额提现把钱挪到冻结，可用归零——不能因此被判定为「没钱」。

    改造前这里 200：钱包冻结着 ¥15,000，账号已经注销。
    复核驳回时 `available_cents += amount`，钱退回一个再也登不上的账户。
    """
    u = make_user(client, "13911100001")
    topup(client, u, 1_500_000)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1_500_000},
                    headers=auth(u))
    assert r.json()["status"] == "pending_review"          # 触发 AML 人审
    w = client.get("/api/v1/wallet", headers=auth(u)).json()
    assert w["available_cents"] == 0 and w["frozen_cents"] == 1_500_000

    r = deactivate(client, u)
    assert r.status_code == 409, "冻结中的钱不能被注销掉"
    assert r.json()["detail"]["code"] == "funds_remaining"
    assert "15000.00" in r.json()["detail"]["message"]      # 说清楚是多少钱
    assert "冻结" in r.json()["detail"]["message"]           # 以及卡在哪一态


def test_accdel011_message_names_every_blocking_bucket_at_once(client):
    """三个态一次说全，别让用户逐个撞墙。"""
    u = make_user(client, "13911100002")
    topup(client, u, 1_500_000)
    client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1_400_000}, headers=auth(u))
    msg = deactivate(client, u).json()["detail"]["message"]
    assert "可用余额 ¥1000.00" in msg and "冻结" in msg, msg


def test_accdel030_review_cleared_then_deactivation_leaves_all_buckets_zero(client):
    """闸门不是死路：复核出结果、冻结清零之后，注销照常可以完成。

    断言的是**不变量本身**（三态全零），而不是「某几个 409」。
    """
    import sqlalchemy as sa

    from app.core.db import engine

    u = make_user(client, "13911100003")
    topup(client, u, 5000)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 5000}, headers=auth(u))
    req_id = r.json()["request_id"]
    assert deactivate(client, u).status_code == 409          # 冻结中，先拦住

    admin = register(client, "13911100093", "风控员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    ok = client.post(f"/api/v1/wallet/withdraw-requests/{req_id}/approve", headers=auth(admin))
    assert ok.status_code == 200, ok.text

    assert deactivate(client, u).status_code == 200
    db = SessionLocal()
    acct = db.get(WalletAccount, u["id"])
    assert (acct.available_cents, acct.escrow_cents, acct.frozen_cents) == (0, 0, 0)
    db.close()


# ---------- ACCDEL-012/013 反向判断：不在终态就算进行中 ----------
def test_accdel012_settled_status_sets_are_declared_not_hand_copied():
    """终态集合必须是模型里的声明，且不与「进行中」重叠。

    钉住方向：新增状态忘了登记 → 多拦一次注销（安全侧），
    而不是被一张手抄的「进行中」白名单漏掉 → 放走一笔钱。
    """
    from app.modules.contract.models import CONTRACT_STATUSES, SETTLED_STATUSES
    from app.modules.dispute.models import CLOSED_STATUSES

    assert SETTLED_STATUSES <= set(CONTRACT_STATUSES), "终态必须是合法合约状态"
    assert {"pending_signatures", "signed", "funded"} & SETTLED_STATUSES == set()
    assert "appealed" not in CLOSED_STATUSES, "申诉复核会重新分账，不是终态"


def test_accdel013_appealed_dispute_blocks_deactivation(client, requester, worker):
    """`appealed` 是改造前手抄白名单漏掉的那一个。

    申诉复核（`appeal-verdict`）会重新分账；当事人此刻注销，
    等于放弃一笔还没算完的钱，而平台还得把钱打进一个死账户。
    """
    from app.modules.dispute.models import Dispute

    from .test_task_flow import match_and_fund, publish_task

    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付不符约定，要求重做或退款"}, headers=auth(requester))
    assert r.status_code == 201, r.text

    # 直接把纠纷置为申诉复核中：这里要验的是闸门，不是申诉流程本身
    db = SessionLocal()
    d = db.get(Dispute, r.json()["id"])
    d.status = "appealed"
    db.add(d)
    db.commit()
    db.close()

    r = deactivate(client, requester)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] in ("open_dispute", "active_contract")


# ---------- ACCDEL-020/021 处置表逐列覆盖模型 ----------
@pytest.mark.parametrize(
    "model, table",
    [(User, USER_DISPOSITION), (PayoutAccount, PAYOUT_DISPOSITION)],
)
def test_accdel021_disposition_table_covers_exactly_the_model_columns(model, table):
    """新增一列就必须做一次决定——不做决定的默认行为不能是「悄悄留下」。

    改造前注销是一段手写的六行赋值，`skills` / `certifications` / `privacy` /
    `city` / `referral_code` / `is_admin` 全部被留着，且没有任何测试会红。
    """
    columns = {c.key for c in model.__table__.columns}
    missing = columns - set(table)
    extra = set(table) - columns
    assert not missing, f"{model.__name__} 新增了列但没在处置表里登记：{sorted(missing)}"
    assert not extra, f"处置表里有 {model.__name__} 已不存在的列：{sorted(extra)}"
    assert all(isinstance(v, Disposition) for v in table.values())


# ---------- ACCDEL-022~027 逐项处置 ----------
def test_accdel022_027_dispositions_are_actually_applied(client):
    u = make_user(client, "13911100004", nickname="老王", name="张三")
    client.patch("/api/v1/users/me",
                 json={"bio": "十年水电工", "city": "杭州", "skills": ["水电"],
                       "interests": ["钓鱼"], "service_rate_cents": 20000},
                 headers=auth(u))
    db = SessionLocal()
    before = db.get(User, u["id"])
    before.is_admin = True                 # ACCDEL-024 注销一个管理员
    before.credit_score = 87
    db.add(before)
    db.commit()
    db.close()

    assert deactivate(client, u).status_code == 200

    db = SessionLocal()
    usr, payout = db.get(User, u["id"]), db.get(PayoutAccount, u["id"])
    assert usr.real_name == "张*"                  # ACCDEL-022 掩码，不是清空
    assert payout.account_no == "6222****0123"     # ACCDEL-023 不足以再发起打款
    assert payout.holder_name == "张*"
    assert usr.is_admin is False                   # ACCDEL-024
    assert usr.referral_code == ""                 # ACCDEL-026
    assert usr.credit_score == 87                  # ACCDEL-027 对手方的凭证，保留
    assert usr.id_digest and usr.id_masked         # 法定身份资料，保留
    assert (usr.bio, usr.city, usr.skills, usr.interests) == ("", "", [], [])
    assert usr.password_hash == "" and usr.accepting_orders is False
    db.close()


def test_accdel025_deactivation_does_not_wash_away_a_ban(client):
    """注销不是洗白封禁的手段。

    走单元入口而不是 HTTP：被封禁的账号连 `get_current_user` 都过不去，
    但被封者可以先注销**再**被追认封禁（人工审核滞后），也可以由
    管理员在注销后回溯封禁——两种情形下这个位都必须留得住。
    """
    from app.modules.account.deletion import erase_personal_data

    u = register(client, "13911100007", "被封者")
    db = SessionLocal()
    usr = db.get(User, u["id"])
    usr.is_banned = True
    erase_personal_data(db, usr)
    db.commit()
    assert usr.is_banned is True and usr.is_deleted is True
    db.close()


def test_accdel032_no_full_card_number_survives_deletion(client):
    """扫全表，而不是只看刚注销的那一行。"""
    u = make_user(client, "13911100005")
    assert deactivate(client, u).status_code == 200

    db = SessionLocal()
    deleted = {r.id for r in db.query(User).filter(User.is_deleted.is_(True))}
    leaked = [
        p.account_no for p in db.query(PayoutAccount)
        if p.user_id in deleted and re.search(r"\d{12,}", p.account_no)
    ]
    db.close()
    assert not leaked, f"已注销用户的完整卡号仍在库里：{leaked}"


# ---------- 非回归 ----------
def test_clean_account_can_still_deactivate_and_is_locked_out(client):
    """没有钱、没有合约的账号，注销体验与改造前一致。"""
    u = register(client, "13911100006", "路人")
    assert deactivate(client, u).status_code == 200
    assert client.get("/api/v1/users/me", headers=auth(u)).status_code == 403
    r = client.post("/api/v1/auth/login",
                    json={"phone": "13911100006", "password": "pass123456"})
    assert r.status_code == 400
