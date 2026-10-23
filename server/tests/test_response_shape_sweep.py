"""CLI-083 响应形状的整条扫除：SDK 声明 vs 服务端真实返回（100 号 spec）。

V85 建了响应形状闸门，它的 docstring 原话是「类型对不上，却没有任何东西会红」。
V122 量了一下它实际管多少：

    this.request< 调用点         281 个
    _assert_shape 真的比过的接口   26 个

**覆盖 26/281，而响应侧没有任何记账说这件事。** 那次是因为要用
`knowledgeCards` 才撞见它的声明是错的（写着服务端从没给过的 `body`）。

V85 的手写案例要造真数据、一个端点一个端点地跑，所以覆盖面天然很窄。
这里换一个来源：**服务端处理函数里 `return {...}` 的字面量本身就是契约**——
161/321 个 handler 直接返回字面量 dict，另有 37 个返回字面量 dict 的列表推导。
读出它们的键，与 SDK 声明的字段比，两边都不用造数据。

第一次跑就扫出 **10 处真实对不上**，其中一处是法律后果：
`exportEvidence` 的 `evidentiary_notice`（证明力边界说明，含「平台处理决定
**不是**仲裁裁决」那一句）SDK 没声明，于是网页下载证据包时用
`{...package, sha256}` 拼文件，把它整个丢掉了——用户交给律师的那份文件里，
没有任何一句话说明它能证明什么、不能证明什么。

这一篇的覆盖仍然不是 281/281：返回 `dump_task(...)` 这类调用、返回变量的
handler，静态读不出键。那部分不假装覆盖了——**用棘轮钉住它的数目，只许降不许升**。
"""
import ast
import inspect
import re
import textwrap


from tests.test_client_shape_alignment import (
    CLIENT_TS, INTERFACES, _element_decl, _inline_fields, _norm, _split_args, _typed,
)

# ------------------------------------------------------------------ 豁免
# 静态比不了、且**有正当理由**比不了的调用点 → 为什么。值是理由，不是布尔。
EXEMPT: dict[str, str] = {
    "decideWithdraw":
        "路径最后一段是 `${decision}`（approve / reject），一个 SDK 方法对应两条路由；"
        "两条路由各自的形状由 test_aml / test_withdraw_review 的真实响应断言覆盖",
    "exportMyData":
        "数据可携导出按用户实际拥有的数据动态组装，刻意声明成 Record<string, unknown>；"
        "给它定死字段反而会让新加的数据类别在类型里不可见",
}

# 静态读不出、也没有真实响应断言覆盖的调用点数目——**只许降不许升**。
#
# 这个数不是目标，是现状。它存在的意义是：新加一个返回 `dump_xxx(...)`
# 的端点而没有任何形状检查，这里会红，逼着去补一条真实响应断言，
# 或者把 handler 改成返回字面量。降下来的时候请同步改小这个数。
MAX_UNVERIFIED = 103


# ------------------------------------------------------------------ 解析
def _replace_template_exprs(path: str) -> str:
    """把模板字符串里的每个 `${...}` 换成 `{x}`——**按括号配平扫，不用正则**。

    正则版在 `${qs ? `?${qs}` : ''}` 这种嵌套模板上会切错位置，
    于是 `updateCategory` 被算成打 `/admin/categories`（一条不存在的路由），
    一个假报警。连续的占位（`/{x}{x}`，后一个通常是查询串）收成一个。
    """
    out, i = [], 0
    while i < len(path):
        if path.startswith("${", i):
            depth, j = 0, i + 1
            while j < len(path):
                if path[j] == "{":
                    depth += 1
                elif path[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append("{x}")
            i = j + 1
        else:
            out.append(path[i])
            i += 1
    s = "".join(out)
    while "{x}{x}" in s:
        s = s.replace("{x}{x}", "{x}")
    return s


def _sdk_calls() -> list[tuple[str, str, str, str]]:
    """(方法名, 动词, 归一化路径, 响应类型原文)。"""
    src = CLIENT_TS.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"this\.request<", src):
        i = m.end()
        depth, j = 1, i
        while j < len(src) and depth:
            if src[j] == "<":
                depth += 1
            elif src[j] == ">":
                depth -= 1
            j += 1
        decl = src[i:j - 1].strip()
        k = src.index("(", j - 1)
        args = _split_args(src[k + 1:])
        if len(args) < 2:
            continue
        verb = args[0].strip().strip("'\"")
        path = args[1].strip()
        if path[:1] not in "`'\"":
            continue
        literal = _replace_template_exprs(path[1:-1])
        # `async` 也要认：第一版漏了它，`apiScopes` 的不一致被算到了
        # 上一个方法 `addOrganizationRecord` 头上
        names = list(re.finditer(r"\n  (?:async\s+)?([a-zA-Z][a-zA-Z0-9_]*)\s*[(<]",
                                 src[:m.start()]))
        out.append((names[-1].group(1) if names else "?", verb, _norm(literal), decl))
    return out


