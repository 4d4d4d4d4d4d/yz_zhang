"""SEC-060 对象级授权：146+ 个带资源 id 的端点，谁能碰谁的东西（99 号 spec）。

量出来的现状（V123 写 99 号 spec 时数的）：

    /api/v1 端点                292 个
    其中带路径参数的            166 个（方法 × 路径）
    碰到 403/forbidden 的测试    68 个文件

68 个文件里确实有大量越权断言，但**没有任何记账说明这 166 个里哪些做过
「把 id 换成别人的」这件事**。于是和 V122 的响应形状闸门同一个形状：
看起来覆盖了，实际覆盖率无人知晓。

业界把这一类叫 BOLA，并一致指出它为什么最难被发现：**它返回的是正常的
200 和一份有效数据**——只检查「有没有报错」的扫描器会直接放过。
要验它必须知道「哪个对象属于谁」，也就是用两个账号互相去拿对方的东西。
还有一条常被误解的：把 id 换成 UUID 不解决问题，那只是让枚举变慢。

本篇两层：

1. **覆盖记账**：每一个带参端点都要落进一条归属规则，规则说明「这个 id
   属于谁、谁可以碰」。新增一个带参端点而没有规则 → 红。
   规则按**资源**写而不是按端点写——同一个资源上的八个端点归属规则是同一条，
   逐条抄八遍只会让这张表没人维护。
2. **行为验**：对钱与身份那一批，真的用 B 的 token 去拿 A 的对象，
   断言不是 200。不比声明，比行为。
"""
import os
import re
import sys

import pytest

from tests.conftest import auth, bind_payout, register, topup, verify_user
from tests.test_task_flow import match_and_fund, publish_task

