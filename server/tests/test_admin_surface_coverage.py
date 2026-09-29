"""CLI-080 / ADMIN-070 把运营面纳入覆盖闸门（76 号 spec）。

V82 立了覆盖闸门（服务端新增用户可达端点，必须给出「端上怎么到达」
或「为什么不给端」），而它的扫描器第一行就把整个运营面排除了：

    if "/admin" in rel or "/jobs" in rel:
        continue          # 运营后台与调度端点不面向普通客户端

那句注释回答的是「要不要放进用户 SDK」，被当成了「要不要有人接」。
于是四十条运营端点整体退出了任何覆盖检查——V96、V98 各自靠**人工清点**
捞回来几条，而人工清点捞不到「端点压根不存在」这一类：

    POST /teams/2/company      → 200  verify_status = pending
    POST /admin/teams/2/verify → 404      ← 没有人能核过一个团队
    库里唯一把它写成 verified 的地方是一条测试（直接写库）

V98 建的 `ADMIN_CONSOLE` 是一张**手挑的必达清单**：它只回答「表里这几条
做到了没有」，不回答「有没有第四十一条没人管」。这一篇回答后者。
"""
import ast
import re
from pathlib import Path

import pytest

from tests.clientscan import calls as _client_calls
from tests.clientscan import sdk_has

REPO = Path(__file__).resolve().parents[2]


def _calls(method: str) -> bool:
    return _client_calls("admin", method)


def _admin_paths() -> set[str]:
    """服务端**自己声明的**那一份运营路由表，不是手抄的清单。"""
    from app.main import app

    prefix = "/api/v1"
    out = set()
    for path in app.openapi()["paths"]:
        if path.startswith(prefix) and "/admin" in path:
            out.add(re.sub(r"\{[^}]+\}", "{x}", path[len(prefix):]))
    return out


# 运营端点 -> 管理后台里兑现它的 SDK 方法。
#
# 判定标准（沿用 V98）：**只有运营/风控能做，而不做就有人的钱或权利卡住。**
REACHED_BY: dict[str, str] = {
    "/admin/teams/pending": "pendingTeams",
    "/admin/teams/{x}/verify": "verifyTeam",
    "/admin/certifications/pending": "pendingCertifications",
    "/admin/certifications": "adminCertifications",
    "/admin/certifications/{x}/revoke": "revokeCertification",
    "/admin/certifications/{x}/decide": "decideCertification",
    "/admin/uploads/pending": "pendingUploads",
    "/admin/uploads/{x}/resolve": "resolveUpload",
    "/admin/tickets": "adminTickets",
    "/admin/tickets/{x}/resolve": "resolveTicket",
    "/admin/security": "adminSecurity",
    "/admin/security/unban": "unbanIp",
    "/admin/cities": "createCity",
    "/admin/categories": "createCategory",
    "/admin/categories/{x}": "updateCategory",
    "/admin/users": "adminUsers",
    "/admin/users/{x}/ban": "banUser",
    "/admin/users/{x}/unban": "unbanUser",
    "/admin/users/{x}/ban-impact": "banImpact",
    "/admin/reports": "adminReports",
    "/admin/reports/{x}/resolve": "resolveReport",
    "/admin/metrics": "adminMetrics",
    "/admin/audit-log": "adminAuditLog",
    "/admin/platform-finance": "platformFinance",
    "/admin/platform-finance/settle": "settlePlatform",
    "/admin/announcements": "broadcastAnnouncement",
    "/admin/aml/activities": "amlActivities",
    "/admin/aml/activities/{x}/review": "reviewAmlActivity",
}

# 不属于上面那条判定标准的 -> 为什么。
#
# 「豁免」不等于「不该做」，只等于**不卡任何人的钱或权利**；
# 它们仍然在 72 号台账里挂着。
ADMIN_EXEMPT: dict[str, str] = {
    "/admin/coupons": "没有补贴活动就是没有补贴——不卡任何人的钱或权利，属于增长动作",
    "/admin/coupons/{x}/pause": "停用券只影响新领取，已领的不受影响，不卡任何人的既得权益",
    "/admin/campaigns": "活动是自愿的增长动作，不建只是没有活动可参加，不卡既有权益",
    "/admin/subsidy-pool/fund": "给补贴池注资是自愿的营销支出，不注资只是没有补贴可发",
    "/admin/agents": "平台自有 AI 执行者是可选的一种执行者，不建只是少一种供给",
    "/admin/agents/{x}": "改 agent 的参数是调优，不改只是沿用创建时的设定",
    "/admin/funnels": "转化漏斗是看数，不看只是不知道流失在哪一步，不卡任何人",
    "/admin/market-health": "供需健康度是看数，不看只是不知道哪个城市缺人，不卡具体某个人",
    "/admin/north-star": "北极星指标是看数（后台首屏已有核心指标）",
    "/admin/aml/stats": "合规统计是看数；要处置的那条队列（activities）已在后台",
    "/admin/settlements/verify": "分账自检是运维核对工具，`scripts/consistency_check.py` 也能跑",
    "/admin/vendors": "供应商在位状态是看数；真正会拦人的是生产启动自检",
    "/admin/jobs/reconcile": "日终对账由调度器执行（32 号调度表里在册），不靠人点",
    "/admin/matching-config": "匹配权重是调参，不调用默认值，不卡任何人",
    "/admin/cities/{x}": "停用城市是收缩动作；开通（createCity）才是会卡住人的那一半",
}