def _server_routes() -> dict[tuple[str, str], object]:
    """(动词, 归一化路径) → handler。递归走进 include 进来的子路由。"""
    from fastapi.routing import APIRoute

    from app.main import app

    def walk(routes, prefix=""):
        for r in routes:
            if isinstance(r, APIRoute):
                yield prefix + r.path, r
            elif hasattr(r, "original_router"):
                yield from walk(r.original_router.routes,
                                prefix + (r.include_context.prefix or ""))

    out = {}
    for full, r in walk(app.routes):
        if full.startswith("/api/v1"):
            for v in r.methods:
                out[(v, _norm(full[len("/api/v1"):]))] = r.endpoint
    return out


def _server_shapes(fn) -> tuple[list[set[str]] | None, str]:
    """handler 所有 `return` 的字面量键集合；有一处不是字面量就说读不出、为什么。"""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError):
        return None, "无源码"
    fn_node = tree.body[0]
    shapes: list[set[str]] = []
    for node in ast.walk(fn_node):
        # 嵌套函数里的 return 不是这个 handler 的返回
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) \
                and node is not fn_node:
            continue
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        v = node.value.elt if isinstance(node.value, ast.ListComp) else node.value
        if isinstance(v, ast.Dict) and None not in v.keys \
                and all(isinstance(k, ast.Constant) for k in v.keys):
            shapes.append({k.value for k in v.keys})
        else:
            return None, type(node.value).__name__
    return (shapes, "literal") if shapes else (None, "无字面量返回")


def _sdk_fields(decl: str) -> tuple[set[str], set[str]] | None:
    elem = _element_decl(decl)
    fields = _inline_fields(elem or decl)
    if fields is not None:
        return ({k.rstrip("?") for k in fields},
                {k.rstrip("?") for k in fields if k.endswith("?")})
    name = (elem or decl).strip()
    if name in INTERFACES:
        types, optional = _typed(name)
        return set(types), set(optional)
    return None


def _compare(declared: set[str], optional: set[str], shapes: list[set[str]]):
    """多个 return 分支时：

    - **给了没声明** = 任一分支给了而 SDK 没声明（客户端看不见）；
    - **声明了没给** = SDK 必选的字段，**不是每个分支都给**（某些情况下 undefined）。
    """
    union = set().union(*shapes)
    inter = set.intersection(*shapes)
    return sorted((declared - optional) - inter), sorted(union - declared)


def _runtime_checked() -> set[str]:
    """已经被真实响应断言覆盖的：接口名与内联方法名。"""
    from pathlib import Path

    names: set[str] = set()
    for p in Path(__file__).parent.glob("test_*.py"):
        text = p.read_text(encoding="utf-8")
        names |= set(re.findall(r'_assert_shape\([^,]+,\s*"(\w+)"', text))
        names |= set(re.findall(r'_assert_inline_shape\([^,]+,\s*"(\w+)"', text))
    return names


def _sweep():
    routes = _server_routes()
    runtime = _runtime_checked()
    result = {"checked": [], "mismatch": [], "no_route": [], "unverified": [],
              "runtime": [], "exempt": [], "sdk_unreadable": []}
    for meth, verb, path, decl in _sdk_calls():
        if meth in EXEMPT:
            result["exempt"].append(meth)
            continue
        fn = routes.get((verb, path))
        if fn is None:
            result["no_route"].append(f"{meth} {verb} {path}")
            continue
        shapes, why = _server_shapes(fn)
        sdk = _sdk_fields(decl)
        if shapes is None:
            iface = (_element_decl(decl) or decl).strip()
            if meth in runtime or iface in runtime:
                result["runtime"].append(meth)
            else:
                result["unverified"].append(f"{meth}（服务端返回 {why}）")
            continue
        if sdk is None:
            result["sdk_unreadable"].append(f"{meth}: {decl[:60]}")
            continue
        missing, extra = _compare(sdk[0], sdk[1], shapes)
        if missing or extra:
            result["mismatch"].append(
                f"{meth} {verb} {path}  声明了没给={missing}  给了没声明={extra}")
        else:
            result["checked"].append(meth)
    return result