# ---------------------------------------------------------------- 归属规则
#
# (模式, 归属类别, 规则说明)
#
# 模式按 "VERB /path" 匹配（正则）。**顺序有意义**：先匹配到的那条生效，
# 所以更具体的规则写在前面。
#
# 五个类别，含义固定：
#   party     —— 资源属于特定当事人，第三方不得读写（**要行为验**）
#   public    —— 刻意公开，任何人可读（必须写明为什么公开）
#   admin     —— 需要管理员身份（另有 /admin 覆盖闸门 CLI-080 管着）
#   self      —— 路径参数是调用者自己的东西（自己的 id、自己持有的令牌），
#                不存在「换成别人的」这种攻击面
#   machine   —— /open/v1 走 API Key 主体，自有授权模型（机器委托那批测试管着）
OWNERSHIP_RULES: list[tuple[str, str, str]] = [
    # ---- 钱与合约：最高后果，逐条行为验 ----
    (r"^\w+ /contracts/", "party",
     "合约只对发布方与执行方开放（管理员在纠纷场景另有入口）。"
     "第三方读到的是金额、条款与分账明细；写到的是托管与放款"),
    (r"^\w+ /wallet/withdraw-requests/", "admin",
     "提现复核是运营动作，且大额出款要四眼原则（V99）——两个不同管理员先后确认"),
    (r"^\w+ /anchors/contracts/", "party",
     "单合约的存证条目属于合约当事人；取证时由平台出证据包"),
    (r"^\w+ /legal/disputes/.*/evidence-export", "party",
     "证据包含对话与交付物原文，只对纠纷当事人与管理员开放"),
    (r"^\w+ /disputes/.*/(verdict|appeal-verdict)$", "admin",
     "裁决与复核裁决是平台动作，当事人不能自己给自己判"),
    (r"^\w+ /disputes/", "party",
     "纠纷的答辩、和解、申诉只对当事人开放：第三方读到的是双方陈述与证据"),
    # ---- 身份与私密 ----
    (r"^GET /files/.*/secure$", "party",
     "私密影像（证件、交付物）按引用鉴权，只有有权方取得到"),
    (r"^GET /files/", "public",
     "公开附件按不可猜测的文件名提供，且响应带 `default-src 'none'; sandbox`；"
     "**不含证件与交付物**，那些走 /secure"),
    (r"^\w+ /conversations/", "party",
     "会话只对参与者开放。读到别人的私聊是泄露，往别人的会话里发消息是冒名"),
    (r"^POST /messages/.*/recall$", "party",
     "只能撤回自己发的消息：message_id 是别人的时候必须拒，否则等于可以替别人删话"),
    (r"^POST /auth/sessions/.*/revoke$", "self",
     "吊销的是自己的设备会话；session_id 属于调用者本人"),
    (r"^POST /auth/oauth/", "machine",
     "provider 是第三方登录渠道名，不是用户对象"),
    (r"^\w+ /legal/consents/", "self",
     "scope 是同意项的名字（如 id_image），不是别人的对象；授权只作用于自己"),
    (r"^DELETE /notifications/devices/", "self",
     "token 是调用者自己的推送令牌"),
    (r"^POST /notifications/.*/read$", "party",
     "只能把自己的通知标成已读：别人的 notification_id 必须拒，"
     "否则等于可以替别人清掉催办与临期提醒（V100 那批的价值全靠他看见）"),
    # ---- 任务：公开可见的那部分与当事人的那部分要分开 ----
    (r"^GET /tasks/.*/(applications|agent-runs|trip|final-report|eligible-agents|recommendations)$",
     "party",
     "报名名单、Agent 运行记录、行程、结项报告只对发布方（及相应执行方）开放"),
    (r"^POST /tasks/.*/(accept-delivery|reject-delivery|cancel|publish|decompositions|invitations|verification|agent-apply|agent-run)$",
     "party", "这些是发布方的动作，执行方与第三方都不得代为执行"),
    (r"^POST /tasks/.*/(deliver|checkin|progress|sos|trip-share|experience-post)$",
     "party", "这些是执行方的动作：交付、打卡、求助、行程分享"),
    (r"^POST /tasks/.*/(applications|reviews|disputes|bookmark)$", "party",
     "报名与评价要满足身份条件（评价限当事人、报名限非发布方）"),
    (r"^DELETE /tasks/.*/bookmark$", "self", "取消的是自己的收藏：task_id 是收藏对象，收藏记录按调用者自己的 id 存"),
    (r"^PATCH /tasks/", "party", "改任务限发布方：标题、预算、验收标准都在这个接口里"),
    (r"^GET /tasks/.*/(reviews|progress|tree|dispute)$", "public",
     "评价、进度、子任务树、是否有纠纷：对任务可见范围内的人公开，"
     "是买方决策与平台公信的一部分；不含金额明细与联系方式"),
    (r"^GET /tasks/", "public",
     "任务详情在广场上本就公开（未登录也能看，SPACE-004 同一条规矩）；"
     "精确地址等敏感字段由响应层按身份过滤"),
    # ---- 报名 / 邀约 ----
    (r"^POST /applications/", "party",
     "接受报名限发布方，撤回报名限报名人本人"),
    (r"^POST /invitations/", "party", "邀约的接受与拒绝限被邀请人：替别人接单会把他绑进一份合约"),
    # ---- 团队 / 合作体 ----
    (r"^\w+ /teams/.*/spends", "party",
     "预算申请、审批、执行按团队成员档位（owner/admin/member）鉴权"),
    (r"^\w+ /teams/", "party",
     "团队详情与成员管理只对成员开放，改动按档位"),
    (r"^\w+ /ventures/.*/payout-proposals", "party",
     "分配提案与投票限合作体成员（一致同意治理，613f386 那批）"),
    (r"^\w+ /ventures/", "party",
     "合作体的份额、贡献、分配、组织记录只对成员开放"),
    # ---- 核验台 ----
    (r"^POST /verification-orders/.*/claim$", "party",
     "抢单要满足核验人资格（CERT 资质门槛），不是任何登录用户都能接核验单"),
    (r"^POST /verification-orders/.*/outcome$", "party",
     "结论只能由抢到这一单的核验人提交：别人提交的结论会影响任务验收"),
    (r"^GET /verification-orders/", "party", "核验单详情只对相关方开放：里面有任务内容与核验结论"),
    (r"^GET /missions/.*/steps/.*/reviews$", "party", "子步骤核验记录由核验台内部使用"),
    (r"^\w+ /missions/", "party", "编排任务属于创建它的人：取消与推进别人的 mission 必须拒"),
    # ---- 开放 API / 机器 ----
    (r"^\w+ /open/v1/", "machine",
     "按 API Key 主体与机器委托额度鉴权，自有授权模型（test_machine_delegation）"),
    (r"^\w+ /developer/", "self",
     "API Key 与 Webhook 属于创建它的开发者本人"),
    # ---- 社交与内容：公开的那部分与自己的那部分 ----
    (r"^GET /spaces/", "public",
     "公开空间就是要给别人看的（SPACE-004）；未发布/隐私/封禁/注销统一 404"),
    (r"^GET /users/.*/(contents|reviews|follow-stats)$", "public",
     "作品、口碑、关注计数是公开画像的一部分——「让别人了解你」是产品定位本身"),
    (r"^GET /users/", "public",
     "公开资料按隐私设置过滤后开放；手机号等敏感字段不在公开字段白名单里"),
    (r"^(PUT|DELETE) /users/.*/follow$", "self",
     "关注/取关是调用者自己的动作，user_id 是对象而不是凭据"),
    (r"^POST /users/.*/block$", "self", "拉黑写进的是调用者自己的名单，user_id 是被拉黑的对象"),
    (r"^\w+ /friends/", "self", "好友关系与请求属于调用者本人：决定别人收到的请求必须拒"),
    (r"^\w+ /circles/.*/members/", "party",
     "圈层成员的审批与移除按圈层管理员鉴权"),
    (r"^POST /circles/.*/join$", "self", "加入圈层是调用者自己的动作，circle_id 是对象而不是凭据"),
    (r"^GET /circles/", "public",
     "圈层信息、动态、成员、统计按圈层可见性开放（私密圈层另有过滤）"),
    (r"^(PATCH|DELETE) /contents/", "party", "改/删内容限作者：别人的 content_id 必须拒，否则可以删掉他人的作品"),
    (r"^POST /contents/.*/publish$", "party", "发布限作者：把别人的草稿发出去等于替他公开未定稿的内容"),
    (r"^POST /contents/.*/(comments|like)$", "self",
     "评论与点赞是调用者自己的动作，content_id 是被评论的对象"),
    (r"^GET /contents/", "public",
     "已发布内容与其评论对所有人公开——内容本来就是发给人看的；"
     "未发布的草稿不在此列（按作者过滤），敏感字段不进公开响应"),
    (r"^DELETE /subscriptions/", "self", "退订的是自己的订阅：sub_id 属于调用者，别人的 id 必须拒"),
    (r"^POST /coupons/.*/claim$", "self", "领券是调用者自己的动作：券归领取人，coupon_id 只是券的种类"),
    (r"^\w+ /decompositions/", "party", "分解提案属于母任务的发布方：确认它会真的生成子任务并分走预算"),
    (r"^POST /support/tickets/.*/escalate-to-dispute$", "party",
     "工单升级为纠纷限提单人：替别人开纠纷会冻结他的合约"),
    # ---- 运营后台 ----
    (r"^\w+ /admin/", "admin",
     "后台端点统一要求管理员；逐条覆盖由 CLI-080 闸门管着（V101）"),
]

