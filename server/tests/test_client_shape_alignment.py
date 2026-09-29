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


# CLI-071 嵌套多深还比：再深就退回宽容。
#
# 两层足够覆盖这个仓里实际出现的形状（`Array<{...}>`、`{ wallet: {...} }`），
# 而无限递归下去，遇到自引用类型会转不出来。**闸门要能停。**
MAX_NEST_DEPTH = 2


def _split_top_level(body: str, sep: str = ";") -> list[str]:
    """按分隔符切，但不切进括号里。

    `{ a: Array<{ b: number }>; c: string }` 直接 `split(";")` 会把
    内层切开——第一版就是这么写的，于是解析出一堆残缺字段。
    """
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch in "{[<(":
            depth += 1
        elif ch in "}]>)":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _inline_fields(decl: str) -> dict[str, str] | None:
    """把内联对象字面量解析成「字段 → 类型声明」。

    认三种写法：`{ a: number }`、`Array<{ a: number }>`、`{ a: number }[]`。
    认不出来就返回 None——调用方据此退回宽容，而不是报一个假警报。
    """
    d = decl.strip()
    if d.startswith("Array<") and d.endswith(">"):
        d = d[len("Array<"):-1].strip()
    if d.endswith("[]"):
        d = d[:-2].strip()
    if not (d.startswith("{") and d.endswith("}")):
        return None
    fields: dict[str, str] = {}
    for item in _split_top_level(d[1:-1]):
        fm = re.match(r"(\w+)(\??)\s*:\s*(.+)$", item)
        if not fm:
            return None              # 有一项看不懂就整体放弃，不猜
        fields[fm.group(1) + ("?" if fm.group(2) else "")] = fm.group(3).strip()
    return fields or None


def _element_decl(decl: str) -> str | None:
    """数组声明的元素类型；不是数组就返回 None。"""
    d = decl.strip()
    if d.startswith("Array<") and d.endswith(">"):
        return d[len("Array<"):-1].strip()
    if d.endswith("[]"):
        return d[:-2].strip()
    return None


def _object_fields(part: str) -> dict[str, str] | None:
    """一个类型声明对应的字段表：内联字面量，或者具名 interface。"""
    inline = _inline_fields(part)
    if inline is not None:
        return inline
    if part in INTERFACES:
        types, optional = _typed(part)
        return {k + ("?" if k in optional else ""): v for k, v in types.items()}
    return None


def _dict_matches(fields: dict[str, str], value: dict, depth: int) -> bool:
    """嵌套对象：声明的必选键要在、类型要对、也不许有没声明的键。

    三个方向与顶层同一套政策（`_assert_shape` 的那三条）——
    **只查一边的闸门，另一边就是自由的。**
    """
    declared = {k.rstrip("?"): v for k, v in fields.items()}
    optional = {k.rstrip("?") for k in fields if k.endswith("?")}
    if set(declared) - set(value) - optional:
        return False
    if set(value) - set(declared):
        return False
    return all(_matches(d, value[k], depth + 1)
               for k, d in declared.items() if k in value)


def _matches(decl: str, value, depth: int = 0) -> bool:
    """CLI-068/071 值的类型对不对得上声明。**刻意宽容**，只抓「类型层级错了」这一类。

    规则克制的理由：**一个假报警多的闸门会被人关掉**（V80 的教训）。
    所以联合类型逐个试、字面量按值比、解析不了的声明一律放过
    ——**不去解析别名的定义**，那是编译器的活。

    CLI-071（V105 补）：数组元素与内联对象**也比**。此前这两类一律返回 True，
    于是 `Array<{ role: string }>` 里把 `role` 写成 `number` 没有任何东西会红
    （探针实测：两个字段同时写错，15 条形状测试全绿）。
    """
    parts = _split_top_level(decl, "|")
    for part in parts:
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
        if isinstance(value, list):
            elem = _element_decl(part)
            if elem is None:
                continue
            if depth >= MAX_NEST_DEPTH or not value:
                return True          # 太深、或空数组：无从比较，放过
            # 只看前几个：同一个列表里的元素形状一致，全比一遍只是更慢
            return all(_matches(elem, v, depth + 1) for v in value[:5])
        if isinstance(value, dict):
            if part.startswith("Record<"):
                return True          # 键未知，无从比较
            fields = _object_fields(part)
            if fields is None:
                # 解析不了的具名类型（别名、泛型实例化…）：**放过**。
                # 不放过的话，`Array<SomeAlias>` 会变成一条假警报——
                # 而那正是这套闸门最怕的东西（V80：假报警多的闸门会被人关掉）。
                # 这一条是我自己写的测试当场抓出来的。
                if part[:1].isupper():
                    return True
                continue
            if depth >= MAX_NEST_DEPTH:
                return True
            return _dict_matches(fields, value, depth)
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


