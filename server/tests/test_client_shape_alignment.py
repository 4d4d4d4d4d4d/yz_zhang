"""CLI-067 形状也要对上：SDK 的类型/请求体 vs 服务端的真实契约（60 号 spec）。

V82 建的覆盖闸门只看**路径**：端点在不在 SDK 里。两批之内，它没挡住的东西
就出现了两次：

1. `addCertification(name, licenseNo)` 发的请求体服务端**早就不收了**（V76 改的），
   调用必 422；而 SDK 的测试打的是 mock fetch，只验证「我发出的请求长这样」，
   从不验证「服务端认不认」。
2. V82 自己给 `CompliancePath` 写的 TS 类型是错的：声明了 `items`，
   服务端返回的是 `documents` / `registrations` / `notices`。
   **类型对不上，却没有任何东西会红。**

两次都是人眼发现的。所以这一批把「形状」也变成会红的东西：

- 请求体：SDK 里字面量对象的键 vs OpenAPI 的 requestBody schema
- 响应体：SDK 声明的 TS 接口字段 vs **真实响应**的键

响应侧特意用真实响应而不是 OpenAPI：大量端点返回的是手写字典，
OpenAPI 里根本没有 schema（FastAPI 只知道它返回 `dict`）。
**能拿到真东西的时候就别去比声明。**
"""
import json
import re
from pathlib import Path

import pytest

from tests.conftest import JOB_HEADERS, auth, make_admin, register, topup, verify_user
from tests.test_agent_execution import FakeRunner, make_agent, remote_task
from tests.test_task_flow import match_and_fund, publish_task

ROOT = Path(__file__).resolve().parents[2]
TYPES_TS = ROOT / "packages" / "core" / "src" / "types.ts"
CLIENT_TS = ROOT / "packages" / "core" / "src" / "client.ts"


# ----------------------------------------------------------------- TS 接口解析
def _parse_interfaces(src: str) -> dict[str, dict]:
    """从 types.ts 里取出每个 interface 的**顶层**字段（名 → 类型声明）与继承。

    只认顶层：嵌套对象字面量里的字段属于那个子对象，不该被算成本接口的键。
    可选字段（`foo?:`）单独记下来——CLI-068 比类型时，可选字段缺失不算错。
    """
    out: dict[str, dict] = {}
    for m in re.finditer(r"export interface (\w+)(?:\s+extends\s+([\w, ]+))?\s*\{", src):
        name, bases = m.group(1), m.group(2)
        i = src.index("{", m.end() - 1)
        depth, j = 0, i
        while j < len(src):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = src[i + 1:j]
        fields: dict[str, str] = {}
        optional: set[str] = set()
        nested = 0
        for line in body.split("\n"):
            stripped = re.sub(r"//.*$", "", line.strip()).strip()
            if nested == 0 and stripped and not stripped.startswith(("*", "/*")):
                fm = re.match(r"(\w+)(\??)\s*:\s*(.+?);?\s*$", stripped)
                if fm:
                    fields[fm.group(1)] = fm.group(3).rstrip(";").strip()
                    if fm.group(2):
                        optional.add(fm.group(1))
            nested += (line.count("{") + line.count("[")
                       - line.count("}") - line.count("]"))
        out[name] = {"fields": fields, "optional": optional,
                     "bases": [b.strip() for b in (bases or "").split(",") if b.strip()]}
    return out


INTERFACES = _parse_interfaces(TYPES_TS.read_text(encoding="utf-8"))


def _typed(name: str) -> tuple[dict[str, str], set[str]]:
    spec = INTERFACES[name]
    types: dict[str, str] = {}
    optional: set[str] = set()
    for base in spec["bases"]:
        if base in INTERFACES:
            btypes, bopt = _typed(base)
            types.update(btypes)
            optional |= bopt
    types.update(spec["fields"])
    optional |= spec["optional"]
    return types, optional


def _fields(name: str) -> set[str]:
    return set(_typed(name)[0])