CATEGORIES = {"party", "public", "admin", "self", "machine"}
EXCUSE_WORDS = ("还没做", "待补", "TODO", "以后", "下一批", "暂时")


def _scoped_endpoints() -> list[str]:
    """所有带路径参数的 /api/v1 端点，形如 "GET /tasks/{task_id}"。"""
    from app.main import app

    out = []
    for path, ops in app.openapi()["paths"].items():
        if not path.startswith("/api/v1") or "{" not in path:
            continue
        for verb in ops:
            out.append(f"{verb.upper()} {path[len('/api/v1'):]}")
    return sorted(out)


def _match(endpoint: str) -> tuple[str, str] | None:
    for pattern, category, rule in OWNERSHIP_RULES:
        if re.search(pattern, endpoint):
            return category, rule
    return None


def test_sec060_scanner_actually_finds_the_endpoints():
    """扫不到等于全绿，是最糟的一种绿。"""
    eps = _scoped_endpoints()
    assert len(eps) >= 150, f"只扫到 {len(eps)} 个带参端点，提取逻辑可能坏了"
    for known in ("POST /contracts/{contract_id}/fund",
                  "GET /conversations/{conv_id}/messages"):
        assert known in eps, f"扫不到已知端点 {known}"
    assert "GET /not-a-real-endpoint/{x}" not in eps


def test_sec060_every_scoped_endpoint_has_an_ownership_rule():
    """每一个带资源 id 的端点都要落进一条归属规则。

    **这一条是为「下一个加带 id 端点的人」准备的**：
    他不会去读 99 号 spec，但他会看到这里红。
    """
    unmatched = [e for e in _scoped_endpoints() if _match(e) is None]
    assert not unmatched, (
        f"这些带资源 id 的端点没有归属规则（共 {len(unmatched)} 个）：\n  "
        + "\n  ".join(unmatched)
        + "\n在 OWNERSHIP_RULES 里写明这个 id 属于谁、谁可以碰。"
    )


def test_sec060_rules_are_well_formed_and_none_are_dead():
    """类别合法、理由是人话、且每条规则都真的匹配到了端点。

    留着匹配不到任何端点的规则，会掩护掉真正该被看的那些
    （V105 的 `test_cli072_declared_table_has_no_stale_entries` 同一条道理）。
    """
    eps = _scoped_endpoints()
    for pattern, category, rule in OWNERSHIP_RULES:
        assert category in CATEGORIES, f"{pattern} 的类别不合法：{category}"
        assert len(rule) >= 15, f"{pattern} 的规则说明太敷衍：{rule}"
        bad = [w for w in EXCUSE_WORDS if w in rule]
        assert not bad, f"{pattern} 的说明里有欠账词 {bad}——那属于台账，不属于这张表"
        assert any(re.search(pattern, e) for e in eps), (
            f"规则 {pattern} 匹配不到任何端点，已经死了"
        )


