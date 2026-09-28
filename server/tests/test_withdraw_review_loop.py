"""PAY-040/041 进了人审，就再也出不来（71 号 spec）。

V91 把提现这条路接通了——在那之前没有任何端能发起提现，所以
「大额进人审」这条分支是理论上的。接通之后它变成了活的：

    WITHDRAW: 200 {"status":"pending_review","request_id":1,
                   "message":"该笔提现需人工复核，通常 1 个工作日内处理完成",
                   "available_cents":2000000,"frozen_cents":3000000}
    用户收到的通知: []

¥30000 进了 `frozen_cents`，而管理后台里**没有提现复核台**，
用户那一侧同时是全静音的。
"""
from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from tests.conftest import auth, make_admin, register, topup, verify_user

BIG = 3000000     # 触发人审的大额


def notices(user_id: int, title: str | None = None) -> list[Notification]:
    with SessionLocal() as db:
        q = db.query(Notification).filter(Notification.user_id == user_id)
        if title:
            q = q.filter(Notification.title == title)
        return q.all()


def _pending_withdraw(client, phone: str, admin_phone: str, amount: int = BIG):
    u = register(client, phone, "提现的人")
    verify_user(client, u, name="提现")
    topup(client, u, amount + 2000000)
    client.put("/api/v1/wallet/payout-account",
               json={"kind": "bank", "account_no": f"6222{phone[-8:]}0000", "holder_name": "提现"},
               headers=auth(u))
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": amount}, headers=auth(u))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_review", r.text
    return u, make_admin(client, admin_phone), r.json()["request_id"]


# ------------------------------------------------- PAY-040 复核台有判断依据
def test_pay040_queue_carries_what_a_reviewer_needs_to_decide(client):
    """改造前每行只有 id / user_id / amount_cents——
    一个风控岗要为三万块做放行判断，拿到的是一个用户 ID。"""
    u, admin, _rid = _pending_withdraw(client, "13800094001", "13800094009")
    rows = client.get("/api/v1/wallet/withdraw-requests?status=pending",
                      headers=auth(admin)).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["nickname"] == "提现的人"
    assert row["is_verified"] is True
    assert row["registered_at"], "看不到注册时间，判断不了是不是新号"
    assert row["withdrawn_total_cents"] == 0
    # 命中标记要带**具体数值**：只写「疑似拆分」，复核的人无从判断
    assert isinstance(row["flags"], list)
    assert row["flags"], "大额进人审却一条命中依据都没带出来"
    assert all(f["detail"] for f in row["flags"]), "标记没有明细"


def test_pay040_flags_never_leak_to_the_user(client):
    """AML-030/031 的分界：合规官看得到为什么，**用户只看到中性话术**。"""
    u, _admin, _rid = _pending_withdraw(client, "13800094010", "13800094019")
    # 用户自己拉不到这个队列
    assert client.get("/api/v1/wallet/withdraw-requests", headers=auth(u)).status_code == 403
    # 他自己的账单里也不该出现命中字样
    ledger = client.get("/api/v1/wallet/ledger", headers=auth(u)).text
    for word in ("可疑", "拆分", "风控", "聚集"):
        assert word not in ledger, f"账单里泄露了风控字样：{word}"


# ------------------------------------------------- PAY-041 裁决要告诉用户
def test_pay041_approval_tells_the_user_the_money_is_on_its_way(client):
    u, admin, rid = _pending_withdraw(client, "13800094020", "13800094029")
    r = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    assert r.status_code == 200, r.text

    got = notices(u["id"], "提现已通过复核")
    assert got, "批准了却不告诉用户——他看着冻结的钱不知道发生了什么"
    assert "¥30000.00" in got[-1].body