# CLI-072（V105 补）：请求体是个**变量**时，它的类型标注就是契约。
#
# 探针：73 条字面量请求体被比过，另外 11 条被静默跳过——它们的 body 是
# `patch` / `input` / `body` 这样的参数名。而这些参数都是**有类型标注的**：
#
#     editTask(id: number, patch: Partial<{ title: string; ... }>)
#
# 所以能比：SDK 可能发出去的键，必须是服务端 schema 认的。
# 这正是 `addCertification` 那一类（SDK 发的键服务端不认，调用必 422）。


def _method_params(src: str, call_index: int) -> str:
    """从 `this.request<` 往回找到所在方法的参数表原文。"""
    head = src.rfind("\n  ", 0, call_index)
    while head > 0:
        line_start = head + 3
        if re.match(r"[a-zA-Z_]\w*\s*[(<]", src[line_start:line_start + 40]):
            # 参数表可能跨多行：从第一个 ( 配对到对应的 )
            i = src.index("(", line_start)
            depth, j = 0, i
            while j < len(src):
                if src[j] in "([{<":
                    depth += 1
                elif src[j] in ")]}>":
                    depth -= 1
                    if depth == 0:
                        return src[i + 1:j]
                j += 1
            return ""
        head = src.rfind("\n  ", 0, head)
    return ""


def _param_type(params: str, name: str) -> str | None:
    """参数表里某个参数的类型标注原文。"""
    for arg in _split_top_level(params, ","):
        m = re.match(rf"{re.escape(name)}\s*:\s*(.+)$", arg.strip(), re.S)
        if m:
            return m.group(1).strip().rstrip("=").strip()
    return None


def _resolve_body_keys(expr: str) -> tuple[set[str], bool]:
    """类型表达式 -> (可能发出去的键, 是否完全解析)。

    认得四种：内联 `{...}`、`Partial<...>`、`Pick<Iface, 'a' | 'b'>`、具名 interface。
    **`Partial<具名 interface>` 刻意算作"没解析"**：`Partial<Task>` 比创建
    schema 宽得多（`id`/`status`/`created_at` 都在里面），逐键比会是一堆假警报。
    那个"宽"本身是 SDK 的设计问题，记在台账里，而不是用假警报去逼它。
    """
    keys: set[str] = set()
    resolved = True
    for part in _split_top_level(expr, "&"):
        part = part.strip()
        inline = _inline_fields(part)
        if inline is not None:
            keys |= {k.rstrip("?") for k in inline}
            continue
        pm = re.match(r"Partial<(.+)>$", part, re.S)
        if pm:
            inner = pm.group(1).strip()
            sub_inline = _inline_fields(inner)
            if sub_inline is not None:
                keys |= {k.rstrip("?") for k in sub_inline}
                continue
            pick = re.match(r"Pick<\s*(\w+)\s*,(.+)>$", inner, re.S)
            if pick:
                keys |= {k.strip().strip("'\"") for k in pick.group(2).split("|")}
                continue
            resolved = False        # Partial<具名接口>：太宽，不比
            continue
        pick = re.match(r"Pick<\s*(\w+)\s*,(.+)>$", part, re.S)
        if pick:
            keys |= {k.strip().strip("'\"") for k in pick.group(2).split("|")}
            continue
        if part in INTERFACES:
            keys |= set(_typed(part)[0])
            continue
        resolved = False
    return keys, resolved