def test_sec060_public_rules_say_why_they_are_public():
    """声称公开的，必须写明为什么公开。

    **「公开」是这张表里唯一可以用来偷懒的类别**——把一条拿不准的端点标成
    public 就不用做行为验了。所以它的说明要求最高：要能看出这是一个产品判断，
    而不是一句「本来就是公开的」。
    """
    for pattern, category, rule in OWNERSHIP_RULES:
        if category != "public":
            continue
        assert len(rule) >= 25, f"{pattern} 声称公开，理由太短：{rule}"
        # 必须提到「为什么可以给别人看」或「敏感字段怎么处理」
        assert any(k in rule for k in ("公开", "给别人看", "过滤", "白名单", "可见")), (
            f"{pattern} 的公开理由没说清敏感字段怎么处理：{rule}"
        )


def test_sec060_money_and_identity_are_never_public():
    """钱与身份相关的端点**不得**被标成 public。

    这一条是防我自己的：上面那张表是我写的，而把一条难判的端点标成 public
    是最省事的做法。钱、合约、纠纷、私聊、私密影像——这些一旦标成公开，
    覆盖记账就从保护变成了掩护。
    """
    sensitive = ("/contracts/", "/wallet/", "/disputes/", "/conversations/",
                 "/messages/", "/secure", "/evidence-export", "/anchors/")
    for endpoint in _scoped_endpoints():
        if not any(s in endpoint for s in sensitive):
            continue
        matched = _match(endpoint)
        assert matched, endpoint
        assert matched[0] != "public", (
            f"{endpoint} 被标成 public，而它属于钱/身份那一类：{matched[1]}"
        )


# ------------------------------------------------- 行为验：B 去拿 A 的东西
@pytest.fixture()
def outsider(client):
    """一个与任何资源都无关的第三方账号。"""
    u = register(client, "13800088001", "第三方")
    verify_user(client, u)
    return u


def test_sec060_outsider_cannot_read_someone_elses_contract(client, requester, worker, outsider):
    """第三方读不到别人的合约——**读到的是金额、条款与分账明细**。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)

    for path in (f"/api/v1/contracts/{cid}",
                 f"/api/v1/contracts/{cid}/signatures",
                 f"/api/v1/contracts/{cid}/settlements",
                 f"/api/v1/contracts/{cid}/change-orders"):
        r = client.get(path, headers=auth(outsider))
        assert r.status_code in (403, 404), (
            f"{path} 对第三方返回了 {r.status_code}：{r.text[:200]}"
        )


def test_sec060_outsider_cannot_move_money_on_someone_elses_contract(
        client, requester, worker, outsider):
    """第三方动不了别人合约上的钱。**这是这一篇里后果最重的一条。**"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)

    for path in (f"/api/v1/contracts/{cid}/fund",
                 f"/api/v1/contracts/{cid}/sign"):
        r = client.post(path, headers=auth(outsider))
        assert r.status_code in (403, 404), (
            f"{path} 让第三方动了合约：{r.status_code} {r.text[:200]}"
        )
    r = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(outsider))
    assert r.status_code in (400, 403, 404), f"第三方触发了放款：{r.text[:200]}"


def test_sec060_executor_cannot_perform_requester_actions(client, requester, worker):
    """**当事人之间也要分**：执行方不能替发布方验收放款。

    这一条比「挡住第三方」更容易被漏——两个人都是合约当事人，
    只按「是不是当事人」判断就会放行，而验收是发布方单方面的权利。
    """
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))

    r = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(worker))
    assert r.status_code in (403, 404), f"执行方自己把钱放给了自己：{r.text[:200]}"


