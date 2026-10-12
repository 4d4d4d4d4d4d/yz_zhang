"""SEC-067 / SYNC-050b 哪些字段永远不许从请求体里收（99 号 spec 第 4 节）。

**请求体多收一个字段的代价，取决于那个字段是什么。** 多收一个 `status`
是业务错乱（任务被自己置成「已完成」）；多收一个 `is_admin` 是整站失守。

V124 开工前先探过一次：把 OpenAPI 里所有请求体 schema 的字段与一串敏感字段
求交——

    is_admin / is_verified / credit_score / status / creator_id /
    executor_id / released_cents / available_cents / id ...   → 0 处

今天一处都没有。用户资料更新是严格白名单（`ProfileUpdateIn`），而 pydantic
默认把多余字段静默丢掉。**但这是一个碰巧成立的事实，不是一个被钉住的约束**：
哪天有人为了方便给某个 schema 加一个 `status: str | None = None`，
而 SDK 的 `createTask` 参数类型此前是 `Partial<Task>`（里面就有 status），
客户端早就在发了——那一刻起它就生效了，没有任何东西会红。

本篇三层：

1. **永不接受表**：身份、权限、信用、账本、签署状态这些字段，任何请求体
   schema 都不许声明；
2. **受控接受表**：金额、角色、目标用户这类**合法但敏感**的字段，
   只许出现在表里写明了理由的 schema 上，新的 schema 要接收它就得来这里登记；
3. **行为验**：把这些字段塞进真实请求，断言它们**没有生效**。
"""
import re

import pytest

from tests.conftest import auth, register, topup, verify_user
from tests.test_task_flow import publish_task

# ---------------------------------------------------------------- 永不接受
# 字段 → 为什么任何请求体都不许收它。值是理由，不是布尔。
NEVER_ACCEPTED: dict[str, str] = {
    "is_admin": "权限位。能从请求体写进来，任何人都能把自己变成管理员",
    "is_verified": "实名结果只能由核验流程写入；自己声明自己已实名，等于没有实名",
    "is_banned": "封禁状态由处置流程写入；被封的人自己解封",
    "is_adult": "成年标记从证件号派生（LAW-005），自己声明就绕过了未成年人接单拦截",
    "is_agent": "主体类型（人/Agent/团队/合作体）决定一整套权限分支，不能由调用方声明",
    "is_team": "团队账号有独立钱包与审批链，自称团队就能绕开个人额度",
    "is_venture": "合作体账号走一致同意治理，自称合作体就能绕开个人身份约束",
    "credit_score": "信用分是平台对行为的评价，自己写自己的信用分等于没有信用分",
    "rating_avg": "口碑由评价聚合得出",
    "tasks_completed": "完成数由闭环事件累计",
    "id_digest": "证件号摘要只由核验流程写入，用于一人多号查重（VND-023）",
    "creator_id": "任务的发布方就是调用者本人；能指定 creator_id 就能替别人发任务",
    "executor_id": "执行方由选人成交写入；能指定它就能把任务直接指给自己",
    "requester_id": "合约当事人由成交写入",
    "released_cents": "已放款金额是账本的派生值；能写它就能伪造放款进度",
    "available_cents": "余额只能由账本变动产生",
    "escrow_cents": "托管额只能由托管/放款产生",
    "frozen_cents": "冻结额只能由风控与提现流程产生",
    "fee_bps": "平台费率是平台定的，不是下单人定的",
    "signed_by_requester": "签署状态只能由签署动作写入",
    "signed_by_executor": "执行方的签署状态只能由执行方本人的签署动作写入",
    "verdict_executor_share_bps": "裁决比例只能由裁决流程写入",
    "created_at": "时间戳由服务端生成；能写它就能伪造先后顺序（比如抢在截止前报名）",
}