# 解析不了的请求体 -> 为什么（值是**理由**，不是布尔）
DYNAMIC_BODY: dict[tuple[str, str], str] = {
    ("POST", "/tasks"): (
        "参数类型是 `Partial<Task> & {...}`，它比创建 schema 宽得多"
        "（`id` / `status` / `created_at` 都在里面）。逐键比会是一堆假警报；"
        "这个宽度本身是 SDK 的设计问题，记在 72 号台账的 SYNC-050 那条线上"
    ),
    ("POST", "/tasks/{x}/applications"): (
        "请求体里有条件展开（`...(bidCents ? { bid_cents } : {})`），"
        "静态读不出稳定的键集合；两个键都很稳定，值得的话该把签名改成显式两参"
    ),
}


def test_cli072_variable_request_bodies_are_checked_or_declared():
    """请求体是变量时，用**它的类型标注**比；解析不了的必须在表里写明理由。

    改造前这 11 条是**静默跳过**的——闸门报了「比对了 73 个请求体」，
    听起来很齐全，而另外 11 条从来没人看。
    """
    from app.main import app

    spec = app.openapi()
    schemas = spec.get("components", {}).get("schemas", {})
    by_route: dict[tuple[str, str], set[str]] = {}
    for path, ops in spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for verb, op in ops.items():
            ref = ((op.get("requestBody") or {}).get("content", {})
                   .get("application/json", {}).get("schema", {}).get("$ref"))
            if ref:
                sch = schemas.get(ref.split("/")[-1], {})
                by_route[(verb.upper(), _norm(path[len("/api/v1"):]))] = set(
                    sch.get("properties", {}))

    src = CLIENT_TS.read_text(encoding="utf-8")
    checked, problems, undeclared = 0, [], []
    for m in re.finditer(r"this\.request<", src):
        i = src.index("(", m.end())
        args = _split_args(src[i + 1:])
        if len(args) < 3:
            continue
        verb = args[0].strip().strip("'\"")
        path = args[1].strip()
        if not (path.startswith("`") or path.startswith("'")):
            continue
        literal = re.sub(r"\$\{[^{}]*(\{[^{}]*\}[^{}]*)*\}", "{x}", path[1:-1])
        route = (verb, _norm(literal))
        props = by_route.get(route)
        if props is None:
            continue
        body = args[2].strip()
        if _literal_body_keys(body) is not None:
            continue                      # 字面量请求体由上一条闸门比
        # 变量请求体：拿它的类型标注来比
        if not re.match(r"^[a-zA-Z_]\w*$", body):
            if route not in DYNAMIC_BODY:
                undeclared.append(f"{verb} {route[1]} body={body[:40]}")
            continue
        params = _method_params(src, m.start())
        decl = _param_type(params, body) if params else None
        if decl is None:
            if route not in DYNAMIC_BODY:
                undeclared.append(f"{verb} {route[1]} 的 {body} 没有类型标注")
            continue
        keys, resolved = _resolve_body_keys(decl)
        if not resolved:
            if route not in DYNAMIC_BODY:
                undeclared.append(f"{verb} {route[1]} 的类型 {decl[:40]} 解析不了")
            continue
        checked += 1
        extra = keys - props
        if extra:
            problems.append(f"{verb} {route[1]} 可能发出服务端不认的键：{sorted(extra)}")

    assert checked >= 6, f"只比了 {checked} 个变量请求体，解析逻辑可能坏了"
    assert not undeclared, (
        "这些请求体静态读不出来，也没在 DYNAMIC_BODY 里写明理由：\n  "
        + "\n  ".join(undeclared)
    )
    assert not problems, "SDK 的参数类型允许发出服务端不认的键：\n  " + "\n  ".join(problems)


def test_cli072_declared_table_has_no_stale_entries():
    """表里留着已经能比的路由，就会掩护掉真正该被看的那些。"""
    from app.main import app

    paths = {(v.upper(), _norm(p[len("/api/v1"):]))
             for p, ops in app.openapi()["paths"].items() if p.startswith("/api/v1")
             for v in ops}
    stale = sorted(r for r in DYNAMIC_BODY if r not in paths)
    assert not stale, f"DYNAMIC_BODY 里这些路由已经不在服务端了：{stale}"
    for route, why in DYNAMIC_BODY.items():
        assert len(why) >= 20, f"{route} 的理由太短：{why}"


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


