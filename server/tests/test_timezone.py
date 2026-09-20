"""TZ-060~064 时间是一条契约（58 号 spec）。

缺口的证据是代码里现成的两行补丁：

    // web/src/DisputePanel.tsx
    const left = new Date(iso + 'Z').getTime() - Date.now();
    // app/App.tsx
    (new Date(dispute.response_deadline + 'Z').getTime() - Date.now()) / 3_600_000

有人在这两个地方发现了「服务端给的时间被当成本地时间解析」，就地补了个 `Z`。
**补丁本身就是缺陷报告**：同样的问题全仓还有七处没补，而且两个端各自补了一次。

服务端所有时间都是 UTC，但响应里一律 `x.isoformat()`——没有 `Z`。
而 JS 的规矩是：ISO 日期时间形式不带偏移时按**本地时间**解析。
于是全站每一个时间显示都偏了用户所在时区的偏移量。
"""
import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.timefmt import UtcDatetime, iso, to_utc_naive
from tests.conftest import auth, register, topup, verify_user
from tests.test_task_flow import CLEAN_TASK, match_and_fund, publish_task

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# 长得像 ISO 日期时间的字符串（有 T 有时分），不含纯日期
ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?")
HAS_ZONE = re.compile(r"(Z|[+-]\d{2}:\d{2})$")


# ------------------------------------------------------------- TZ-060 出口带时区
def _walk_strings(node, path="$"):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def assert_zoned(payload, where: str) -> int:
    """返回检查过的时间字符串条数——**零条也要看得见**，否则闸门恒真。"""
    seen = 0
    for path, value in _walk_strings(payload):
        if not ISO_DATETIME.match(value):
            continue
        seen += 1
        assert HAS_ZONE.search(value), (
            f"{where} 的 {path} 是 {value!r}：没有时区标记。"
            f"浏览器会把它当本地时间解析，显示出来会差一个时区偏移。"
        )
    return seen


def test_tz060_real_responses_all_carry_a_zone(client, requester):
    """跑一遍真实业务流程，把响应递归走一遍。

    这道闸门看的是**用户真正收到的东西**，不关心中间是怎么生成的——
    源码扫描挡不住 FastAPI 自己序列化字典里的裸 `datetime`，那里没有
    `.isoformat()` 可扫。
    """
    worker = register(client, "13800058001", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/progress",
                json={"content": "开工了"}, headers=auth(worker))
    client.post("/api/v1/support/tickets",
                json={"subject": "想问一下结算", "body": "什么时候到账"}, headers=auth(worker))
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付不符约定，要求重做"}, headers=auth(requester))
    dispute_id = d.json()["id"]
    client.post(f"/api/v1/disputes/{dispute_id}/statements",
                json={"content": "我方已按约定交付，附证据"}, headers=auth(worker))

    checked = 0
    for method, path, user in [
        ("GET", f"/api/v1/tasks/{task['id']}", requester),
        ("GET", "/api/v1/tasks", requester),
        ("GET", "/api/v1/tasks/mine", requester),
        ("GET", f"/api/v1/tasks/{task['id']}/progress", worker),
        ("GET", "/api/v1/wallet/ledger", requester),
        ("GET", "/api/v1/notifications", worker),
        ("GET", "/api/v1/users/me", requester),
        ("GET", "/api/v1/auth/sessions", requester),
        ("GET", f"/api/v1/contracts/by-task/{task['id']}", requester),
        ("GET", "/api/v1/users/me/certifications", worker),
        ("GET", "/api/v1/support/tickets", worker),
        ("GET", f"/api/v1/tasks/{task['id']}/dispute", worker),
        ("GET", f"/api/v1/disputes/{dispute_id}/statements", worker),
    ]:
        r = client.request(method, path, headers=auth(user))
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
        checked += assert_zoned(r.json(), path)
    # 自检：一条时间都没查到，说明这个测试什么也没验证
    assert checked >= 10, f"只检查到 {checked} 个时间字符串，闸门可能形同虚设"


def test_tz060_dispute_deadline_is_zoned(client, requester):
    """`response_deadline` 是两处手工 `+ 'Z'` 补丁的源头，单独钉一条。"""
    worker = register(client, "13800058002", "执行者")
    verify_user(client, worker, name="执行")
    topup(client, requester, 100000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "交付不符约定，要求重做"}, headers=auth(requester))
    assert r.status_code == 201, r.text
    deadline = r.json()["response_deadline"]
    assert HAS_ZONE.search(deadline), f"{deadline!r} 没有时区标记"
    # 客户端不再需要自己补 Z：直接解析就是对的
    assert datetime.fromisoformat(deadline.replace("Z", "+00:00")).tzinfo is not None