# ------------------------------------------------------------------ 闸门
def test_cli083_scanner_actually_reads_both_sides():
    """扫不到等于全绿，是最糟的一种绿。"""
    calls = _sdk_calls()
    assert len(calls) >= 250, f"只读出 {len(calls)} 个 SDK 调用点"
    routes = _server_routes()
    assert len(routes) >= 280, f"只读出 {len(routes)} 条服务端路由（include 进来的子路由没走进去？）"
    r = _sweep()
    assert len(r["checked"]) >= 120, f"只比上了 {len(r['checked'])} 个，提取逻辑可能坏了"
    # 几个已知一定可比的
    for known in ("knowledgeCards", "legalAsk", "followUser"):
        assert known in r["checked"], f"{known} 应当可比而没比上"
    # 方法名归属：`async` 方法要认对
    assert any(m == "apiScopes" for m, *_ in calls), "async 方法名没认出来"


def test_cli083_nested_template_paths_are_not_misread():
    """嵌套模板字符串不能把路径切错（第一版把 updateCategory 算成打一条不存在的路由）。"""
    assert _replace_template_exprs(
        "/admin/categories/${categoryId}${qs ? `?${qs}` : ''}"
    ) == "/admin/categories/{x}"
    assert _replace_template_exprs("/tasks/${id}/apply") == "/tasks/{x}/apply"


def test_cli083_every_sdk_call_maps_to_a_real_route():
    """SDK 打的每一条路由，服务端都要有。打一条不存在的路由，调用必然 404/405。"""
    r = _sweep()
    assert not r["no_route"], (
        "这些 SDK 方法打的路由服务端没有：\n  " + "\n  ".join(r["no_route"])
    )


def test_cli083_comparable_shapes_line_up_in_both_directions():
    """能静态比的，两个方向都要对上。

    **声明了没给** → 客户端读到 undefined；
    **给了没声明** → 客户端看不见它（`exportEvidence` 的证明力说明就是这么丢的）。
    """
    r = _sweep()
    assert not r["mismatch"], (
        f"SDK 声明与服务端返回对不上（共 {len(r['mismatch'])} 处）：\n  "
        + "\n  ".join(r["mismatch"])
    )


def test_cli083_sdk_declarations_are_readable():
    """服务端能读出形状、而 SDK 那一侧读不出——那是解析器的盲区，不能悄悄算过。"""
    r = _sweep()
    assert not r["sdk_unreadable"], (
        "这些 SDK 响应声明解析不了（解析器盲区会让它们悄悄退出闸门）：\n  "
        + "\n  ".join(r["sdk_unreadable"])
    )


def test_cli083_unverified_count_only_goes_down():
    """静态读不出、又没有真实响应断言的调用点——只许降不许升。"""
    r = _sweep()
    n = len(r["unverified"])
    # 消息里不说「新增的是哪几个」：这里没有上一次的名单，只能列出全部。
    # 第一版取列表末尾 N 个冒充「新增的」——V128 撞上时它点名的是两个早就在那儿的
    # 方法，而真正新增的那两个不在里面。**一个会说错话的闸门比沉默的更糟。**
    assert n <= MAX_UNVERIFIED, (
        f"未验证的调用点从 {MAX_UNVERIFIED} 涨到了 {n}。新加的端点要么返回字面量 dict，"
        "要么补一条 `_assert_shape` / `_assert_inline_shape` 真实响应断言。"
        "对照这次新加的 SDK 方法在下面找（全部未验证的，按名字排序）：\n  "
        + "\n  ".join(sorted(r["unverified"]))
    )