def test_cli077_admin_review_shapes(client):
    """PAY-040 / AML-021 管理端两个形状。

    管理后台**整体在覆盖闸门之外**（`_server_paths` 跳过 `/admin`），
    所以这两个形状此前没有任何东西看着。建的时候就进闸门。
    """
    from tests.conftest import make_admin
    from tests.test_withdraw_review_loop import _pending_withdraw

    _u, admin, _rid = _pending_withdraw(client, "13800064400", "13800064409")
    rows = client.get("/api/v1/wallet/withdraw-requests?status=pending",
                      headers=auth(admin)).json()
    _assert_shape(rows[0], "WithdrawRequestRow")

    items = client.get("/api/v1/admin/aml/activities?status=pending",
                       headers=auth(admin)).json()["items"]
    assert items, "大额提现进人审却没有留下可疑活动记录"
    _assert_shape(items[0], "SuspiciousActivityRow")


def test_cli076_change_order_shape(client, requester):
    """SC-007 变更单列表的形状。这个接口是 V95 新建的——
    **建的时候就进闸门**，别等它漂了才补。"""
    worker = register(client, "13800064300", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 300000)
    topup(client, worker, 100000)
    task = publish_task(client, requester)
    cid = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/contracts/{cid}/change-orders",
                json={"new_amount_cents": 30000, "reason": "加了两个房间"},
                headers=auth(requester))
    rows = client.get(f"/api/v1/contracts/{cid}/change-orders", headers=auth(worker)).json()
    _assert_shape(rows[0], "ChangeOrderView")


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


def test_cli071_nested_types_are_compared():
    """CLI-071 数组元素与内联对象里的类型也要比。

    这是这套闸门挂了很久的盲区：此前 `list` 与 `dict` 一律返回 True，
    于是把 `Array<{ role: string }>` 的 `role` 改成 `number`、
    再把 `spend_limit_cents` 改成 `boolean`，**15 条形状测试全绿**（探针实测）。
    """
    # 元素里的类型错了 → 红
    assert not _matches("Array<{ a: number; b: string }>", [{"a": 1, "b": 2}])
    assert _matches("Array<{ a: number; b: string }>", [{"a": 1, "b": "x"}])
    # 元素里少了声明的键 / 多了没声明的键 → 都红（与顶层同一套政策）
    assert not _matches("Array<{ a: number; b: string }>", [{"a": 1}])
    assert not _matches("Array<{ a: number }>", [{"a": 1, "unexpected": 2}])
    # 可选键缺失不算错
    assert _matches("Array<{ a: number; b?: string }>", [{"a": 1}])
    # `X[]` 写法与 `Array<X>` 等价
    assert not _matches("{ a: number }[]", [{"a": "1"}])
    # 内联对象（不在数组里）同样比
    assert not _matches("{ available_cents: number }", {"available_cents": "200"})
    assert _matches("{ available_cents: number }", {"available_cents": 200})
    # 具名 interface 作为嵌套类型时也展开比
    assert not _matches("Wallet", {"available_cents": "x", "escrow_cents": 0, "frozen_cents": 0})


def test_cli071_stays_permissive_where_it_cannot_know():
    """宽容的边界要写清楚：**一个假报警多的闸门会被人关掉。**"""
    # 空数组：无从比较
    assert _matches("Array<{ a: number }>", [])
    # Record<>：键未知
    assert _matches("Record<string, number>", {"anything": 1})
    # 解析不出来的元素声明：放过而不是报错
    assert _matches("Array<SomeAliasWeDoNotParse>", [{"a": 1}])
    # 超过两层：退回宽容（自引用类型不能让闸门转不出来）
    deep = "Array<{ a: Array<{ b: Array<{ c: number }> }> }>"
    assert _matches(deep, [{"a": [{"b": [{"c": "wrong-but-too-deep"}]}]}])


def test_cli071_splitter_does_not_cut_inside_brackets():
    """`split(";")` 会把内层对象切开——第一版就是这么解析出一堆残缺字段的。"""
    fields = _inline_fields("{ a: Array<{ b: number; c: string }>; d: string }")
    assert fields == {"a": "Array<{ b: number; c: string }>", "d": "string"}
    # 联合类型也不能被内层的 | 带跑
    assert _split_top_level("Array<{ a: number | null }> | null", "|") == \
        ["Array<{ a: number | null }>", "null"]


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
