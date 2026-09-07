"""DSPC-001~040 纠纷的当事人闭环（36 号 spec）。

纠纷开出来以后，当事人在客户端上是**哑的**。
`client.ts` / `web/src` / `app` 全文搜 `statement` / `答辩`：**零命中**。
七个当事人侧端点里客户端只接了一个（发起纠纷）；和解的两个 SDK 方法写好了
却没有任何界面调用，等于没写。

后果不是「慢一点」。服务端把两造兼听当作裁决的硬性前置：

    if not _respondent_had_voice(db, dispute, task):
        raise conflict("被诉方尚未答辩且答辩期未过，暂不可裁决", "response_window_open")

而被诉方永远不可能 `spoke`——没有任何客户端能写入 `DisputeStatement`。
于是这个判断的第一条分支在生产里是死代码，每次都落到「等满 48 小时」：
**平台上线后的每一份处理决定都是缺席裁决**，被诉方从未获得陈述的手段。
"""
import re
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.modules.account.models import utcnow
from app.modules.dispute.models import Dispute

from .conftest import auth, register, topup
from .test_task_flow import match_and_fund, publish_task

CLIENT_TS = "../packages/core/src/client.ts"


def open_dispute(client, requester, worker, reason="交付不符约定，要求重做或退款"):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/disputes", json={"reason": reason},
                    headers=auth(requester))
    assert r.status_code == 201, r.text
    return task, r.json()