def _matches(decl: str, value) -> bool:
    """CLI-068 值的类型对不对得上声明。**刻意宽容**，只抓「类型层级错了」这一类。

    规则克制的理由：**一个假报警多的闸门会被人关掉**（V80 的教训）。
    所以联合类型逐个试、字面量按值比、自定义别名（`IpAssignment`）一律当字符串
    ——**不去解析别名的定义**，那是编译器的活。
    """
    for part in [p.strip() for p in decl.split("|")]:
        if value is None and part in ("null", "undefined"):
            return True
        if isinstance(value, bool) and part == "boolean":
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool) and part == "number":
            return True
        if isinstance(value, str):
            if part == "string" or part.strip("'\"") == value:
                return True
            if part[:1].isupper() or part.startswith("Record<"):
                return True          # 自定义别名/枚举，当字符串处理
        if isinstance(value, list) and (part.endswith("[]") or part.startswith("Array<")):
            return True
        if isinstance(value, dict) and (part.startswith("{") or part.startswith("Record<")
                                        or part in INTERFACES):
            return True
    return False


def test_cli067_interface_parser_actually_works():
    """扫描器自检：解析不出来就恒真（V72 立的规矩）。"""
    assert len(INTERFACES) >= 30, f"只解析出 {len(INTERFACES)} 个接口，解析逻辑可能坏了"
    assert "Task" in INTERFACES and "VentureDetail" in INTERFACES
    # 继承要真的展开
    assert "task_title" in _fields("VerificationOrderDetail")
    assert "status" in _fields("VerificationOrderDetail"), "extends 没有被展开"


# ------------------------------------------------------- CLI-067(a) 响应形状
def _assert_shape(payload: dict, interface: str, *, optional: set[str] = frozenset()):
    """真实响应的键与**值的类型**必须与 TS 接口一致。

    多出来的键 = 客户端拿不到（类型里没有，写代码时看不见）；
    少掉的键 = 客户端以为有（`x.foo` 编译通过，运行时 undefined）；
    类型对不上 = 两边都以为自己是对的。
    三个方向都要红——**只查一边的闸门，另一边就是自由的**。
    """
    declared, ts_optional = _typed(interface)
    actual = set(payload)
    missing = set(declared) - actual - set(optional) - ts_optional
    extra = actual - set(declared)
    assert not missing, f"{interface} 声明了服务端没给的字段：{sorted(missing)}"
    assert not extra, f"服务端给了 {interface} 没声明的字段（客户端看不见它）：{sorted(extra)}"
    wrong = [
        f"{k}: 声明 {declared[k]}，实际 {type(v).__name__}={v!r}"
        for k, v in payload.items()
        if k in declared and not _matches(declared[k], v)
    ]
    assert not wrong, f"{interface} 的字段类型对不上：{wrong}"


@pytest.fixture()
def runner():
    from app.modules.agent.runner import set_runner

    r = FakeRunner()
    set_runner(r)
    yield r
    set_runner(None)


def test_cli067_agent_and_verification_shapes(client, requester, runner):
    admin = make_admin(client, "13800060001")
    agent_id = make_agent(client, admin, confidence_threshold_bps=9000)
    topup(client, requester, 200000)
    task = remote_task(client, requester)
    r = client.post(f"/api/v1/tasks/{task['id']}/agent-apply?agent_user_id={agent_id}",
                    headers=auth(requester))
    cid = client.post(f"/api/v1/applications/{r.json()['id']}/accept",
                      headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(requester))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))

    agents = client.get("/api/v1/agents", headers=auth(requester)).json()
    _assert_shape(agents[0], "AgentProfileView")

    eligible = client.get(f"/api/v1/tasks/{task['id']}/eligible-agents",
                          headers=auth(requester)).json()
    _assert_shape(eligible[0], "EligibleAgent")

    runner.confidence_bps = 4000
    run = client.post(f"/api/v1/tasks/{task['id']}/agent-run", headers=auth(requester)).json()
    # runAgent 的返回多了 delivered / task_status（SDK 里是交叉类型声明的）
    _assert_shape({k: v for k, v in run.items() if k not in ("delivered", "task_status")},
                  "AgentRunView")

    order = client.post(f"/api/v1/tasks/{task['id']}/verification",
                        headers=auth(requester)).json()
    _assert_shape(order, "VerificationOrderView")