# 豁免理由不许是**欠账**：欠账归 72 号台账管，不该伪装成豁免。
EXCUSE_WORDS = ("还没做", "待补", "TODO", "todo", "以后", "下一批", "暂未实现")


# ---------------------------------------------------- 扫描器自己先会红
def test_cli080_scanner_finds_the_admin_surface():
    """扫不到等于全绿，是最糟的一种绿（V82 立的规矩）。"""
    paths = _admin_paths()
    assert len(paths) >= 35, f"只扫到 {len(paths)} 条运营端点，提取逻辑可能坏了"
    for known in ("/admin/metrics", "/admin/users/{x}/ban", "/admin/teams/{x}/verify"):
        assert known in paths, f"已知运营端点没被扫出来：{known}"
    assert "/admin/nope" not in paths


# ---------------------------------------------------- CLI-080 覆盖
def test_cli080_every_admin_endpoint_is_reachable_or_exempt():
    """每条运营端点，要么管理后台真的调它，要么豁免表里写一句人话理由。

    **这条闸门的存在本身就是这一批的产出**：它一上来就抓到了
    「没有人能核过一个团队」——那条端点当时压根不存在。
    """
    paths = _admin_paths()
    accounted = set(REACHED_BY) | set(ADMIN_EXEMPT)
    missing = sorted(paths - accounted)
    assert not missing, (
        "这些运营端点既没有后台入口，也没有豁免理由：\n  "
        + "\n  ".join(missing)
        + "\n要么在管理后台里接上它，要么在 ADMIN_EXEMPT 里写清"
          "「不做也不会卡住任何人的钱或权利」。"
    )


def test_cli080_tables_do_not_keep_paths_that_no_longer_exist():
    """删了端点、表里留着，闸门就会慢慢空掉（V82 立的双向对齐）。"""
    paths = _admin_paths()
    stale = sorted((set(REACHED_BY) | set(ADMIN_EXEMPT)) - paths)
    assert not stale, f"这些路径已经不在服务端了，从表里删掉：{stale}"


@pytest.mark.parametrize("path", sorted(REACHED_BY))
def test_cli080_the_console_really_calls_it(path):
    """「有 SDK 方法」不等于「后台在用」——组件还得真的挂上（V96 的教训）。"""
    method = REACHED_BY[path]
    assert sdk_has(method), f"{path} 登记的 {method}() 在共享 SDK 里不存在"
    assert _calls(method), (
        f"{path} 登记由 {method}() 兑现，而管理后台里没有挂上的组件调用它。\n"
        f"不做会怎样：这条队列/动作没有出口，提交的人永远等着。"
    )


def test_cli080_exemption_reasons_are_reasons_not_excuses():
    """豁免理由不许是「还没做」。

    那不是理由，是欠账——欠账归 72 号台账管。允许它伪装成豁免，
    这张表会在几个批次之内变成一张垃圾场。
    """
    assert len(ADMIN_EXEMPT) >= 10
    for path, why in sorted(ADMIN_EXEMPT.items()):
        assert len(why) >= 12, f"{path} 的豁免理由太短，说不清为什么不卡人：{why}"
        bad = [w for w in EXCUSE_WORDS if w in why]
        assert not bad, (
            f"{path} 的豁免理由里有 {bad}——那是欠账，不是豁免理由。"
            f"要么接上它，要么写清它为什么不卡任何人。"
        )


# ---------------------------------------------------- ADMIN-070 审计 target
def test_admin070_audit_target_id_is_never_a_string():
    """`AdminAudit.target_id` 是 `Integer`，传字符串在 Postgres 上会拒绝这条 INSERT。

    SQLite 会默默接受，所以本地全绿；而这些写入点都在处置动作里——
    生产上**处置会连带失败**。

    用 AST 而不是正则：正则读不懂调用结构（V58 那条状态机闸门同一个理由）。
    """
    offenders: list[str] = []
    checked = 0
    for path in sorted((REPO / "server" / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "record_audit":
                continue
            checked += 1
            target = None
            if len(node.args) >= 5:
                target = node.args[4]
            for kw in node.keywords:
                if kw.arg == "target_id":
                    target = kw.value
            if target is None:
                continue
            is_str_call = (isinstance(target, ast.Call)
                           and getattr(target.func, "id", "") == "str")
            if is_str_call or isinstance(target, ast.Constant) and isinstance(target.value, str):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert checked >= 10, f"只扫到 {checked} 处 record_audit 调用，AST 提取可能坏了"
    assert not offenders, (
        "这些 record_audit 把字符串传给了整型的 target_id（Postgres 会拒绝）：\n  "
        + "\n  ".join(offenders)
    )
