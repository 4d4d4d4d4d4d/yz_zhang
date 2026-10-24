"""CLI-074 通知里让你做的事，两端都得做得到（67 号 spec）。

V91 立了 `REMEDY_UI`：服务端的「请先 X」，X 的入口必须存在。
这一条是它在通知侧的孪生。

第一个实例是 V91 手写的那条单独断言——V90 给 AI 交付的必达通知写了
「可在任务详情页申请人工核验」，而 `requestVerification` 当时只在
`web/src/AgentPanel.tsx` 出现过一次。**通知把人叫来了，他点进去无路可走。**

V92 给团队审批补通知时，同样的坑就摆在面前：App 上根本没有团队页。
**先发通知、界面下批再补，等于先把人叫醒再告诉他没事可做。**

判定标准：**这条通知的正文让收件人去做一件事，那件事就必须在收到通知的
端上做得到。** 不要求收件人做任何事的通知（纯周知）不进表。
"""
import re

import pytest

from tests.test_remedy_ui import CLIENT_SRC, _calls, _sources

# (通知类别, 标题) -> (要做的那件事的 SDK 方法, 必须做得到的端, 这条通知在叫他做什么)
NOTICE_ACTIONS: dict[tuple[str, str], tuple[str, tuple[str, ...], str]] = {
    ("team", "支出待审批"): (
        "decideTeamSpend", ("web", "app"),
        "这条通知就是叫他来批的。点进去没有审批入口，这条通知等于白发——"
        "而且比不发更糟：把人叫醒了又告诉他没事可做",
    ),
    ("team", "支出审批结果"): (
        "teamSpends", ("web", "app"),
        "被驳回的人要看到那段**被强制写下的理由**，批准的人要能去执行",
    ),
    ("task", "待验收提醒"): (
        "acceptDelivery", ("web", "app"),
        "N 天后不处理就自动放款。叫他来验收，就得让他验收得了",
    ),
    ("task", "待验收提醒（人工核验）"): (
        "requestVerification", ("web", "app"),
        "V90 的文案写着「可在任务详情页申请人工核验」，而这条路 V91 之前"
        "只在网页上存在——**通知里指的路，必须在收到通知的端上走得通**",
    ),
    ("task", "交付被驳回"): (
        "deliver", ("web", "app"),
        "叫他整改，就得让他在同一个端上能把修正稿重新提交上去",
    ),
    ("task", "收到任务邀约"): (
        "acceptInvitation", ("web", "app"),
        "有人点名请他接这一单。App 上此前既看不到邀约也应不了——"
        "**又一条把人叫来了却无路可走的通知**（V93 才补上）",
    ),
    ("contract", "收到合约变更单"): (
        "acceptChange", ("web", "app"),
        "这条通知就是叫他去确认或拒绝改价的。点进去没有入口，"
        "任务范围变了却只能走取消或纠纷",
    ),
    ("contract", "合约签署超期作废"): (
        "signContract", ("web", "app"),
        "叫他去签，就得让他签得了——作废后要重新走一遍成交，错过没法补",
    ),
}


def test_cli074_scanner_self_check():
    """扫不到等于全绿，是最糟的一种绿。先证明扫描器真的在读东西。"""
    for client, files in CLIENT_SRC.items():
        assert files, f"{client} 一个源码文件都没扫到"
    assert _calls("app", "topup"), "扫不到已知成员，正则坏了"
    assert not _calls("web", "definitelyNotAnSdkMethod")


def test_cli074_table_says_what_the_notice_asks_for():
    """值是**这条通知在叫他做什么**，不是 True。

    与 MUST_REACH / REMEDY_UI 同一条：判定标准得写下来，
    否则半年后没人知道该往表里加什么。
    """
    assert len(NOTICE_ACTIONS) >= 5
    for key, (method, clients, why) in NOTICE_ACTIONS.items():
        assert method and method[0].islower(), f"{key} 的动作不像 SDK 方法名"
        assert clients, f"{key} 一个端都不要求，进表没有意义"
        assert len(why) >= 15, f"{key} 的理由太敷衍：{why}"


@pytest.mark.parametrize("key", sorted(NOTICE_ACTIONS))
def test_cli074_the_action_a_notice_asks_for_is_reachable(key):
    method, clients, why = NOTICE_ACTIONS[key]
    for client in clients:
        assert _calls(client, method), (
            f"通知「{key[1]}」叫用户去做一件事，而 {client} 上没有 {method}() 的入口。\n"
            f"这条通知在叫他做什么：{why}"
        )


def test_cli074_declared_actions_exist_in_the_sdk():
    """写错一个方法名，上面那条会永远红，而人只会以为是界面没做。"""
    from tests.test_remedy_ui import REPO

    sdk = (REPO / "packages" / "core" / "src" / "client.ts").read_text(encoding="utf-8")
    for key, (method, _clients, _why) in NOTICE_ACTIONS.items():
        assert re.search(r"^  " + re.escape(method) + r"\s*\(", sdk, re.M), \
            f"{key} 声明的动作 {method}() 在 SDK 上不存在"


def test_cli074_declared_titles_are_really_sent_by_the_server():
    """表里的标题必须是服务端真的会发的。

    否则这张表会慢慢变成一堆过时的猜测——**和它要防的那种漂移一模一样**。
    带括号的那条是同一条通知的分支文案，按主标题核对。
    """
    from tests.test_remedy_ui import REPO

    server_src = "\n".join(
        p.read_text(encoding="utf-8") for p in (REPO / "server" / "app").rglob("*.py")
    )
    for _category, title in NOTICE_ACTIONS:
        base = title.split("（")[0]
        assert f'"{base}"' in server_src, f"服务端已经不发「{base}」了，表该清理"


# ------------------------------------------------------- APP-069 三条线在 App 上
def test_app069_the_three_lines_exist_on_the_app():
    """V84 把合作体 / 团队 / 开发者做在了网页上，App 至今一个都没有。

    这一批必须和通知一起做：**先发通知、界面下批再补，
    等于先把人叫醒再告诉他没事可做。**
    """
    app_src = _sources("app")
    for method in ("myTeams", "team", "teamSpends", "decideTeamSpend", "executeTeamSpend",
                   "myVentures", "ventureShares", "submitContribution", "confirmContribution",
                   "apiKeys", "createApiKey", "revokeApiKey", "webhooks", "createWebhook"):
        assert _calls("app", method), f"App 上没有 {method}() 的入口"
    # API-013 明文密钥只在创建时返回一次，界面必须把这件事说出来，
    # 否则用户关掉页面就永远拿不回来了
    assert "warning" in app_src and "signature_howto" in app_src
