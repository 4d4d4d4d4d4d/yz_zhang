"""FIN-070 「资金类强制幂等」是一句没人检查的承诺（98 号 spec）。

`app/core/idempotency.py` 的 docstring 第一行写着：

    14.6「所有写操作支持 Idempotency-Key，**资金类强制**」

量一下这句话值多少：全仓只有两处用了 `replay_or_run`——
`wallet.topup` 与 `wallet.withdraw`。而动钱的函数一共六个
（`fund` / `release` / `release_milestone` / `accept_change` / `cancel` /
`execute_verdict`），**四个没有幂等键**。

这是「一个承诺，没有任何东西在检查」的第十次（V96/V99/V101/V103/V106/
V108/V109/V116/V122）。

但这一次结论不是「补四个幂等键」——合约那四条走的是**另一种**保护：
`lock_contract_funds()` 取行锁，然后判状态，不对就 409。重放一次
`POST /fund` 得到的是 `not_fundable`，钱不会动第二次。**那是一种正当的
保护，而且在并发下比幂等键更强**（幂等键挡的是同一个 key 的重放，
挡不住两个不同 key 的并发重复托管）。

真正的毛病是**没有人说过哪条走哪种**。于是：
- 读 docstring 的人以为资金类全都有幂等键（不对）；
- 加一条新的动钱接口时，没有任何东西问「你靠什么防重复」。

所以本篇做两件事：
1. `MONEY_WRITE_PROTECTION` 声明表：每一条动钱的路径写明靠什么防重复，
   **值是机制与理由，不是布尔**；
2. **真的打两次**，断言钱只动一次——不比声明，比行为。
"""
import ast
import re
from pathlib import Path

import pytest

from tests.conftest import auth, bind_payout, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task

REPO = Path(__file__).resolve().parents[2]
CONTRACT_SERVICE = REPO / "server" / "app" / "modules" / "contract" / "service.py"
WALLET_ROUTER = REPO / "server" / "app" / "modules" / "wallet" / "router.py"

# 动钱的原语。新增一个就要同时进这张表，否则下面第一条闸门会红。
MONEY_PRIMITIVES = {"escrow_hold", "escrow_release", "escrow_refund", "_settle"}

# ---------------------------------------------------------------- 声明表
#
# 每一条动钱的路径 → (防重复的机制, 为什么是这一种)。
#
# 两种机制都是正当的，但它们挡的东西不同，所以必须分别说清：
#   idempotency_key     —— 挡「同一个请求被重试两次」（网络超时、用户连点）
#   row_lock_and_status —— 挡「同一笔钱被动两次」（并发、不同 key 的重复提交）
MONEY_WRITE_PROTECTION: dict[str, tuple[str, str]] = {
    "fund": (
        "row_lock_and_status",
        "托管：先 lock_contract_funds 取行锁再判 status，重复请求拿到 409 "
        "not_fundable。幂等键在这里更弱——它挡不住两个不同 key 的并发托管，"
        "而行锁挡得住",
    ),
    "release": (
        "row_lock_and_status",
        "整单放款是重复执行代价最高的路径（CONC-012 的原话）。行锁 + "
        "status != funded 直接 409 not_releasable；放完之后状态已变，"
        "再放一次进不来",
    ),
    "release_milestone": (
        "row_lock_and_status",
        "分期放款：同上，且里程碑自己还要 status == delivered 才放，"
        "放完标 released，重放进不来",
    ),
    "accept_change": (
        "row_lock_and_status",
        "变更单加价/减价会补托管或退款。行锁 + 变更单 status 必须是 pending，"
        "接受过一次就不再是 pending",
    ),
    "cancel": (
        "row_lock_and_status",
        "取消退款：行锁 + 合约状态流转，退过一次状态已变",
    ),
    "execute_verdict": (
        "row_lock_and_status",
        "裁决分账：由纠纷状态机驱动，裁决只能下一次（dispute status 守着），"
        "不是用户可直接重放的入口",
    ),
    "wallet.topup": (
        "idempotency_key",
        "充值没有「状态」可依赖——同一个人连续充两次 100 元是**完全正当的**，"
        "所以只能靠幂等键区分「重试」与「真的又充了一笔」",
    ),
    "wallet.withdraw": (
        "idempotency_key",
        "提现同理：连续提两笔同额是正当操作，状态机分不出重试，必须靠 key",
    ),
}

EXCUSE_WORDS = ("还没做", "待补", "TODO", "以后", "下一批", "暂时")