def test_cli067_venture_shapes(client):
    from tests.test_early_cooperation import confirm, contribute, join, make_user, make_venture

    founder = make_user(client, "13800060010", "发起人")
    other = make_user(client, "13800060011", "同伴")
    vid = make_venture(client, founder)
    join(client, vid, other)
    contribute(client, vid, founder)

    detail = client.get(f"/api/v1/ventures/{vid}", headers=auth(founder)).json()
    _assert_shape(detail, "VentureDetail")

    mine = client.get("/api/v1/ventures/mine", headers=auth(founder)).json()
    # 列表项多一个 role（SDK 里同样是交叉类型）
    _assert_shape({k: v for k, v in mine[0].items() if k != "role"}, "VentureView")

    contribs = client.get(f"/api/v1/ventures/{vid}/contributions", headers=auth(founder)).json()
    _assert_shape(contribs[0], "ContributionView")

    # **这就是当初写错的那个**：声明的是 items，实际是 documents/registrations/notices
    path = client.get(f"/api/v1/ventures/{vid}/compliance-path", headers=auth(founder)).json()
    _assert_shape(path, "CompliancePath")

    disclosure = client.get("/api/v1/ventures/risk-disclosure").json()
    _assert_shape(disclosure, "RiskDisclosure")


def test_cli067_team_shapes(client):
    owner = register(client, "13800060020", "队长")
    verify_user(client, owner, name="队长")
    member = register(client, "13800060021", "队员")
    verify_user(client, member, name="队员")
    team_id = client.post("/api/v1/teams", json={"name": "设计组"},
                          headers=auth(owner)).json()["id"]
    client.post(f"/api/v1/teams/{team_id}/members",
                json={"user_id": member["id"], "role": "member", "spend_limit_cents": 1000},
                headers=auth(owner))
    client.post(f"/api/v1/teams/{team_id}/spends",
                json={"amount_cents": 5000, "purpose": "买素材", "task_id": None},
                headers=auth(member))

    _assert_shape(client.get(f"/api/v1/teams/{team_id}", headers=auth(owner)).json(), "TeamDetail")
    mine = client.get("/api/v1/teams/mine", headers=auth(owner)).json()
    _assert_shape({k: v for k, v in mine[0].items()
                   if k not in ("my_role", "my_spend_limit_cents")}, "TeamView")
    spends = client.get(f"/api/v1/teams/{team_id}/spends", headers=auth(owner)).json()
    _assert_shape(spends[0], "SpendRequestView")


def test_cli067_developer_shapes(client, requester):
    client.post("/api/v1/developer/api-keys",
                json={"name": "集成", "scopes": ["tasks:read"]}, headers=auth(requester))
    keys = client.get("/api/v1/developer/api-keys", headers=auth(requester)).json()
    _assert_shape(keys[0], "ApiKeyView")

    hook = client.post("/api/v1/developer/webhooks",
                       json={"url": "https://example.com/cb", "events": ["task.completed"]},
                       headers=auth(requester)).json()
    hooks = client.get("/api/v1/developer/webhooks", headers=auth(requester)).json()
    _assert_shape(hooks[0], "WebhookView")

    # 造一条投递记录：完成一单任务会触发事件
    worker = register(client, "13800060030", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    client.post("/api/v1/openapi/jobs/deliver-webhooks", headers=JOB_HEADERS)

    rows = client.get(f"/api/v1/developer/webhooks/{hook['id']}/deliveries",
                      headers=auth(requester)).json()
    if rows:
        _assert_shape(rows[0], "WebhookDeliveryView")


def test_cli067_certification_shape(client):
    from tests.test_certification import apply_cert, make_verified

    user = make_verified(client, "13800060040")
    assert apply_cert(client, user).status_code == 201
    body = client.get("/api/v1/users/me/certifications", headers=auth(user)).json()
    _assert_shape(body["applications"][0], "CertificationApplicationView")


# ------------------------------------------------------- CLI-067(b) 请求形状
def _split_args(text: str) -> list[str]:
    args, depth, buf, i, quote = [], 0, [], 0, None
    while i < len(text):
        c = text[i]
        if quote:
            buf.append(c)
            if c == "\\":
                i += 1
                if i < len(text):
                    buf.append(text[i])
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
            buf.append(c)
        elif c in "([{":
            depth += 1
            buf.append(c)
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
            buf.append(c)
        elif c == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(c)
        i += 1
    args.append("".join(buf).strip())
    return args


def _literal_body_keys(body: str) -> set[str] | None:
    """字面量对象的顶层键；不是字面量（变量、展开）就返回 None（跳过）。"""
    body = body.strip()
    if not body.startswith("{"):
        return None
    inner = body[1:-1]
    if "..." in inner:
        return None
    keys = set()
    for seg in re.split(r",(?![^{\[(]*[}\])])", inner):
        seg = seg.strip()
        m = re.match(r"^(\w+)\s*:", seg) or re.match(r"^(\w+)$", seg)
        if m:
            keys.add(m.group(1))
        elif seg:
            return None
    return keys


def _norm(path: str) -> str:
    p = re.sub(r"\{[^}]*\}", "{x}", path).split("?")[0]
    segs = []
    for seg in p.split("/"):
        if seg and seg != "{x}" and "{x}" in seg:
            seg = seg.replace("{x}", "")
        segs.append(seg)
    return "/".join(segs).rstrip("/") or "/"


def _sdk_calls() -> list[tuple[str, str, str | None]]:
    src = CLIENT_TS.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"this\.request<", src):
        i = src.index("(", m.end())
        args = _split_args(src[i + 1:])
        if len(args) < 2:
            continue
        verb = args[0].strip().strip("'\"")
        path = args[1].strip()
        if not (path.startswith("`") or path.startswith("'")):
            continue
        literal = re.sub(r"\$\{[^{}]*(\{[^{}]*\}[^{}]*)*\}", "{x}", path[1:-1])
        out.append((verb, _norm(literal), args[2].strip() if len(args) > 2 else None))
    return out


