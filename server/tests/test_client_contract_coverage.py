"""CLI-060/061 端上接得到：客户端契约覆盖闸门（57 号 spec）。

V81 收尾时清点了一次：**78 个用户可达的服务端端点，共享 SDK 里一个都没有**。
V73~V79 六个批次（agent、人类核验、早期合作体、受限类目资质、团队账户、
开放 API）的用户侧入口，端上全是空的。服务端完整、测试全绿、文档齐备,
而用户点不到。

这个文件不负责补那些方法，它负责让「下一次再这样」立刻变红：

    服务端新增一个用户可达的端点，就必须同时给出「端上怎么到达它」
    或者「为什么不给端」——二选一，不许沉默。

与 V60 的注销处置表同一种做法：新增一项就逼作者做一次决定，
而不做决定时的默认行为不能是「悄悄留下」。
"""
import re
from pathlib import Path

import pytest

CLIENT_TS = Path(__file__).resolve().parents[2] / "packages" / "core" / "src" / "client.ts"

# CLI-061 **豁免要写理由，不是写 True。** 一个只有布尔值的豁免表，
# 三个月后没人知道当初为什么豁免，也就没人敢删。
CLIENT_EXEMPT: dict[str, str] = {
    "/open/v1/tasks": "开放 API 是给第三方用 API Key 调的，我们自己的客户端走普通会话",
    "/open/v1/tasks/{x}": "开放 API 的任务详情，第三方集成入口，不是本平台客户端的入口",
    "/open/v1/wallet": "开放 API 的余额查询，同样只给持 API Key 的第三方",
    "/wallet/pay/callback": "支付供应商回调，服务端到服务端，客户端不该也不能调",
    "/wallet/withdraw-requests/{x}/approve": "提现人审是风控岗位的动作，在管理后台做",
    "/wallet/withdraw-requests/{x}/reject": "提现驳回同样是风控岗位的动作，不是用户按钮",
    "/disputes/{x}/verdict": "裁决由平台仲裁岗做（require_admin），不是当事人的按钮",
    "/disputes/{x}/appeal-verdict": "二审裁决也由平台仲裁岗做，且必须与一审不是同一个人",
    "/events/health": "事件投递健康度，job 鉴权，给调度与监控用",
    "/events/dead-letters": "死信队列是运维视图（require_admin）",
    "/finance/tax-ledger": "代扣与缴库台账（require_admin）",
    "/files/{x}": "FILE-013 能力 URL：由 <img src> 直读，带不了 Authorization 头正是它存在的理由",
    "/files/{x}/secure": "签名直读路径，同样由浏览器直接取，不经 SDK",
}

# 扫描器自检用：这几条必须被扫出来，否则说明提取逻辑坏了（V72 立的规矩）。
KNOWN_SDK_PATHS = {
    "/auth/login",
    "/tasks",
    "/tasks/mine",          # 它在源码里是嵌套模板字面量，正则版本会漏掉
    "/contracts/{x}/fund",  # 同上：路径后面拼了查询串
    "/wallet",
}
MIN_SDK_PATHS = 150


def _sdk_paths(src: str) -> set[str]:
    """提取 client.ts 里所有 URL 字面量，模板插值统一成 `{x}`。

    **手写字符扫描，不用正则**：SDK 里有

        `/tasks/mine${qs ? `?${qs}` : ''}`

    模板字面量里嵌了第二层模板字面量，正则会在第一个反引号处断掉。
    这类假阴性在覆盖率闸门里表现为**假报缺失**——比不做还糟，
    因为一个满口假警报的闸门会被人关掉（V80 那条法律文本闸门的教训）。
    """
    out: set[str] = set()
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch in "'\"":
            j, buf = i + 1, []
            while j < n and src[j] != ch:
                if src[j] == "\\":
                    j += 2
                    continue
                buf.append(src[j])
                j += 1
            out.add("".join(buf))
            i = j + 1
            continue
        if ch == "`":
            j, buf = i + 1, []
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "`":
                    break
                if src[j] == "$" and j + 1 < n and src[j + 1] == "{":
                    buf.append("{x}")
                    j += 2
                    depth = 1
                    while j < n and depth:
                        if src[j] == "{":
                            depth += 1
                        elif src[j] == "}":
                            depth -= 1
                        elif src[j] == "`":
                            j = _skip_template(src, j)
                        j += 1
                    continue
                buf.append(src[j])
                j += 1
            out.add("".join(buf))
            i = j + 1
            continue
        i += 1
    return {p for p in out if p.startswith("/")}