def make_admin(client, phone="13922200099"):
    admin = register(client, phone, "仲裁员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


# ---------- DSPC-001 被诉方真的能开口，裁决前置真的能被满足 ----------
def test_dspc001_respondent_can_speak_and_that_unblocks_the_verdict(client, requester, worker):
    """改造前这条路走不通：没有任何客户端能写入 DisputeStatement。

    这里走的是完整的当事人路径——被诉方从任务 id 找到纠纷、读事由、答辩，
    然后裁决前置立刻满足，不必等满答辩期。
    """
    task, dispute = open_dispute(client, requester, worker)
    admin = make_admin(client)

    # 答辩期内、被诉方未答辩 → 不得裁决（DSP-005 原有保障）
    blocked = client.post(f"/api/v1/disputes/{dispute['id']}/verdict",
                          json={"executor_share_bps": 5000, "reason": "各担一半"},
                          headers=auth(admin))
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "response_window_open"

    # 被诉方（worker）只知道任务 id —— 通知里就只说「任务 #N 有纠纷」
    found = client.get(f"/api/v1/tasks/{task['id']}/dispute", headers=auth(worker))
    assert found.status_code == 200, found.text
    assert found.json()["id"] == dispute["id"]
    assert found.json()["respondent_id"] == worker["id"]
    assert found.json()["respondent_spoke"] is False

    spoke = client.post(f"/api/v1/disputes/{dispute['id']}/statements",
                        json={"content": "已按约定完成，附现场照片与验收单。"},
                        headers=auth(worker))
    assert spoke.status_code == 201, spoke.text
    assert spoke.json()["role"] == "respondent"

    # 前置满足 → 不必等满答辩期就能裁决
    ok = client.post(f"/api/v1/disputes/{dispute['id']}/verdict",
                     json={"executor_share_bps": 5000, "reason": "双方各有责任"},
                     headers=auth(admin))
    assert ok.status_code == 200, ok.text
    assert client.get(f"/api/v1/disputes/{dispute['id']}",
                      headers=auth(worker)).json()["respondent_spoke"] is True


def test_dspc010_respondent_cannot_be_locked_out_by_not_knowing_the_dispute_id(
    client, requester, worker,
):
    """按任务查纠纷是被诉方进入这场程序的唯一一条路。

    发起方能从 `POST /tasks/{id}/disputes` 的返回值里拿到 id；
    被诉方拿不到，而改造前全站没有任何「按任务查纠纷」的入口。
    """
    task, _ = open_dispute(client, requester, worker)
    assert client.get(f"/api/v1/tasks/{task['id']}/dispute",
                      headers=auth(worker)).status_code == 200
    # 无关第三方看不到
    outsider = register(client, "13922200077", "路人")
    assert client.get(f"/api/v1/tasks/{task['id']}/dispute",
                      headers=auth(outsider)).status_code == 403


def test_dspc010_task_without_dispute_returns_404(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    assert client.get(f"/api/v1/tasks/{task['id']}/dispute",
                      headers=auth(requester)).status_code == 404


# ---------- DSPC-011 客户端算不出来的事实由服务端给 ----------
def test_dspc011_deadline_comes_from_config_not_from_a_hardcoded_48(
    client, requester, worker, monkeypatch,
):
    """答辩期长度是服务端配置，客户端不该猜也不该硬编码。"""
    monkeypatch.setattr(settings, "DISPUTE_RESPONSE_HOURS", 12)
    task, dispute = open_dispute(client, requester, worker)
    d = client.get(f"/api/v1/disputes/{dispute['id']}", headers=auth(worker)).json()

    db = SessionLocal()
    created = db.get(Dispute, dispute["id"]).created_at
    db.close()
    assert d["response_deadline"].startswith((created + timedelta(hours=12)).isoformat()[:16])


def test_dspc012_open_notification_carries_the_task_and_the_configured_hours(
    client, requester, worker, monkeypatch,
):
    """通知此前写死「请在 48 小时内协商或提交证据」，而提交证据没有入口。"""
    monkeypatch.setattr(settings, "DISPUTE_RESPONSE_HOURS", 36)
    task, _ = open_dispute(client, requester, worker)
    notices = client.get("/api/v1/notifications", headers=auth(worker)).json()
    body = next(n for n in notices if n["title"] == "纠纷已受理")["body"]
    assert "36 小时" in body, body
    assert f"#{task['id']}" in body       # 被诉方要能知道是哪个任务
    assert "48" not in body               # 改了配置就不能再说 48


def test_dspc013_dispute_notice_ignores_the_category_switch(client, requester, worker):
    """允许用一个通知开关放弃自己的陈述权，是把公平交给了默认设置。"""
    r = client.put("/api/v1/notifications/prefs?category=task&enabled=false",
                   headers=auth(worker))
    assert r.status_code == 200, r.text
    open_dispute(client, requester, worker)
    notices = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any(n["title"] == "纠纷已受理" for n in notices), \
        "关掉 task 类通知不该连「有人对你发起纠纷」都收不到"


# ---------- DSPC-030 appealable 与端点是同一个判断 ----------
def test_dspc030_appealable_flag_and_the_appeal_endpoint_never_disagree(
    client, requester, worker,
):
    """客户端画出来的按钮和端点真正的准入不允许有两份实现。

    两个方向都验：为真时端点必须放行，为假时端点必须拒绝。
    """
    task, dispute = open_dispute(client, requester, worker)
    admin = make_admin(client)
    did = dispute["id"]

    # 未结案：不可申诉，端点也拒绝
    d = client.get(f"/api/v1/disputes/{did}", headers=auth(worker)).json()
    assert d["appealable"] is False
    assert client.post(f"/api/v1/disputes/{did}/appeal", headers=auth(worker)).status_code == 409

    client.post(f"/api/v1/disputes/{did}/statements", json={"content": "我方陈述如下。"},
                headers=auth(worker))
    client.post(f"/api/v1/disputes/{did}/verdict",
                json={"executor_share_bps": 3000, "reason": "交付部分达标"}, headers=auth(admin))

    # 平台处理决定结案：可申诉，端点放行
    d = client.get(f"/api/v1/disputes/{did}", headers=auth(worker)).json()
    assert d["appealable"] is True
    assert client.post(f"/api/v1/disputes/{did}/appeal", headers=auth(worker)).status_code == 200

    # 用掉后立刻转为不可申诉，端点同步拒绝
    d = client.get(f"/api/v1/disputes/{did}", headers=auth(worker)).json()
    assert d["appealable"] is False
    assert client.post(f"/api/v1/disputes/{did}/appeal", headers=auth(worker)).status_code == 409


def test_dspc030_expired_appeal_window_closes_the_flag_too(client, requester, worker):
    task, dispute = open_dispute(client, requester, worker)
    admin = make_admin(client)
    did = dispute["id"]
    client.post(f"/api/v1/disputes/{did}/statements", json={"content": "我方陈述如下。"},
                headers=auth(worker))
    client.post(f"/api/v1/disputes/{did}/verdict",
                json={"executor_share_bps": 3000, "reason": "交付部分达标"}, headers=auth(admin))

    db = SessionLocal()
    d = db.get(Dispute, did)
    d.resolved_at = utcnow() - timedelta(days=settings.APPEAL_WINDOW_DAYS + 1)
    db.add(d)
    db.commit()
    db.close()

    assert client.get(f"/api/v1/disputes/{did}", headers=auth(worker)).json()["appealable"] is False
    r = client.post(f"/api/v1/disputes/{did}/appeal", headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "appeal_window_closed"


# ---------- DSPC-040 机器闸门 ----------
def test_dspc040_every_party_facing_dispute_endpoint_is_reachable_from_the_sdk():
    """当事人侧端点必须在 SDK 里有对应调用。

    枚举来自 FastAPI 路由（不会抄漏），断言是**字面量子串**（不会误判）。
    我先试过用正则统计 `client.ts` 的覆盖率，三次跑出三个不同的数字——
    模板字符串、跨行泛型、查询串拼接都能骗过正则。
    一个会漏报的检查器去防漏报，是自欺，所以这里不做通用解析（DSPC-041）。
    """
    import inspect
    import os

    from app.core.deps import get_current_user
    from app.modules.dispute import router as dispute_router

    src = open(os.path.join(os.path.dirname(__file__), "..", CLIENT_TS)).read()

    required = []
    for route in dispute_router.router.routes:
        if "/jobs/" in route.path:
            continue                      # 调度端点由 cron 调，不需要 SDK
        defaults = [
            p.default.dependency
            for p in inspect.signature(route.endpoint).parameters.values()
            if hasattr(p.default, "dependency")
        ]
        if get_current_user in defaults:   # 管理员端点用 require_admin，不在此列
            required.append(route.path)
    assert required, "没有识别出任何当事人侧纠纷端点——断言本身失效了"

    # 把路由路径变成一条精确的正则：/disputes/{dispute_id}/statements
    #   → `/disputes/${任意标识符}/statements`
    # 不做通用 TS 解析，只做这一条精确匹配——匹配上了就是真的接了。
    def as_regex(path: str) -> str:
        parts = re.split(r"\{\w+\}", path)          # 路径参数位
        return "`" + r"\$\{\w+\}".join(re.escape(p) for p in parts) + "`"

    missing = sorted({
        path for path in required
        if not re.search(as_regex(path), src) and f"'{path}'" not in src
    })
    assert not missing, (
        f"这些当事人侧端点在 packages/core/src/client.ts 里没有对应调用：{missing}。"
        "服务端加了当事人能做的动作而客户端没接，等于这个动作不存在——"
        "V59 的人机验证门和 V61 的答辩都是这么丢的。"
    )


def test_dspc040_the_four_actions_that_were_missing_are_named_explicitly():
    """把 V61 修掉的那四条钉死，避免闸门被改松后无人察觉。"""
    import os

    src = open(os.path.join(os.path.dirname(__file__), "..", CLIENT_TS)).read()
    for literal in [
        "`/tasks/${taskId}/dispute`",
        "`/disputes/${disputeId}`",
        "`/disputes/${disputeId}/statements`",
        "`/disputes/${disputeId}/appeal`",
    ]:
        assert literal in src, f"SDK 缺少 {literal}"


# ---------- 非回归 ----------
def test_verdict_still_allowed_by_default_after_the_response_window(client, requester, worker):
    """答辩期过后仍可缺席裁决——原有行为不变。"""
    task, dispute = open_dispute(client, requester, worker)
    admin = make_admin(client)
    db = SessionLocal()
    d = db.get(Dispute, dispute["id"])
    d.created_at = utcnow() - timedelta(hours=settings.DISPUTE_RESPONSE_HOURS + 1)
    db.add(d)
    db.commit()
    db.close()
    r = client.post(f"/api/v1/disputes/{dispute['id']}/verdict",
                    json={"executor_share_bps": 5000, "reason": "被诉方逾期未答辩，依现有证据处理"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text