def _money_moving_functions() -> dict[str, set[str]]:
    """`contract/service.py` 里哪些函数动了钱（静态读出来，不手抄）。"""
    tree = ast.parse(CONTRACT_SERVICE.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        used = {
            (c.func.attr if isinstance(c.func, ast.Attribute)
             else getattr(c.func, "id", None))
            for c in ast.walk(fn) if isinstance(c, ast.Call)
        }
        hit = used & MONEY_PRIMITIVES
        if hit:
            out[fn.name] = hit
    return out


def test_fin070_scanner_actually_finds_the_money_paths():
    """扫不到等于全绿，是最糟的一种绿。"""
    found = _money_moving_functions()
    assert len(found) >= 5, f"只扫出 {len(found)} 个动钱的函数，提取逻辑可能坏了"
    for known in ("fund", "release", "release_milestone"):
        assert known in found, f"扫不到已知会动钱的 {known}"
    # 反向：编一个不存在的
    assert "definitely_not_a_function" not in found


def test_fin070_every_money_path_declares_what_stops_a_duplicate():
    """每一条动钱的路径都必须写明靠什么防重复。

    **这一条是为「下一个加动钱接口的人」准备的**：他不会读 idempotency.py
    的 docstring，但他会看到这里红。
    """
    declared = set(MONEY_WRITE_PROTECTION)
    actual = set(_money_moving_functions())
    missing = sorted(actual - declared)
    assert not missing, (
        "这些函数动了钱，而没有说明靠什么防重复：\n  " + "\n  ".join(missing)
        + "\n在 MONEY_WRITE_PROTECTION 里写明机制（idempotency_key / "
        "row_lock_and_status）与理由。"
    )


def test_fin070_declared_table_has_no_dead_entries():
    """表里留着已经不存在的路径，表就会慢慢失去意义。"""
    actual = set(_money_moving_functions())
    # wallet.* 两条是端点级的，不在 contract/service.py 里
    stale = sorted(k for k in MONEY_WRITE_PROTECTION
                   if not k.startswith("wallet.") and k not in actual)
    assert not stale, f"MONEY_WRITE_PROTECTION 里这些函数已经不动钱了：{stale}"


def test_fin070_reasons_are_reasons_not_placeholders():
    """理由要是人话，而不是「以后补」——那是欠账，归 72 号台账。"""
    for name, (mech, why) in MONEY_WRITE_PROTECTION.items():
        assert mech in ("idempotency_key", "row_lock_and_status"), \
            f"{name} 的机制不在已知两种之内：{mech}"
        assert len(why) >= 20, f"{name} 的理由太敷衍：{why}"
        bad = [w for w in EXCUSE_WORDS if w in why]
        assert not bad, f"{name} 的理由里有欠账词 {bad}——那属于台账，不属于这张表"


def test_fin070_claimed_mechanism_is_really_in_the_code():
    """声称靠行锁的，代码里必须真的取了行锁。

    **不然这张表就只是一份自我声明**——而自我声明正是这一篇在修的东西。
    """
    src = CONTRACT_SERVICE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    bodies = {fn.name: ast.get_source_segment(src, fn) or ""
              for fn in tree.body if isinstance(fn, ast.FunctionDef)}
    for name, (mech, _why) in MONEY_WRITE_PROTECTION.items():
        if mech != "row_lock_and_status" or name not in bodies:
            continue
        body = bodies[name]
        assert "lock_contract_funds" in body, (
            f"{name} 声称靠行锁防重复，而函数里找不到 lock_contract_funds"
        )

    # 声称靠幂等键的，router 里必须真的接了 Idempotency-Key 并走 replay_or_run
    wallet = WALLET_ROUTER.read_text(encoding="utf-8")
    for name, (mech, _why) in MONEY_WRITE_PROTECTION.items():
        if mech != "idempotency_key":
            continue
        scope = name.split(".", 1)[1] if "." in name else name
        assert re.search(rf'replay_or_run\([^)]*"wallet\.{scope}"', wallet, re.S), (
            f"{name} 声称靠幂等键，而 wallet/router.py 里没有对应的 replay_or_run"
        )
        assert "idempotency_key: str = Header" in wallet, (
            "声称靠幂等键，而路由没有从请求头里接这个 key"
        )


# ------------------------------------------------- 行为验：真的打两次
def test_fin070_duplicate_topup_with_same_key_credits_once(client, requester):
    """同一个幂等键充两次，只到账一次——这是键唯一的用处。"""
    before = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    headers = {**auth(requester), "Idempotency-Key": "dup-topup-1"}
    a = client.post("/api/v1/wallet/topup", json={"amount_cents": 50000}, headers=headers)
    b = client.post("/api/v1/wallet/topup", json={"amount_cents": 50000}, headers=headers)
    assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
    after = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    assert after - before == 50000, f"同 key 充两次到账了 {after - before}，应只有 50000"


def test_fin070_same_key_different_amount_is_refused_not_swallowed(client, requester):
    """复用旧 key 提交**新金额**必须被拒，而不是静默返回旧结果。

    否则用户以为充了 800，实际回放的是上一次的 500——
    **把一笔没发生的充值显示成成功，比报错严重得多。**
    """
    headers = {**auth(requester), "Idempotency-Key": "dup-topup-2"}
    client.post("/api/v1/wallet/topup", json={"amount_cents": 50000}, headers=headers)
    r = client.post("/api/v1/wallet/topup", json={"amount_cents": 80000}, headers=headers)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "idempotency_key_conflict"


def test_fin070_topup_without_key_is_two_real_topups(client, requester):
    """没带 key 时两次充值是**两笔真的充值**，不该被当成重复吞掉。

    这条是反向的：一个把「同额连充」误判成重试的系统会吞掉用户的钱。
    **连续充两次 100 元是完全正当的操作。**
    """
    before = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    for _ in range(2):
        assert client.post("/api/v1/wallet/topup", json={"amount_cents": 10000},
                           headers=auth(requester)).status_code == 200
    after = client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"]
    assert after - before == 20000, f"两笔独立充值只到账 {after - before}"


def test_fin070_duplicate_fund_moves_escrow_once(client, requester, worker):
    """重复托管：第二次必须被状态拦住，托管金额只动一次。"""
    topup(client, requester, 200000)
    task = publish_task(client, requester, budget_cents=50000)
    cid = match_and_fund(client, requester, worker, task)
    wallet = client.get("/api/v1/wallet", headers=auth(requester)).json()
    escrow_after_first = wallet["escrow_cents"]

    again = client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    assert again.status_code == 409, f"重复托管没有被拦：{again.text}"
    wallet2 = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wallet2["escrow_cents"] == escrow_after_first, "重复托管动了第二次钱"


def test_fin070_duplicate_release_pays_once(client, requester, worker):
    """重复放款：第二次被拦，执行方只到账一次。

    **放款是重复执行代价最高的路径**（CONC-012 的原话）——
    托管重复了钱还在平台手里，放款重复了钱已经出去了。
    """
    topup(client, requester, 200000)
    task = publish_task(client, requester, budget_cents=50000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    assert client.post(f"/api/v1/tasks/{task['id']}/accept-delivery",
                       headers=auth(requester)).status_code == 200
    paid = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]

    again = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery",
                        headers=auth(requester))
    assert again.status_code in (400, 409), f"重复放款没有被拦：{again.text}"
    paid2 = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert paid2 == paid, f"重复放款又付了一次：{paid} → {paid2}"


