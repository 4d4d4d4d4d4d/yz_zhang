"""CLI-082 SDK 的每个方法都要有人负责（77 号 spec）。

V82 的闸门问的是一个方向：**服务端端点在端上到达得了吗**。
反过来那一半一直没人管——SDK 里的方法有没有人调。清点结果：

    SDK 方法 265 个，两端都没人调用 87 个

87 个里这一批挑出了五条闭环真的断了的（登录找回、资质提交、工单自助、
发票、通知开关），剩下的必须被**分类**，而不是继续躺着：

1. **有端调用**：扫描器能在 web / app / admin 里找到调用；
2. **有意不给端**：豁免表，写一句人话理由；
3. **台账排期**：72 号台账里有对应的行，说明是哪条线、为什么还没做。

三类都不在 → 红。新增 SDK 方法时必须回答「谁来调它」——
这正是 V82 对服务端端点立下的规矩，现在两个方向都有了。
"""
import re
from pathlib import Path

import pytest

from tests.clientscan import SDK, calls

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "docs" / "specs" / "72-status-ledger.md"

# 扫描器噪音：不是 API 方法
NOT_METHODS = {"constructor"}


def sdk_methods() -> list[str]:
    src = SDK.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"\n  ([a-zA-Z][a-zA-Z0-9_]*)\s*[(<]", src)) - NOT_METHODS)


def _unused(method: str) -> bool:
    return not any(calls(c, method) for c in ("web", "app", "admin"))


# ---------------------------------------------------------------- 第 2 类
# 有意不给端 -> 为什么。
#
# 判定标准：**这个方法本来就不该由用户侧界面调用**，
# 不是「还没做」。后者属于第 3 类。
INTENTIONAL: dict[str, str] = {
    "expireTasks": "job 端点，由调度器按 32 号调度表执行，不该由界面触发",
    # 运营看数：V101 的 CLI-080 闸门已经逐条判过「不做也不卡人」
    "amlStats": "运营看数，/admin 覆盖闸门（CLI-080）里已归为不卡人的一类",
    "marketHealth": "同上：供需健康度是看数，不看只是不知道哪个城市缺人",
    "northStar": "同上：北极星指标看数，后台首屏已有核心指标",
    "supplyHint": "同上：供给提示是运营参考，不影响任何人的钱或权利",
    "categoryDemand": "同上：类目需求热度是运营参考",
    "updateCity": "停用城市是运营收缩动作，开通（createCity）才是会卡人的那一半",
    # 取证与对账：给争议处理与审计用，不是日常界面
    "anchorCoverage": "存证覆盖率是运维/取证口径，争议时由平台出证据包，不是用户页面",
    "verifyAnchorChain": "同上：存证链校验是取证动作，证据包里已包含结论",
    "contractAnchors": "同上：单合约的存证条目由证据包呈现",
    "contractSettlements": "分账明细在账单流水里已可见，这条是对账口径的原始数据",
    "couponsForContract": "某合约可用券由下单流程内部选用，不单独成页",
    "decompositionTemplate": "模板由发布流程内部取用（taskTemplate 才是用户侧那条）",
    "dispute": "单个纠纷详情：当事人页面走 myDisputes + 详情组件，这条是同一数据的另一入口",
    "stepReviews": "子步骤核验记录由核验台内部使用",
    "listReviews": "评价列表由任务详情与口碑页内部取用（userReviews 是画像那条）",
}