def test_cli083_exemptions_are_real_and_reasoned():
    """豁免表里的方法必须真的存在，理由要是人话。"""
    names = {m for m, *_ in _sdk_calls()}
    for meth, why in EXEMPT.items():
        assert meth in names, f"EXEMPT 里的 {meth} 已经不在 SDK 里了"
        assert len(why) >= 30, f"{meth} 的豁免理由太敷衍：{why}"


def test_cli083_comparator_catches_both_directions():
    """比较器自己的红验：两个方向、以及多分支的情况都要报出来。"""
    # 声明了没给
    assert _compare({"a", "b"}, set(), [{"a"}]) == (["b"], [])
    # 给了没声明
    assert _compare({"a"}, set(), [{"a", "b"}]) == ([], ["b"])
    # 可选字段缺失不报
    assert _compare({"a", "b"}, {"b"}, [{"a"}]) == ([], [])
    # 多分支：必选字段只在一个分支出现 → 另一个分支 undefined
    assert _compare({"a", "b"}, set(), [{"a", "b"}, {"a"}]) == (["b"], [])


def test_cli083_coverage_is_reported_honestly():
    """覆盖率写进断言消息里：这一篇的价值有一半在于**让那个数字可见**。"""
    r = _sweep()
    total = sum(len(v) for v in r.values())
    covered = len(r["checked"]) + len(r["runtime"]) + len(r["exempt"])
    # 不是阈值断言，是「这个数必须算得出来」——0 覆盖说明整个扫描坏了
    assert covered > 0 and total >= 250, (covered, total)
    print(f"\nCLI-083 响应形状覆盖：静态比对 {len(r['checked'])} + "
          f"真实响应 {len(r['runtime'])} + 豁免 {len(r['exempt'])} = {covered}/{total}；"
          f"未验证 {len(r['unverified'])}")


# ------------------------------------------------- 扫出来的服务端那两处，行为验
def test_cli083_verify_response_has_the_same_keys_on_both_branches(client, monkeypatch):
    """实名核验两个出口同形：通过与转人工都带 `status`。

    此前通过那支只回 `{is_verified: true}`，转人工那支回
    `{is_verified: false, status: 'manual_review'}`。SDK 只声明了前者的形状，
    于是网页在转人工时照样弹「实名认证成功」——**HTTP 200 不等于通过**。
    """
    from tests.conftest import auth, register
    from app.vendors.base import VendorResult
    from app.vendors.registry import get_provider

    ok_user = register(client, "13800091001", "通过的人")
    r = client.post("/api/v1/users/me/verify",
                    json={"real_name": "张三", "id_number": "110101199001011235"},
                    headers=auth(ok_user))
    assert r.status_code == 200, r.text
    assert r.json() == {"is_verified": True, "status": "verified"}

    provider = get_provider("kyc")
    monkeypatch.setattr(provider, "verify", lambda *a, **k: VendorResult(
        ok=True, external_ref="m-1", status="manual"))
    manual_user = register(client, "13800091002", "转人工的人")
    r = client.post("/api/v1/users/me/verify",
                    json={"real_name": "李四", "id_number": "11010119900101123X"},
                    headers=auth(manual_user))
    assert r.status_code == 200, r.text
    assert r.json() == {"is_verified": False, "status": "manual_review"}
    assert set(r.json()) == {"is_verified", "status"}


def test_cli083_adding_a_team_member_confirms_the_spend_limit(client):
    """加成员时回显额度——那是 owner 刚给这个人设下的花钱上限。

    额度一直是存下了的；缺的是**响应里的确认**。SDK 声明了这个字段而服务端
    不给，客户端读到 undefined：一个「我设的上限到底生效没有」答不出来的界面。
    """
    from tests.conftest import auth, register, verify_user

    owner = register(client, "13800091011", "团队主")
    verify_user(client, owner)
    member = register(client, "13800091012", "成员")
    team = client.post("/api/v1/teams", json={"name": "额度回显测试队"}, headers=auth(owner))
    assert team.status_code in (200, 201), team.text
    tid = team.json()["id"]
    r = client.post(f"/api/v1/teams/{tid}/members",
                    json={"user_id": member["id"], "role": "member", "spend_limit_cents": 50000},
                    headers=auth(owner))
    assert r.status_code == 201, r.text      # 建成员是创建，201
    assert r.json()["spend_limit_cents"] == 50000