def test_pay041_rejection_is_neutral_and_says_where_the_money_went(client):
    """驳回**不能说原因**：《反洗钱法》第五条的保密义务，
    而且说了就等于教对方下次怎么规避（V55 立的那条）。

    但**必须说钱去哪了**——否则用户只知道「没通过」，不知道钱还在不在。
    """
    u, admin, rid = _pending_withdraw(client, "13800094030", "13800094039")
    client.post(f"/api/v1/wallet/withdraw-requests/{rid}/reject", headers=auth(admin))

    got = notices(u["id"], "提现未通过复核")
    assert got, "驳回了却不告诉用户"
    body = got[-1].body
    assert "退回可用余额" in body, f"没说钱去哪了：{body}"
    for word in ("可疑", "拆分", "风控", "聚集", "洗钱", "命中"):
        assert word not in body, f"驳回通知里泄露了原因：{word}"

    # 钱真的回到可用
    w = client.get("/api/v1/wallet", headers=auth(u)).json()
    assert w["frozen_cents"] == 0
    assert w["available_cents"] >= BIG


def test_pay041_decision_notices_are_funds_category_not_must_reach(client):
    """归 `funds` 类——`notify()` 的既有规则里 funds 本来就不可关，
    所以**不需要进 `MUST_REACH`**（那张表是给「本该可关却不能关」的用的）。"""
    from app.modules.notification.service import MUST_REACH

    u, admin, rid = _pending_withdraw(client, "13800094040", "13800094049")
    # 用户把能关的都关掉
    for category in ("task", "system", "interaction"):
        client.put(f"/api/v1/notifications/prefs?category={category}&enabled=false",
                   headers=auth(u))
    client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))

    rows = notices(u["id"], "提现已通过复核")
    assert rows, "资金类通知被开关拦住了"
    assert rows[-1].category == "funds"
    for title in ("提现已通过复核", "提现未通过复核"):
        assert ("funds", title) not in MUST_REACH, "funds 本来就必达，不该再塞进表里"


def test_pay041_audit_records_who_approved_it(client):
    """谁批了这笔三万块，必须留痕——这是合规底线，不是可选项。"""
    from app.modules.admin.models import AdminAudit

    u, admin, rid = _pending_withdraw(client, "13800094050", "13800094059")
    client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(admin))
    with SessionLocal() as db:
        rows = db.query(AdminAudit).filter(AdminAudit.action == "withdraw_approve").all()
    assert rows, "批准提现没有留下审计记录"
    assert rows[-1].admin_id == admin["id"]


# ------------------------------------------------- PERF 复核台的查询次数有上界
def _queries_for(client, admin, n_expected: int) -> int:
    from sqlalchemy import event

    from app.core.db import engine

    counted: list[str] = []

    def _count(conn, cursor, statement, params, context, executemany):
        counted.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        r = client.get("/api/v1/wallet/withdraw-requests?status=pending", headers=auth(admin))
        assert r.status_code == 200
        assert len(r.json()) == n_expected, f"队列里应该有 {n_expected} 笔"
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    return len(counted)


def _add_pending_rows(user_id: int, n: int) -> None:
    """直接往库里插待审行。

    这条测试量的是**读路径**的查询次数，不是写路径；而用真实注册去造
    9 个用户会撞上注册限流（那是平台在正常工作）。所以这里只造数据。
    """
    from app.modules.wallet.models import WithdrawRequest

    with SessionLocal() as db:
        for _ in range(n):
            db.add(WithdrawRequest(user_id=user_id, amount_cents=1000000))
        db.commit()


def test_pay040_queue_does_not_scale_queries_with_rows(client):
    """队列的查询次数**不随行数增长**。

    上一批把这一页写成了逐行 `db.get(User)` + **整表扫流水** + 一条标记查询：
    上限 200 行就是 600 次查询，其中 200 次是对 `ledger_entries` 的无界扫描。
    复核台是风控岗每天要开很多次的页面，这个代价不该由它承担。

    断言的是**行数翻倍时查询数不跟着涨**，而不是一个猜出来的常数上界：
    第一版写成 `<= 12`，而三行的 N+1 刚好也在 12 以内——**红验时它没红**。
    「不随行数增长」这句话得直接量出来。
    """
    u, admin, _rid = _pending_withdraw(client, "13800094100", "13800094109")
    few = _queries_for(client, admin, 1)

    _add_pending_rows(u["id"], 8)
    many = _queries_for(client, admin, 9)

    assert many <= few + 2, (
        f"1 行打了 {few} 条 SQL，9 行打了 {many} 条——查询数在跟着行数涨。\n"
        "复核台上限 200 行，这样下去就是几百次查询加上对流水表的逐行扫描。"
    )
