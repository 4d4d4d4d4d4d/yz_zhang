"""CLI-077 「在管理后台做」必须是一句会红的承诺（71 号 spec）。

V82 的覆盖闸门有一张豁免表，里面写着：

    "/wallet/withdraw-requests/{x}/approve": "提现人审是风控岗位的动作，在管理后台做",

理由是对的——**那确实不该是用户按钮**。但这句话同时是一个承诺：
「在管理后台做」。而没有任何东西核对过那个地方是否真的有这一条。

V91 把提现接通之后，大额进人审的钱就冻在用户账上，
**没有任何界面能放行**。三万块，没有一个按钮。

更结构性的一层：同一个闸门里写着

    if "/admin" in rel or "/jobs" in rel:
        continue          # 运营后台与调度端点不面向普通客户端

于是**整个管理后台在所有闸门的覆盖范围之外**——而真正动钱的决定大半
发生在那里：放款审批、纠纷裁决、可疑活动复核、税款缴库。
"""
import re
from pathlib import Path

import pytest

from tests.test_client_contract_coverage import CLIENT_EXEMPT

# 扫描实现只有一份（tests/clientscan.py）。这个文件原本自带一份 `_calls`，
# 而那一份漏了「组件得挂上」那一层——红验时把 `<WithdrawReview />` 摘掉，
# 闸门照样是绿的。**第二份实现必然抄漏**，对测试代码同样成立。
from tests.clientscan import calls as _client_calls
from tests.clientscan import sdk_has, sources


def _calls(method: str) -> bool:
    return _client_calls("admin", method)


# 运营侧必须可达的能力 -> 为什么
#
# 判定标准：**这件事只有运营/风控能做，而不做就有人的钱或权利卡住。**
# 报表、指标一类不进表——那些不做只是不好看，不会把人卡住。
ADMIN_CONSOLE: dict[str, str] = {
    "withdrawRequests": (
        "大额提现进人审后，钱冻在用户账上。列不出来就等于没人知道有钱等着放行"
    ),
    "decideWithdraw": (
        "**进了人审就再也出不来**：端点是通的，而此前没有任何界面能打它。"
        "V91 把提现接通之后，这条分支从理论变成了活的陷阱"
    ),
    "adminReports": "举报堆着没人看，被举报的内容就一直挂在站上",
    "resolveReport": "举报要能处置，否则举报入口只是一个许愿池",
    "banUser": "封禁是处置违规账号的唯一手段；不做就只能看着对方继续接单",
    "adminAuditLog": (
        "**谁批了那笔三万块**——在这条接上之前，这个问题只能靠查数据库回答。"
        "审计日志不可读，等于留痕只留给了事后取证，日常复核用不上"
    ),
    "banImpact": (
        "封禁是不可逆的处置，而这个人手上可能有几笔在途合约与一笔托管资金。"
        "V58 专门算了影响面，而后台此前直接调 banUser——**管理员在盲封**"
    ),
    "platformFinance": (
        "平台自己的钱：佣金收了多少、结算走了多少、账上还剩多少。"
        "看不到就只能查库，而结算是个动钱的动作"
    ),
    "settlePlatform": (
        "结算把佣金从平台账户划走，必须是个留痕的后台动作而不是一条脚本"
    ),
    "amlActivities": (
        "可疑活动躺在库里没人复核。合规官的队列不可读，"
        "《反洗钱法》要求的复核与报送判断就无处发生"
    ),
    "reviewAmlActivity": "复核结论要落下来（cleared / 待报送），否则队列只会越堆越长",
}


def test_cli077_scanner_can_see_the_admin_page():
    """扫不到等于全绿，是最糟的一种绿。"""
    src = sources("admin")
    assert len(src) > 2000, "管理后台源码短得不像真的——路径写错了？"
    assert _calls("adminMetrics"), "扫不到已知成员，正则或路径坏了"
    assert not _calls("definitelyNotAnSdkMethod")


def test_cli077_table_says_why():
    assert len(ADMIN_CONSOLE) >= 5
    for method, why in ADMIN_CONSOLE.items():
        assert len(why) >= 15, f"{method} 的理由太敷衍：{why}"
        assert sdk_has(method), f"{method} 在 SDK 上不存在"


@pytest.mark.parametrize("method", sorted(ADMIN_CONSOLE))
def test_cli077_admin_capability_is_reachable(method):
    assert _calls(method), (
        f"管理后台里没有任何地方调用 {method}()。\n"
        f"不做会怎样：{ADMIN_CONSOLE[method]}"
    )


def test_cli077_exemptions_that_promise_the_admin_console_are_kept():
    """**豁免理由里说「在管理后台做」的，管理后台必须真的做得到。**

    一张豁免表如果没人核对它的理由，它就只是一句无人负责的承诺——
    提现复核台整整缺席了这么久，就是这么漏的。
    """
    promised = {path: why for path, why in CLIENT_EXEMPT.items()
                if "管理后台" in why or "后台" in why}
    assert promised, "豁免表里一条「在管理后台做」都没有？断言写错了"

    # 路径 -> 兑现它的 SDK 方法（表里只放「承诺了管理后台」的那些）
    fulfilled_by = {
        "/wallet/withdraw-requests/{x}/approve": "decideWithdraw",
        "/wallet/withdraw-requests/{x}/reject": "decideWithdraw",
    }
    for path in promised:
        method = fulfilled_by.get(path)
        assert method, (
            f"豁免 {path} 的理由承诺了「在管理后台做」，"
            f"但这条测试里没有登记是哪个 SDK 方法兑现它。\n"
            f"新增这类豁免时要一起登记——否则又是一句没人核对的承诺。"
        )
        assert _calls(method), (
            f"豁免 {path} 时写的理由是「{promised[path]}」，"
            f"而管理后台里没有 {method}() 的调用。**承诺没有兑现。**"
        )