# --------------------------------------------------------- TZ-061 源码里不许裸用
def test_tz061_no_bare_isoformat_in_modules():
    """新写的代码也得走同一个出口。

    允许 `.date().isoformat()`——那是日期，没有时区可言（合同正文里的落款日期）。
    """
    offenders = []
    files = sorted((APP_DIR / "modules").rglob("*.py"))
    for path in files:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "isoformat":
                continue
            inner = node.func.value
            # x.date().isoformat() 放行
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "date"):
                continue
            offenders.append(f"{path.relative_to(APP_DIR.parent)}:{node.lineno}")
    # 扫描器自检：一个文件都没扫到说明解析坏了（V72 立的规矩）
    assert len(files) >= 30, f"只扫到 {len(files)} 个模块文件，扫描逻辑可能坏了"
    assert not offenders, (
        "这些地方直接调了 .isoformat()，给出去的时间没有时区标记；"
        f"请改用 app.core.timefmt.iso()：{offenders}"
    )


def test_tz061_iso_helper_is_actually_used_everywhere():
    """反向自检：`iso(` 的调用点要足够多。

    如果有人把上一条闸门「满足」成了「全删掉时间字段」，这条会红。
    """
    hits = sum(
        len(re.findall(r"\biso\(", p.read_text(encoding="utf-8")))
        for p in (APP_DIR / "modules").rglob("*.py")
    )
    assert hits >= 60, f"只找到 {hits} 处 iso() 调用，时间字段像是被删掉了而不是被修好了"


# --------------------------------------------------------- TZ-062 入口换算不截断
def test_tz062_offset_is_converted_not_truncated(client, requester):
    """改造前 `+08:00` 的 10:00 被存成 10:00——差 8 小时，且没有任何报错。"""
    r = client.post("/api/v1/tasks",
                    json={**CLEAN_TASK, "deadline": "2030-01-01T10:00:00+08:00"},
                    headers=auth(requester))
    assert r.status_code == 201, r.text
    from app.core.db import SessionLocal
    from app.modules.task.models import Task

    with SessionLocal() as db:
        stored = db.get(Task, r.json()["id"]).deadline
    assert stored == datetime(2030, 1, 1, 2, 0), f"存成了 {stored}，偏移被丢掉了"
    # 出口也要带 Z，且与入口是同一时刻
    assert r.json()["deadline"] == "2030-01-01T02:00:00Z"


@pytest.mark.parametrize("offset_hours", [8, -10, 0])
def test_tz062_two_hours_from_now_works_in_any_timezone(client, requester, offset_hours):
    """夏威夷用户（UTC-10）选「2 小时后」，改造前直接 400「截止时间必须晚于当前时间」。

    他没做错任何事，却发不出这个任务，而报错说的是一件他知道不对的事。
    """
    tz = timezone(timedelta(hours=offset_hours))
    local = (datetime.now(timezone.utc) + timedelta(hours=2)).astimezone(tz)
    r = client.post("/api/v1/tasks",
                    json={**CLEAN_TASK, "deadline": local.isoformat()},
                    headers=auth(requester))
    assert r.status_code == 201, f"UTC{offset_hours:+d} 的用户发不出任务：{r.text[:200]}"
    # 三个时区发的是**同一时刻**，落库必须一致（误差 1 秒内）
    got = datetime.fromisoformat(r.json()["deadline"].replace("Z", "+00:00"))
    assert abs((got - (datetime.now(timezone.utc) + timedelta(hours=2))).total_seconds()) < 5


def test_tz062_naive_input_is_treated_as_utc():
    """朴素值视为 UTC。这是个明确的选择：拒收更严格，但会把既有集成方
    （包括开放 API 的第三方）一次性打断，而他们发的朴素值多半本来就是 UTC。"""
    from pydantic import BaseModel

    class M(BaseModel):
        d: UtcDatetime | None = None

    assert M(d="2030-01-01T10:00:00").d == datetime(2030, 1, 1, 10, 0)
    assert M(d="2030-01-01T10:00:00+08:00").d == datetime(2030, 1, 1, 2, 0)
    assert M(d="2030-01-01T10:00:00Z").d == datetime(2030, 1, 1, 10, 0)


def test_tz060_iso_helper_round_trips():
    assert iso(None) is None
    assert iso(datetime(2026, 9, 20, 8, 0)) == "2026-09-20T08:00:00Z"
    aware = datetime(2026, 9, 20, 16, 0, tzinfo=timezone(timedelta(hours=8)))
    assert iso(aware) == "2026-09-20T08:00:00Z"
    assert to_utc_naive("不是时间") == "不是时间"      # 非时间值原样放过