def test_fin070_contract_release_guards_itself_not_just_the_task(client, requester, worker):
    """合约自己必须拦住重复放款——**不能只靠任务状态机在外面挡着**。

    这一条是红验逼出来的：上面那条走 `/accept-delivery`，而第二次请求被
    **任务**状态机拦下（任务已 completed），根本到不了 `release()`。
    于是把合约里的 `status != funded → 409` 删掉，那条测试**仍然是绿的**——
    它断言的是「重复放款被拦住了」，而拦住它的不是它以为的那个东西。

    所以这里直接调服务层，绕过任务状态机，验合约自己的那道门。
    **一个因为别处恰好也拦着而通过的断言，等于没有断言。**
    """
    from app.core.db import SessionLocal
    from app.modules.contract import service as contract_service
    from app.modules.contract.models import Contract

    topup(client, requester, 200000)
    task = publish_task(client, requester, budget_cents=50000)
    cid = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    db = SessionLocal()
    try:
        contract = db.get(Contract, cid)
        released_once = contract.released_cents
        with pytest.raises(Exception) as err:
            contract_service.release(db, contract)
        code = getattr(err.value, "detail", {})
        assert isinstance(code, dict) and code.get("code") == "not_releasable", (
            f"合约层没有用 not_releasable 拦住重复放款：{code}"
        )
        db.rollback()
        contract = db.get(Contract, cid)
        assert contract.released_cents == released_once, "合约层放了第二次"
    finally:
        db.close()


def test_fin070_duplicate_withdraw_with_same_key_debits_once(client):
    """同键重复提现只扣一次。提现是钱**离开平台**的那一步。"""
    user = register(client, "13800079001", "提现人")
    verify_user(client, user)
    topup(client, user, 300000)
    # 收款人姓名必须与实名一致（PAY-005），所以用 conftest 那个助手，
    # 不自己再写一遍绑卡请求——第二份实现必然抄漏。
    bind_payout(client, user)
    before = client.get("/api/v1/wallet", headers=auth(user)).json()["available_cents"]
    headers = {**auth(user), "Idempotency-Key": "dup-withdraw-1"}
    a = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 20000}, headers=headers)
    b = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 20000}, headers=headers)
    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    after = client.get("/api/v1/wallet", headers=auth(user)).json()["available_cents"]
    assert before - after == 20000, f"同 key 提现两次扣了 {before - after}，应只扣 20000"