# ---------------------------------------------------------------- 第 3 类
# 台账排期 -> 台账里对应的编号（必须真的出现在 72 号台账里）。
#
# 「欠账」和「有意不做」是两件不同的事，混在一起就看不出还欠多少。
SCHEDULED: dict[str, str] = {
    # 社交线（43 号 spec）：好友、群聊、圈层成员管理整体未上端
    "friends": "SOCIAL-050", "friendRequests": "SOCIAL-050",
    "sendFriendRequest": "SOCIAL-050", "decideFriendRequest": "SOCIAL-050",
    "removeFriend": "SOCIAL-050", "setFriendRemark": "SOCIAL-050",
    "workedWith": "SOCIAL-050",  # followStats 已由 V117 接到两端的空间页
    "createGroup": "SOCIAL-050", "updateGroup": "SOCIAL-050",
    "inviteToGroup": "SOCIAL-050", "removeFromGroup": "SOCIAL-050",
    "approveCircleMember": "SOCIAL-050", "removeCircleMember": "SOCIAL-050",
    "circleMembers": "SOCIAL-050", "circleStats": "SOCIAL-050",
    "myBlocks": "SOCIAL-050",
    # 内容与检索线（06/08 号 spec）
    "search": "SEARCH-050", "searchSuggest": "SEARCH-050", "trendingTerms": "SEARCH-050",
    "knowledgeSearch": "SEARCH-050", "knowledgeCards": "SEARCH-050",
    "bookmark": "CONTENT-050", "unbookmark": "CONTENT-050", "myBookmarks": "CONTENT-050",
    "userContents": "CONTENT-050", "userReviews": "CONTENT-050",
    "publicProfile": "CONTENT-050", "signVideoUpload": "CONTENT-050",
    "sendQuoteCard": "CONTENT-050",
    "mySubscriptions": "CONTENT-050", "unsubscribe": "CONTENT-050",
    # 任务侧的三条（03 号 spec）：我的任务、草稿发布、编辑
    "myTasks": "TASK-060", "publishTask": "TASK-060", "editTask": "TASK-060",
    "trip": "TASK-060",
    # 编排循环（17 号 spec）：mission 的用户侧界面
    "createMission": "ORC-066", "getMission": "ORC-066", "myMissions": "ORC-066",
    "tickMission": "ORC-066", "cancelMission": "ORC-066", "finalReport": "ORC-066",
    # 团队与合作体的成员管理（53/50 号 spec）
    "addTeamMember": "TEAM-065", "updateTeamMember": "TEAM-065",
    "removeTeamMember": "TEAM-065",
    "inviteToVenture": "COOP-060", "joinVenture": "COOP-060",
    "ventureDistributions": "COOP-060",
    # 账号与推送的长尾
    "changePhone": "ACC-042", "oauthLogin": "ACC-042", "oauthProviders": "ACC-042",
    "unregisterDevice": "ACC-042",
    # 客服升级为纠纷（49 号 spec 已建服务端）
    "escalateTicket": "CS-033",
    # 法律工具与埋点
    "legalAsk": "LAW-050", "legalDocument": "LAW-050",
    "trackEvent": "GROWTH-050",
}

EXCUSE_WORDS = ("还没做", "待补", "TODO", "以后", "下一批")


# ---------------------------------------------------- 扫描器自己先会红
def test_cli082_scanner_finds_methods_and_usages():
    """扫不到等于全绿，是最糟的一种绿。"""
    methods = sdk_methods()
    assert len(methods) >= 200, f"只扫到 {len(methods)} 个 SDK 方法，提取逻辑可能坏了"
    # 几个一定被用到的
    for known in ("login", "createTask", "withdraw", "pendingTeams"):
        assert known in methods, f"已知方法没被扫出来：{known}"
        assert not _unused(known), f"{known} 明明有人调，扫描却说没有"
    assert _unused("nopeNotAMethod") is True


# ---------------------------------------------------- CLI-082 三分类
def test_cli082_every_method_is_used_exempt_or_scheduled():
    """每个 SDK 方法都要落进三类之一。

    **新增方法时必须回答「谁来调它」**——不回答就红。
    """
    accounted = set(INTENTIONAL) | set(SCHEDULED)
    missing = sorted(m for m in sdk_methods() if _unused(m) and m not in accounted)
    assert not missing, (
        "这些 SDK 方法两端都没人调用，也没有交代：\n  "
        + "\n  ".join(missing)
        + "\n三条路选一条：在某个端上接上它；"
          "或写进 INTENTIONAL（说明它本来就不该由界面调）；"
          "或写进 SCHEDULED 并在 72 号台账里留一行。"
    )


