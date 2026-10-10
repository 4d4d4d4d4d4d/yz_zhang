"""MOD-020~026 处置动作的单一实现（33 号 spec）。

**封禁一个用户，在这个系统里原本有两条路，做的事完全不一样。**

`/admin/users/{id}/ban` 做全套：算影响面、通知在途合约对手方、关闭待处理
报名并通知、走状态机下架挂单、记审计。

审核队列的 `/admin/reports/{id}/resolve` 只有两行：

    user.is_banned = True
    db.add(user)

上面五件事一件都没做——而**审核队列恰恰是审核员日常真正在用的那个界面**。

后果不是「少了点提示」：在途合约的对手方永远不会被告知他的钱还托管在一个
已被封禁、永远不会来验收的人那里。OPS-013 整节就是为了防止这件事。

本文件最核心的一条是 `test_mod023_*`：**两条路径的副作用必须逐项对等**。
"""
import pytest

from app.core.db import SessionLocal

from .conftest import auth, register, topup
from .test_task_flow import publish_task


@pytest.fixture()
def admin(client):
    from app.modules.account.models import User

    user = register(client, "13800080001", "审核员")
    with SessionLocal() as db:
        row = db.get(User, user["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return user


def notices_of(client, user):
    body = client.get("/api/v1/notifications", headers=auth(user)).json()
    return body["items"] if isinstance(body, dict) else body


def audit(client, admin, action=None):
    q = f"?action={action}" if action else ""
    return client.get(f"/api/v1/admin/audit-log{q}", headers=auth(admin)).json()


def report_on(client, reporter, target_type, target_id, reason="违规内容"):
    r = client.post("/api/v1/reports",
                    json={"target_type": target_type, "target_id": target_id,
                          "reason": reason}, headers=auth(reporter))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def resolve(client, admin, report_id, action):
    r = client.post(f"/api/v1/admin/reports/{report_id}/resolve",
                    json={"action": action}, headers=auth(admin))
    assert r.status_code == 200, r.text
    return r.json()


def in_flight_setup(client, requester, worker):
    """造一个「托管中 + 有挂单 + 有待处理报名」的发布者，用于封禁影响面。"""
    from .test_task_flow import match_and_fund

    topup(client, requester, 200000)
    funded_task = publish_task(client, requester, budget_cents=50000)
    match_and_fund(client, requester, worker, funded_task)   # 托管中，对手方=worker

    open_task = publish_task(client, requester, budget_cents=30000)
    r = client.post(f"/api/v1/tasks/{open_task['id']}/applications",
                    json={"message": "我来做"}, headers=auth(worker))
    assert r.status_code == 201, r.text
    return funded_task, open_task


# ---------- MOD-020~022 审核队列封禁必须做全套 ----------
def test_mod020_ban_from_report_queue_notifies_the_counterparty(
    client, requester, worker, admin,
):
    """缺口的直接反面：对手方的钱还托管在一个被封的人那里，他必须被告知。"""
    funded_task, _ = in_flight_setup(client, requester, worker)

    rid = report_on(client, worker, "user", requester["id"], "疑似诈骗")
    result = resolve(client, admin, rid, "ban_user")
    assert result["effect"]["is_banned"] is True

    titles = [n["title"] for n in notices_of(client, worker)]
    assert "对方账号已被封禁" in titles, \
        "改造前这条通知不会发出——对手方的托管资金就这么被无限期困住"
    assert funded_task["id"]


def test_mod021_ban_from_report_queue_closes_pending_applications(
    client, requester, worker, admin,
):
    _, open_task = in_flight_setup(client, requester, worker)

    rid = report_on(client, worker, "user", requester["id"])
    resolve(client, admin, rid, "ban_user")

    from app.modules.task.models import Application

    with SessionLocal() as db:
        pending = db.query(Application).filter(
            Application.task_id == open_task["id"],
            Application.status == "pending").all()
        assert pending == [], "报名者不该继续等一个永远没人来选他的任务"
    titles = [n["title"] for n in notices_of(client, worker)]
    assert "报名的任务已下架" in titles


def test_mod022_ban_from_report_queue_takes_down_listings_via_the_state_machine(
    client, requester, worker, admin,
):
    _, open_task = in_flight_setup(client, requester, worker)

    rid = report_on(client, worker, "user", requester["id"])
    resolve(client, admin, rid, "ban_user")

    from app.core.events import OutboxEvent
    from app.modules.task.models import Task

    with SessionLocal() as db:
        assert db.get(Task, open_task["id"]).status == "cancelled"
        # 走了状态机才会有事件；直接赋值不会。下一个给 task.cancelled
        # 加订阅者的人（比如托管退款）就靠这个事件
        assert db.query(OutboxEvent).filter(
            OutboxEvent.event == "task.cancelled").count() >= 1


# ---------- MOD-023 两条路径逐项对等（核心用例） ----------
def test_mod023_both_ban_paths_have_identical_side_effects(client, worker, admin):
    """同样的封禁，从审核队列进和从用户页进，副作用必须一模一样。

    「哪条路进来的」不该改变用户拿不拿得到通知。
    """
    from app.modules.task.models import Application, Task

    def setup_victim(phone, nickname):
        from .conftest import verify_user

        victim = register(client, phone, nickname)
        verify_user(client, victim, nickname)
        topup(client, victim, 100000)
        task = publish_task(client, victim, budget_cents=30000)
        client.post(f"/api/v1/tasks/{task['id']}/applications",
                    json={"message": "报名"}, headers=auth(worker))
        return victim, task

    def snapshot(victim, task):
        with SessionLocal() as db:
            from app.modules.account.models import User

            return {
                "banned": db.get(User, victim["id"]).is_banned,
                "task_status": db.get(Task, task["id"]).status,
                "pending_applications": db.query(Application).filter(
                    Application.task_id == task["id"],
                    Application.status == "pending").count(),
            }

    # 路径一：审核队列
    v1, t1 = setup_victim("13900030001", "受害者一")
    rid = report_on(client, worker, "user", v1["id"])
    resolve(client, admin, rid, "ban_user")
    via_queue = snapshot(v1, t1)

    # 路径二：用户页直接封禁
    v2, t2 = setup_victim("13900030002", "受害者二")
    r = client.post(f"/api/v1/admin/users/{v2['id']}/ban", headers=auth(admin))
    assert r.status_code == 200, r.text
    via_user_page = snapshot(v2, t2)

    assert via_queue == via_user_page, \
        f"两条封禁路径副作用不一致：队列={via_queue} 用户页={via_user_page}"

    # 审计也必须都有
    entries = audit(client, admin, "ban_user")
    assert len(entries) >= 2, "两条路径都必须留下 ban_user 审计"


# ---------- MOD-024 下架任务要告诉受影响的人 ----------
def test_mod024_task_takedown_notifies_creator_and_applicants(
    client, requester, worker, admin,
):
    """任务无声消失，用户既不知情也无从申诉。"""
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    client.post(f"/api/v1/tasks/{task['id']}/applications",
                json={"message": "报名"}, headers=auth(worker))

    rid = report_on(client, worker, "task", task["id"], "标题涉嫌欺诈")
    result = resolve(client, admin, rid, "remove_content")
    assert result["effect"]["removed"] is True

    creator_titles = [n["title"] for n in notices_of(client, requester)]
    assert "任务已被下架" in creator_titles
    # 通知里要带原因，否则用户无从申诉
    body = next(n for n in notices_of(client, requester) if n["title"] == "任务已被下架")
    assert "举报处置" in body["body"] or "违规" in body["body"]
    assert "报名的任务已下架" in [n["title"] for n in notices_of(client, worker)]


def test_takedown_refuses_tasks_that_already_have_escrow(
    client, requester, worker, admin,
):
    """已成交的任务牵涉托管资金，不能被审核动作单方作废——要走纠纷流程。"""
    from .test_task_flow import match_and_fund

    topup(client, requester, 200000)
    task = publish_task(client, requester, budget_cents=50000)
    match_and_fund(client, requester, worker, task)

    rid = report_on(client, worker, "task", task["id"])
    result = resolve(client, admin, rid, "remove_content")
    assert result["effect"]["removed"] is False
    assert "纠纷" in result["effect"]["note"]


def test_content_takedown_notifies_the_author(client, requester, worker, admin):
    r = client.post("/api/v1/contents",
                    json={"kind": "post", "title": "", "body": "一条动态" * 3},
                    headers=auth(requester))
    assert r.status_code == 201, r.text
    content_id = r.json()["id"]

    rid = report_on(client, worker, "content", content_id, "垃圾广告")
    resolve(client, admin, rid, "remove_content")
    assert "内容已被下架" in [n["title"] for n in notices_of(client, requester)]


# ---------- MOD-025 每一次处置都记审计（含驳回） ----------
def test_mod025_every_resolution_including_dismiss_is_audited(
    client, requester, worker, admin,
):
    """驳回同样是决定：谁在什么时候驳回了哪条举报，是事后复盘的关键。

    只写 `report.handled_by` 不够——审计日志按动作查询时看不到它。
    """
    task = publish_task(client, requester, budget_cents=10000)
    rid = report_on(client, worker, "task", task["id"], "我觉得不妥")
    resolve(client, admin, rid, "dismiss")

    entries = audit(client, admin, "report_dismiss")
    assert entries, "驳回也必须能在审计日志里按动作查到"
    assert str(rid) in entries[0]["detail"]


def test_takedown_and_ban_actions_are_individually_queryable(
    client, requester, worker, admin,
):
    task = publish_task(client, requester, budget_cents=10000)
    rid = report_on(client, worker, "task", task["id"])
    resolve(client, admin, rid, "remove_content")

    assert audit(client, admin, "report_remove_content"), "处置动作本身可查"
    assert audit(client, admin, "takedown_task"), "具体副作用也留痕"


# ---------- MOD-026 状态机的「唯一入口」不再只是约定 ----------
def test_mod026_nothing_bypasses_the_state_machine():
    """全仓库扫描：`task.status = ` 只允许出现在 `transition()` 内部。

    状态机的「唯一合法变更入口」原本只靠注释和自觉维持——而约定不会报错。
    上一版就有一处绕过（审核下架任务时直接赋值），今天只是少派发一个事件，
    但下一个给 `task.cancelled` 加订阅者的人会发现它在那条路径上根本不触发。
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        # 用 AST 而不是正则扫文本：正则会把**讲这件事的注释和文档字符串**
        # 也当成违规（第一版就误报了自己的说明文字），而 AST 只看真正的赋值
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (isinstance(target, ast.Attribute) and target.attr == "status"
                        and isinstance(target.value, ast.Name)
                        and "task" in target.value.id.lower()):
                    rel = path.relative_to(root)
                    if str(rel) == "modules/task/service.py":
                        continue      # transition() 是唯一合法处
                    offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, "绕过 transition() 直接改任务状态：\n" + "\n".join(offenders)