def test_cli067_request_bodies_match_the_server_schema():
    """SDK 发的每个字面量请求体，键必须是服务端 schema 认的，且必填项不能少。

    改造前 `addCertification` 发的是 `{name, license_no}`，而服务端 V76 起
    要的是 `{name, holder_name, cert_number, images, ...}`——**调用必 422**，
    没有任何测试会红。
    """
    from app.main import app

    spec = app.openapi()
    schemas = spec.get("components", {}).get("schemas", {})
    by_route: dict[tuple[str, str], tuple[set[str], set[str], str]] = {}
    for path, ops in spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for verb, op in ops.items():
            ref = ((op.get("requestBody") or {}).get("content", {})
                   .get("application/json", {}).get("schema", {}).get("$ref"))
            if not ref:
                continue
            sch = schemas.get(ref.split("/")[-1], {})
            by_route[(verb.upper(), _norm(path[len("/api/v1"):]))] = (
                set(sch.get("properties", {})), set(sch.get("required", [])),
                ref.split("/")[-1],
            )

    calls = _sdk_calls()
    assert len(calls) >= 150, f"只扫到 {len(calls)} 个 SDK 调用，扫描逻辑可能坏了"

    checked, problems = 0, []
    for verb, path, body in calls:
        route = by_route.get((verb, path))
        if not route:
            continue
        props, required, schema_name = route
        keys = _literal_body_keys(body) if body else set()
        if keys is None:
            continue           # 动态请求体（透传的 patch / 展开），本闸门管不到
        checked += 1
        extra = keys - props
        missing = required - keys
        if extra or missing:
            problems.append(f"{verb} {path} ({schema_name}) 多发={sorted(extra)} 漏发={sorted(missing)}")
    # 自检：一条都没比过说明白跑了
    assert checked >= 40, f"只比对了 {checked} 个请求体，闸门可能形同虚设"
    assert not problems, "SDK 的请求体与服务端 schema 对不上：\n  " + "\n  ".join(problems)


