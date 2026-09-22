"""CLI-075 会危及人身、账号与钱的能力，必须有人能按（68 号 spec）。

探针换了个方向问：**这个产品里有多少能力，是两个端加起来都没人能碰到的？**

    SDK: 245   web: 137   app: 58
    两端都没人调用: 105

其中最刺眼的一条是 `sos`。服务端实现得很完整，注释还写着：

    LAW-031 这里**刻意不做**位置同意校验：PIPL 第十三条第(四)项把
    「紧急情况下为保护自然人的生命健康所必需」列为无需同意的处理情形。
    让求助按钮卡在合规弹窗上，是把合规做成了事故。

写这句话的时候，那个按钮在任何一个端上都不存在。
"""
import pytest

from tests.conftest import auth, register, topup, verify_user
from tests.test_remedy_ui import _calls
from tests.test_task_flow import match_and_fund, publish_task

# SDK 方法 -> (必须能按到的端, 按不到会怎样)
#
# 判定标准：**按不到这一条，用户会面临人身风险、账号被别人继续用，
# 或者一笔钱/一个权利落空。** 不满足的不进表——
# 105 条全塞进来，这张表就变成一份待办清单，而不是一条红线。
MUST_BE_REACHABLE: dict[str, tuple[tuple[str, ...], str]] = {
    "sos": (
        ("web", "app"),
        "上门、夜间、独自面对陌生人的那群人。服务端连「求助不该被合规弹窗挡住」"
        "（PIPL 十三条四项）都想清楚了，却没有给他们那个按钮",
    ),
    "setTripShare": (
        ("web", "app"),
        "行程分享是出事前的预防，出事后再开就晚了",
    ),
    "changePassword": (
        ("web", "app"),
        "怀疑密码泄露时，这是用户唯一能立刻自救的动作；"
        "没有它，他能做的只有注销账号",
    ),
    "openDirect": (
        ("web", "app"),
        "任务会话要等**合约托管成功**才自动建。没有这条，"
        "「你几点能到」「要不要带工具」这些成交前的话，双方在产品里说不了",
    ),
    "recallMessage": (
        ("web", "app"),
        "服务端给了 2 分钟撤回窗口。发错人、手滑把手机号发出去，"
        "没有入口就永远收不回来",
    ),
    "myInvitations": (
        ("web", "app"),
        "服务端**会发**「收到任务邀约」这条通知；看不到它就是一单活白白错过",
    ),
    "acceptInvitation": (
        ("web", "app"),
        "同上——通知把人叫来了，他得能当场应下来；错过的是一单已经点名给他的活",
    ),
}


def test_cli075_table_says_what_happens_if_you_cannot_press_it():
    """值是**按不到会怎样**，不是 True。

    与 MUST_REACH / REMEDY_UI / NOTICE_ACTIONS 同一条：
    判定标准得写下来，否则这张表会退化成「还没做的功能」清单。
    """
    assert len(MUST_BE_REACHABLE) >= 5
    for method, (clients, why) in MUST_BE_REACHABLE.items():
        assert clients, f"{method} 一个端都不要求，进表没有意义"
        assert len(why) >= 20, f"{method} 的理由太敷衍：{why}"


@pytest.mark.parametrize("method", sorted(MUST_BE_REACHABLE))
def test_cli075_capability_is_reachable(method):
    clients, why = MUST_BE_REACHABLE[method]
    for client in clients:
        assert _calls(client, method), (
            f"{client} 上没有任何地方调用 {method}()。\n按不到会怎样：{why}"
        )


def test_cli075_scanner_self_check():
    """扫不到等于全绿。"""
    assert _calls("app", "topup") and _calls("web", "topup")
    assert not _calls("app", "definitelyNotAnSdkMethod")


# ------------------------------------------------------- GEO-023 求助真的通得了
def test_geo023_sos_notifies_the_other_party_and_returns_guidance(client, requester):
    """服务端这条一直是通的——缺的只是按钮。

    这里把它钉住，顺便钉住**响应的形状**：SDK 此前声明成 `{id, notified}`，
    服务端返回的是 `{ok, guidance}`，而 `guidance` 是这一刻唯一对用户
    有用的那句话。
    """
    from app.core.db import SessionLocal
    from app.modules.notification.models import Notification

    worker = register(client, "13800098001", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    r = client.post(f"/api/v1/tasks/{task['id']}/sos",
                    json={"lat": 31.2, "lng": 121.5}, headers=auth(worker))
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"ok", "guidance"}, f"响应形状变了：{body}"
    assert "110" in body["guidance"], "指引里必须给出报警电话"

    with SessionLocal() as db:
        titles = [n.title for n in db.query(Notification)
                  .filter(Notification.user_id == requester["id"]).all()]
    assert "对方发出紧急求助" in titles, "求助没有通知到任务对方"


def test_geo023_sos_is_only_for_the_two_parties(client, requester):
    """路人不能替别人求助——那会变成一个骚扰通道。"""
    worker = register(client, "13800098010", "执行者")
    verify_user(client, worker, name="执行")
    outsider = register(client, "13800098011", "路人")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    r = client.post(f"/api/v1/tasks/{task['id']}/sos",
                    json={"lat": 31.2, "lng": 121.5}, headers=auth(outsider))
    assert r.status_code == 403


def test_geo023_sos_does_not_require_location_consent(client, requester):
    """LAW-031 求助**刻意不做**位置同意校验。

    PIPL 第十三条第(四)项把「紧急情况下为保护自然人的生命健康所必需」
    列为无需同意的处理情形。**让求助按钮卡在合规弹窗上，是把合规做成了事故。**
    """
    from app.modules.legal import consent

    worker = register(client, "13800098020", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    # 明确撤回位置同意，再求助——必须照样通
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        # 先同意再撤回：撤回一个从没同意过的项，服务端会 409（这是对的）
        consent.grant(db, worker["id"], "location")
        db.commit()
    with SessionLocal() as db:
        consent.revoke(db, worker["id"], "location")
        db.commit()
    r = client.post(f"/api/v1/tasks/{task['id']}/sos",
                    json={"lat": 31.2, "lng": 121.5}, headers=auth(worker))
    assert r.status_code == 201, f"撤回位置同意后求助被拦了：{r.text}"