def test_cli082_tables_have_no_dead_entries():
    """接上了却还留在豁免/排期表里，表就会慢慢失去意义。"""
    methods = set(sdk_methods())
    for name, table in (("INTENTIONAL", INTENTIONAL), ("SCHEDULED", SCHEDULED)):
        gone = sorted(m for m in table if m not in methods)
        assert not gone, f"{name} 里这些方法已经不在 SDK 里了：{gone}"
        wired = sorted(m for m in table if m in methods and not _unused(m))
        assert not wired, (
            f"{name} 里这些方法已经有端在调用了，从表里删掉：{wired}"
        )


def test_cli082_intentional_reasons_are_reasons_not_excuses():
    """「有意不给端」的理由不许是「还没做」——那属于排期，不属于豁免。"""
    assert len(INTENTIONAL) >= 10
    for method, why in sorted(INTENTIONAL.items()):
        assert len(why) >= 12, f"{method} 的理由太短：{why}"
        bad = [w for w in EXCUSE_WORDS if w in why]
        assert not bad, f"{method} 的理由里有 {bad}——那是欠账，该进 SCHEDULED"


def test_cli082_scheduled_items_really_have_a_ledger_line():
    """排期必须**在台账里真的有行**，否则「排期」只是一个说法。"""
    ledger = LEDGER.read_text(encoding="utf-8")
    missing = sorted({fid for fid in SCHEDULED.values() if fid not in ledger})
    assert not missing, (
        "这些编号被当成「台账里排着」，而 72 号台账里没有：\n  "
        + "\n  ".join(missing)
    )


# ---------------------------------------------------- 反向：路径必须存在
def test_cli082_sdk_never_points_at_a_path_the_server_does_not_have():
    """SDK 里的每条路径都必须在服务端存在。

    V82 那次 `addCertification` 打的就是一个服务端已经改掉的契约：
    SDK 里写得好好的，调用即 422，而**没有任何测试会红**——
    那条测试打的是 mock fetch，只验证「我发出的请求长这样」。
    """
    from tests.test_client_contract_coverage import _norm, _sdk_paths

    from app.main import app

    server = {
        _norm(p[len("/api/v1"):]) for p in app.openapi()["paths"]
        if p.startswith("/api/v1")
    }
    sdk = {_norm(p) for p in _sdk_paths(SDK.read_text(encoding="utf-8"))}
    assert len(sdk) >= 200, f"只扫到 {len(sdk)} 条 SDK 路径，提取逻辑可能坏了"

    # 归一化会把「动作也是模板变量」的那条写成 /{x}/{x}：
    # decideWithdraw 拼的是 `/withdraw-requests/${id}/${approve ? ... : ...}`，
    # 两个具体路径都在服务端（approve / reject），闸门认这一条
    KNOWN_TEMPLATE_ACTIONS = {"/wallet/withdraw-requests/{x}/{x}"}
    ghost = sorted(sdk - server - KNOWN_TEMPLATE_ACTIONS)
    assert not ghost, (
        "SDK 里这些路径在服务端不存在（调用即 404/422）：\n  " + "\n  ".join(ghost)
    )


@pytest.mark.parametrize("method", [
    # 这一批接上的五条线：接上了就不许再退回去
    "resetPassword", "smsLogin", "sendSmsCode",
    "submitCertification", "myCertifications",
    "createTicket", "myTickets",
    "requestInvoice", "myInvoices",
    "notificationPrefs", "setNotificationPref",
    "unreadCount", "markAllRead",
])
def test_cli082_v102_lines_stay_reachable(method):
    """`{method}` 必须有端在调。

    这五条线的服务端与 SDK 一直都在，端上没人调——
    「有能力」和「有人用得上」是两件事。
    """
    assert not _unused(method), (
        f"{method} 又变成两端都没人调了。这条线的服务端是通的，"
        f"用户却点不到——V102 就是为了修这个。"
    )