# ------------------------------------------- CLI-070 闸门扩到老接口
def test_cli070_core_domain_shapes(client, requester):
    """V85 的闸门只盯着 V73~V79 那六条新线，把同样的比对跑一遍老接口，
    立刻掉出两条：`Task` 声明了 `bonus_cents` / `ip_assignment` 而服务端不返回，
    `Me` 返回了三个类型里没有的字段。

    老接口没有一次性对齐过，闸门第一次覆盖它们时掉出东西是正常的——
    **把它们修掉、然后不许再漂**，这正是目的。
    """
    worker = register(client, "13800064001", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    contract_id = match_and_fund(client, requester, worker, task)

    detail = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    # 详情视角字段只在 GET /tasks/{id} 出现，列表里没有——它们在 TS 里是可选的
    _assert_shape(detail, "Task")
    # 广场列表里的任务是另一条序列化路径（没有详情视角字段），单独比一次
    listed = publish_task(client, requester, title="另一单保洁")
    rows = client.get("/api/v1/tasks", headers=auth(worker)).json()
    assert any(t["id"] == listed["id"] for t in rows), "刚发布的任务不在广场上"
    _assert_shape([t for t in rows if t["id"] == listed["id"]][0], "Task")
    _assert_shape(client.get(f"/api/v1/contracts/{contract_id}",
                             headers=auth(requester)).json(), "Contract",
                  optional={"milestones"})
    _assert_shape(client.get("/api/v1/wallet", headers=auth(requester)).json(), "Wallet")
    _assert_shape(client.get("/api/v1/users/me", headers=auth(requester)).json(), "Me")


def test_cli073_wallet_money_out_shapes(client, requester):
    """PAY-030 提现这条路上的两个形状：收款账户与账单流水。

    它们此前在 SDK 里是**行内匿名类型**，闸门够不着；而这条路正是
    「钱能进不能出」那批要修的——修完就得钉住，别再漂回去。
    """
    topup(client, requester, 100000)
    _assert_shape(client.get("/api/v1/wallet/payout-account",
                             headers=auth(requester)).json(), "PayoutAccountView")
    client.put("/api/v1/wallet/payout-account",
               # PAY-005 收款人姓名必须与实名一致（防代提/洗钱），
               # 所以这里用的是 verify_user 的默认实名，不是昵称
               json={"kind": "bank", "account_no": "6222020000001111", "holder_name": "张三"},
               headers=auth(requester))
    bound = client.get("/api/v1/wallet/payout-account", headers=auth(requester)).json()
    _assert_shape(bound, "PayoutAccountView")
    assert "*" in bound["account_no"], "回显了完整卡号"

    rows = client.get("/api/v1/wallet/ledger", headers=auth(requester)).json()
    assert rows, "充值之后账单流水是空的"
    _assert_shape(rows[0], "LedgerRow")


def test_cli075_safety_shapes(client, requester):
    """GEO-023/022 求助与行程分享的响应形状。

    这两个此前**声明得完全不对**（`sos` 声明成 `{id, notified}`，
    服务端给的是 `{ok, guidance}`），而错了这么久没人发现，
    因为**两端都没有任何一处调用过它们**——V89 的闸门也够不着，
    那时它们还是 SDK 里的行内匿名类型。
    """
    worker = register(client, "13800064200", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    sos = client.post(f"/api/v1/tasks/{task['id']}/sos",
                      json={"lat": 31.2, "lng": 121.5}, headers=auth(worker)).json()
    _assert_shape(sos, "SosResult")


def test_cli070_dispute_and_message_shapes(client, requester):
    worker = register(client, "13800064010", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 200000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付不符约定，要求重做"}, headers=auth(requester)).json()
    _assert_shape(d, "Dispute")
    client.post(f"/api/v1/disputes/{d['id']}/statements",
                json={"content": "我方已按约定交付，附证据"}, headers=auth(worker))
    rows = client.get(f"/api/v1/disputes/{d['id']}/statements", headers=auth(worker)).json()
    _assert_shape(rows[0], "DisputeStatement")

    notices = client.get("/api/v1/notifications", headers=auth(worker)).json()
    items = notices if isinstance(notices, list) else notices.get("items", [])
    if items:
        _assert_shape(items[0], "Notice")


def test_cli070_mission_shapes(client, requester):
    """V86 刚给 Mission 加了 `allow_agents`、给 MissionStep 加了 `agent_user_id`。
    闸门覆盖到这里，它们有没有同步进类型就不再靠人记得。"""
    topup(client, requester, 100000)
    m = client.post("/api/v1/missions", json={
        "goal": "搬家统筹", "detail": "", "category": "跑腿",
        "budget_cap_cents": 30000, "max_iterations": 3, "acceptance_criteria": [],
    }, headers=auth(requester)).json()
    _assert_shape(m, "Mission")

    client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester))
    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()
    if detail["steps"]:
        _assert_shape(detail["steps"][0], "MissionStep")


def test_cli068_type_mismatch_is_caught():
    """类型闸门自己的红验：声明 number 而给字符串，必须红。

    不靠「以后有人写错时才知道」——**闸门本身要被验证过会红**。
    """
    import pytest as _pytest

    with _pytest.raises(AssertionError, match="类型对不上"):
        _assert_shape({"available_cents": "200", "escrow_cents": 0, "frozen_cents": 0}, "Wallet")
    # 可选字段缺失不报警
    _assert_shape({"id": 1, "category": "system", "title": "t", "body": "b",
                   "is_read": False, "created_at": "2026-09-21T00:00:00Z"}, "Notice")
