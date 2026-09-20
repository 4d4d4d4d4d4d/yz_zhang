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
    """从 types.ts 里取出每个 interface 的**顶层**字段名与它继承的接口。

    只认顶层：嵌套对象字面量里的字段属于那个子对象，不该被算成本接口的键。
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
        fields, nested = [], 0
        for line in body.split("\n"):
            stripped = line.strip()
            if nested == 0:
                fm = re.match(r"(\w+)\??\s*:", stripped)
                if fm:
                    fields.append(fm.group(1))
            nested += (line.count("{") + line.count("[")
                       - line.count("}") - line.count("]"))
        out[name] = {"fields": fields,
                     "bases": [b.strip() for b in (bases or "").split(",") if b.strip()]}
    return out


INTERFACES = _parse_interfaces(TYPES_TS.read_text(encoding="utf-8"))


def _fields(name: str) -> set[str]:
    spec = INTERFACES[name]
    out = set(spec["fields"])
    for base in spec["bases"]:
        if base in INTERFACES:
            out |= _fields(base)
    return out


def test_cli067_interface_parser_actually_works():
    """扫描器自检：解析不出来就恒真（V72 立的规矩）。"""
    assert len(INTERFACES) >= 30, f"只解析出 {len(INTERFACES)} 个接口，解析逻辑可能坏了"
    assert "Task" in INTERFACES and "VentureDetail" in INTERFACES
    # 继承要真的展开
    assert "task_title" in _fields("VerificationOrderDetail")
    assert "status" in _fields("VerificationOrderDetail"), "extends 没有被展开"


# ------------------------------------------------------- CLI-067(a) 响应形状
def _assert_shape(payload: dict, interface: str, *, optional: set[str] = frozenset()):
    """真实响应的键必须与 TS 接口声明的字段一致。

    多出来的键 = 客户端拿不到（类型里没有，写代码时看不见）；
    少掉的键 = 客户端以为有（`x.foo` 编译通过，运行时 undefined）。
    两个方向都要红——**只查一边的闸门，另一边就是自由的**。
    """
    declared = _fields(interface)
    actual = set(payload)
    missing = declared - actual - optional
    extra = actual - declared
    assert not missing, f"{interface} 声明了服务端没给的字段：{sorted(missing)}"
    assert not extra, f"服务端给了 {interface} 没声明的字段（客户端看不见它）：{sorted(extra)}"


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