# ---------------------------------------------------------------- 受控接受
# 合法但敏感：只许出现在这里登记过的 schema 上。字段 → {schema: 理由}
GUARDED: dict[str, dict[str, str]] = {
    "amount_cents": {
        "AmountIn": "充值与提现的金额本来就由用户填；防重复由幂等键管（FIN-070）",
        "PayCallbackIn": "支付回调的金额来自支付通道，回调本身要验签",
        "SettleIn": "平台收入结算，仅管理员",
        "CouponIn": "券面额，仅管理员",
        "FundIn": "补贴池注资，仅管理员",
        "DistributeIn": "合作体分配金额，需全员一致同意（治理流程）",
        "ProposalIn": "合作体出款提案金额，需全员投票通过才执行（一致同意治理）",
        "SpendIn": "团队花钱申请，按成员额度与档位审批（TEAM-010）",
    },
    "budget_cents": {
        "TaskIn": "发布方定预算，本来就是他的钱",
        "TaskEditIn": "发布方改预算，托管前有效",
        "ClarifyIn": "AI 澄清时带上预算作上下文，不落库",
        "NodePatchIn": "拆解草稿里一步的预算由母任务的发布方自己分；validate_tree 逐层约束不超过上一级，"
                       "确认后才成为子任务预算，动钱仍走托管合约（AI-DEC-046）",
    },
    "role": {
        "MemberIn": "团队成员角色由 owner 设定（require_role owner）",
        "MemberPatch": "改角色与额度同样仅 owner（TEAM-010 只有 owner 能改角色与额度）",
    },
    "user_id": {
        "DirectIn": "目标用户：和谁聊天",
        "FriendRequestIn": "目标用户：加谁好友",
        "MemberIn": "目标用户：把谁加进团队（owner 才能加）",
        "InviteIn": "目标用户：邀请谁（任务邀约 / 合作体邀约）",
    },
}


def _request_schemas() -> dict[str, set[str]]:
    """OpenAPI 里每个**被用作请求体**的 schema → 它的字段集合。"""
    from app.main import app

    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    used: dict[str, set[str]] = {}
    for _path, ops in spec["paths"].items():
        for _verb, op in ops.items():
            body = (op.get("requestBody", {}).get("content", {})
                    .get("application/json", {}).get("schema", {}) or {})
            ref = body.get("$ref")
            if not ref:
                continue
            name = ref.split("/")[-1]
            used[name] = set(schemas.get(name, {}).get("properties", {}))
    return used


def _short(name: str) -> str:
    """FastAPI 遇到同名 schema 会加模块前缀（`app__modules__x__router__InviteIn`）。"""
    return name.rsplit("__", 1)[-1]


def test_sec067_scanner_actually_reads_request_schemas():
    """扫不到等于全绿，是最糟的一种绿。"""
    used = _request_schemas()
    assert len(used) >= 60, f"只读出 {len(used)} 个请求体 schema"
    assert "title" in used.get("TaskIn", set()), "TaskIn 的字段没读出来"
    assert any("amount_cents" in f for f in used.values()), "扫不到任何 amount_cents"


def test_sec067_no_request_schema_accepts_a_never_accepted_field():
    """身份、权限、信用、账本、签署状态——任何请求体都不许声明。"""
    hits = []
    for name, fields in _request_schemas().items():
        for f in sorted(fields & set(NEVER_ACCEPTED)):
            hits.append(f"{_short(name)}.{f} —— {NEVER_ACCEPTED[f]}")
    assert not hits, (
        "这些请求体 schema 声明了永远不该从客户端收的字段：\n  " + "\n  ".join(hits)
    )


def test_sec067_guarded_fields_only_appear_where_registered():
    """金额、角色、目标用户：合法但敏感，新 schema 要收它就得来这里登记。

    **这一条是为「下一个加接口的人」准备的**：他给新 schema 加一个
    `amount_cents` 时，会被问「这个金额是谁定的、谁来管它的上限」。
    """
    unregistered = []
    for name, fields in _request_schemas().items():
        for f in sorted(fields & set(GUARDED)):
            if _short(name) not in GUARDED[f]:
                unregistered.append(f"{_short(name)}.{f}")
    assert not unregistered, (
        "这些 schema 收了敏感字段而没有登记理由：\n  " + "\n  ".join(unregistered)
        + "\n在 GUARDED 里写明这个值是谁定的、谁来约束它。"
    )