def test_sec060_outsider_cannot_read_or_write_someone_elses_conversation(
        client, requester, worker, outsider):
    """第三方读不到别人的私聊，也发不进去。

    **读到别人的私聊是泄露，往别人的会话里发消息是冒名**——后者更糟。
    """
    conv = client.post("/api/v1/conversations/direct",
                       json={"user_id": worker["id"]}, headers=auth(requester))
    assert conv.status_code in (200, 201), conv.text
    cid = conv.json()["id"]

    r = client.get(f"/api/v1/conversations/{cid}/messages", headers=auth(outsider))
    assert r.status_code in (403, 404), f"第三方读到了私聊：{r.status_code} {r.text[:200]}"
    r = client.post(f"/api/v1/conversations/{cid}/messages",
                    # 字段名必须写对（是 content 不是 body）：写错会得到 422，
                    # 而 **422 不是「被鉴权挡住」**——断言若宽到「不是 200」，
                    # 这条用例就会因为自己把请求写坏而通过。
                    json={"content": "我是冒名进来的"}, headers=auth(outsider))
    assert r.status_code in (403, 404), f"第三方发进了别人的会话：{r.text[:200]}"


def test_sec060_outsider_cannot_read_someone_elses_dispute(client, requester, worker, outsider):
    """第三方读不到别人的纠纷——里面是双方陈述与证据。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付不符合约定要求"}, headers=auth(requester))
    assert d.status_code in (200, 201), d.text
    did = d.json()["id"]

    for path in (f"/api/v1/disputes/{did}",
                 f"/api/v1/disputes/{did}/statements",
                 f"/api/v1/legal/disputes/{did}/evidence-export"):
        r = client.get(path, headers=auth(outsider))
        assert r.status_code in (403, 404), (
            f"{path} 对第三方返回了 {r.status_code}：{r.text[:200]}"
        )


def test_sec060_outsider_cannot_decide_someone_elses_dispute(client, requester, worker, outsider):
    """第三方下不了别人纠纷的裁决——**裁决是平台动作**。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    did = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                      json={"reason": "交付不符合约定要求"}, headers=auth(requester)).json()["id"]

    r = client.post(f"/api/v1/disputes/{did}/verdict",
                    json={"outcome": "refund_requester", "reason": "我说的"},
                    headers=auth(outsider))
    assert r.status_code in (403, 404), f"第三方下了裁决：{r.text[:200]}"


def test_sec060_outsider_cannot_approve_withdrawals(client, outsider):
    """第三方批不了提现——提现是钱**离开平台**的那一步。"""
    user = register(client, "13800088002", "提现人")
    verify_user(client, user)
    topup(client, user, 300000)
    bind_payout(client, user)
    req = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 20000},
                      headers=auth(user))
    assert req.status_code == 200, req.text
    rid = req.json().get("request_id") or req.json().get("id")

    r = client.post(f"/api/v1/wallet/withdraw-requests/{rid}/approve", headers=auth(outsider))
    assert r.status_code in (403, 404), f"第三方批了提现：{r.text[:200]}"


def test_sec060_outsider_cannot_read_someone_elses_applications(client, requester, worker, outsider):
    """第三方看不到别人任务的报名名单（里面是报名人画像与报价）。"""
    task = publish_task(client, requester, budget_cents=30000)
    client.post(f"/api/v1/tasks/{task['id']}/applications",
                json={"message": "我可以做"}, headers=auth(worker))
    r = client.get(f"/api/v1/tasks/{task['id']}/applications", headers=auth(outsider))
    assert r.status_code in (403, 404), (
        f"第三方读到了报名名单：{r.status_code} {r.text[:200]}"
    )


def test_sec060_outsider_cannot_patch_someone_elses_task(client, requester, outsider):
    """第三方改不了别人的任务。"""
    task = publish_task(client, requester, budget_cents=30000)
    r = client.patch(f"/api/v1/tasks/{task['id']}", json={"title": "我改了"},
                     headers=auth(outsider))
    assert r.status_code in (403, 404), f"第三方改了别人的任务：{r.text[:200]}"


def test_sec060_party_can_still_read_what_the_outsider_cannot(client, requester, worker, outsider):
    """当事人读得到、第三方读不到——同一个 id，两种结果。

    这才是 BOLA 验法的完整形态。**只断言「别人拿不到」会被「这个 id 根本
    不存在」蒙过去**：如果上面那些 id 其实都没建出来，服务端会一律 404，
    而 `in (403, 404)` 的断言会全部通过——**一整组测试全绿，而它什么都没验**。
    所以这里反向确认同一个 id 对当事人是 200。

    （这条断言原先被我写成一个只有注释、`assert True` 的占位测试。
    一个断言恒真的测试比没有测试更糟：它出现在绿色的清单里。）
    """
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)

    mine = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester))
    assert mine.status_code == 200, f"当事人自己都读不到，这个 id 是假的：{mine.text[:200]}"
    theirs = client.get(f"/api/v1/contracts/{cid}", headers=auth(outsider))
    assert theirs.status_code in (403, 404)
    assert mine.status_code != theirs.status_code, "两种身份拿到同样的结果，没有在鉴权"