def _skip_template(src: str, i: int) -> int:
    """跳过一段嵌套的模板字面量，返回它结尾反引号的下标。"""
    j, n = i + 1, len(src)
    while j < n:
        if src[j] == "\\":
            j += 2
            continue
        if src[j] == "`":
            return j
        if src[j] == "$" and j + 1 < n and src[j + 1] == "{":
            j += 2
            depth = 1
            while j < n and depth:
                if src[j] == "{":
                    depth += 1
                elif src[j] == "}":
                    depth -= 1
                j += 1
            continue
        j += 1
    return n - 1


def _norm(path: str) -> str:
    """把服务端路径与 SDK 字面量归一到同一形状。

    路径参数一律记成 `{x}`；**段内**的插值当作查询串拼接剥掉——
    `/tasks/mine${qs ? '?' + qs : ''}` 归一后必须等于 `/tasks/mine`。
    """
    p = re.sub(r"\{[^}]*\}", "{x}", path).split("?")[0]
    segs = []
    for seg in p.split("/"):
        if seg and seg != "{x}" and "{x}" in seg:
            seg = seg.replace("{x}", "")
        segs.append(seg)
    return "/".join(segs).rstrip("/") or "/"


def _server_paths() -> set[str]:
    """服务端**自己声明的**那一份路由表，不是手抄的清单。"""
    from app.main import app

    prefix = "/api/v1"
    out = set()
    for path in app.openapi()["paths"]:
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        if "/admin" in rel or "/jobs" in rel:
            continue          # 运营后台与调度端点不面向普通客户端
        out.add(_norm(rel))
    return out


@pytest.fixture(scope="module")
def sdk() -> set[str]:
    return {_norm(p) for p in _sdk_paths(CLIENT_TS.read_text(encoding="utf-8"))}


# ---------------------------------------------------- 扫描器自己先会红
def test_cli061_scanner_actually_finds_paths(sdk):
    """扫不到就恒真，闸门等于不存在——这是 V72 立下的规矩。"""
    assert len(sdk) >= MIN_SDK_PATHS, f"只扫到 {len(sdk)} 条 SDK 路径，提取逻辑可能坏了"
    missing = KNOWN_SDK_PATHS - sdk
    assert not missing, f"已知路径没被扫出来，说明提取逻辑有假阴性：{sorted(missing)}"


# ------------------------------------------------------------ CLI-060 覆盖
def test_cli060_every_user_facing_endpoint_is_reachable_from_the_client(sdk):
    """服务端新增用户可达端点时，必须同时回答「端上怎么到达」。

    改造前这条是沉默的：V73~V79 六个批次连续把用户侧入口留空，
    没有任何测试会红——因为没有任何测试问过「谁来调它」。
    """
    unreachable = sorted(p for p in _server_paths() if p not in sdk and p not in CLIENT_EXEMPT)
    assert not unreachable, (
        "这些端点用户可达，但共享 SDK 里没有任何路径能到它们。\n"
        "要么在 packages/core/src/client.ts 里加方法，"
        "要么在 CLIENT_EXEMPT 里写明为什么不给客户端：\n  "
        + "\n  ".join(unreachable)
    )


# ------------------------------------------------------------ CLI-061 豁免
def test_cli061_exemptions_carry_a_real_reason():
    """`True` 不算理由。三个月后没人知道当初为什么豁免，也就没人敢删。"""
    for path, reason in CLIENT_EXEMPT.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 8, f"{path} 的豁免理由太敷衍"


def test_cli061_exemption_table_has_no_dead_entries():
    """反向对齐（SYNC-002 同款）：豁免表里不能留已不存在的路径。

    否则它会慢慢变成一张没人敢删的历史清单，而闸门的实际覆盖面悄悄缩小。
    """
    server = _server_paths()
    dead = sorted(p for p in CLIENT_EXEMPT if p not in server)
    assert not dead, f"豁免表里这些路径服务端已经没有了，删掉它们：{dead}"


def test_cli062_the_six_feature_lines_are_reachable(sdk):
    """六条线各钉一条代表路径：这条红了说明整条线又掉端了。

    比只看总数有用——总数可以被一堆无关方法填平。
    """
    for path, line in [
        ("/tasks/{x}/eligible-agents", "AGT 可用助理（含不可用的理由）"),
        ("/verification-orders", "VER 可接核验单"),
        ("/ventures/mine", "COOP 我的合作体"),
        ("/teams/mine", "TEAM 我的团队"),
        ("/developer/api-keys", "OAPI 开放 API 密钥"),
        ("/users/me/certifications", "CERT 我的资质申请与状态"),
    ]:
        assert path in sdk, f"{line} 在客户端上没有入口（{path}）"