def test_sec067_tables_have_no_dead_or_lazy_entries():
    """登记了却已经不存在的 schema 会掩护掉真正该看的；理由要是人话。"""
    present = {_short(n) for n in _request_schemas()}
    for field, owners in GUARDED.items():
        for schema, why in owners.items():
            assert schema in present, f"GUARDED[{field}] 里的 {schema} 已经不是请求体了"
            assert len(why) >= 6, f"GUARDED[{field}][{schema}] 理由太敷衍"
    for field, why in NEVER_ACCEPTED.items():
        # 与 GUARDED 同一个标准：「同上」不是理由——它让读的人去猜上面那条
        # 为什么也适用于这一条，而那正是这张表要消除的猜测
        assert len(why) >= 6 and why != "同上", f"NEVER_ACCEPTED[{field}] 理由太敷衍：{why}"


# ------------------------------------------------- 行为验：塞进去，没生效
def test_sec067_profile_update_cannot_make_you_an_admin_or_verified(client):
    """把权限位与信用分塞进资料更新：200，但**一个都没写进去**。"""
    u = register(client, "13800096001", "想当管理员的人")
    r = client.patch("/api/v1/users/me", headers=auth(u), json={
        "nickname": "改个名", "is_admin": True, "is_verified": True,
        "credit_score": 999, "is_banned": False, "tasks_completed": 500,
    })
    assert r.status_code == 200, r.text
    me = client.get("/api/v1/users/me", headers=auth(u)).json()
    assert me["nickname"] == "改个名", "正当字段没生效，这条测试本身就没验到东西"
    assert me["is_admin"] is False
    assert me["is_verified"] is False
    assert me["credit_score"] != 999
    assert me["tasks_completed"] == 0


def test_sec067_task_create_ignores_status_and_party_fields(client, requester):
    """发任务时塞 status / creator_id / executor_id：都不生效。

    能写 `status` 就能把任务直接置成已完成；能写 `executor_id` 就能把
    任务直接指给自己——两个都绕过了报名、选人、托管那一整条链。
    """
    other = register(client, "13800096002", "被冒名的人")
    topup(client, requester, 100000)
    r = client.post("/api/v1/tasks", headers=auth(requester), json={
        "title": "多塞字段的任务", "category": "保洁", "budget_cents": 20000,
        "ip_assignment": "assign", "publish_now": True, "is_remote": True,
        "status": "completed", "creator_id": other["id"], "executor_id": other["id"],
        "created_at": "2020-01-01T00:00:00Z", "id": 999999,
    })
    assert r.status_code in (200, 201), r.text
    t = r.json()
    assert t["status"] == "published", f"status 被客户端写进去了：{t['status']}"
    assert t["creator_id"] == requester["id"], "creator_id 被客户端指定了"
    assert t["executor_id"] is None, "executor_id 被客户端指定了"
    assert t["id"] != 999999
    assert not t["created_at"].startswith("2020"), "时间戳被客户端伪造了"


def test_sec067_contract_ledger_fields_cannot_be_posted(client, requester, worker):
    """往合约动作里塞账本字段：都不生效。"""
    from tests.test_task_flow import match_and_fund

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)
    before = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()
    client.post(f"/api/v1/contracts/{cid}/change-orders", headers=auth(worker), json={
        "new_amount_cents": 35000, "reason": "加了一个房间",
        "released_cents": 30000, "fee_bps": 0, "signed_by_requester": True,
    })
    after = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()
    assert after["released_cents"] == before["released_cents"]
    assert after["fee_bps"] == before["fee_bps"]


def test_sec067_sdk_create_task_type_matches_the_server_schema():
    """SDK 的 `TaskCreateInput` 与服务端 `TaskIn` 逐字段一致。

    此前参数类型是 `Partial<Task> & {...}`——`id` / `status` / `creator_id` /
    `executor_id` / `created_at` 全在里面。**客户端能发的，应当正好是服务端会收的。**
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "packages" / "core" / "src"
           / "types.ts").read_text(encoding="utf-8")
    m = re.search(r"export interface TaskCreateInput \{(.*?)\n\}", src, re.S)
    assert m, "types.ts 里找不到 TaskCreateInput"
    sdk = set(re.findall(r"^\s+(\w+)\??:", m.group(1), re.M))
    server = _request_schemas()["TaskIn"]
    assert sdk == server, (
        f"SDK 多出：{sorted(sdk - server)}；SDK 缺：{sorted(server - sdk)}"
    )
    assert not (sdk & set(NEVER_ACCEPTED)), "SDK 的创建类型里出现了永不接受的字段"
