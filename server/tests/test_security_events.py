"""SECEV-030~037 安全事件落库、跨副本封禁与人机验证（31 号 spec）。

这批修的是**一句说谎的注释**。`app/core/guard.py` 原本写着：

    # 封禁本身落 DB（SecurityEvent），因此跨副本仍能看到。
    _banned_until: dict[str, float] = {}

那个表根本不存在，封禁就是一个进程内 dict。三副本下：攻击者换个连接打到
别的副本照样过；有效阈值被放大三倍；管理员解封只解了一个副本，被误封的
公司出口 IP 之后还有 2/3 概率被拒——**时好时坏的故障比稳定的故障难查一个
数量级**。

注释比代码更容易骗人，因为没有测试盯着它。所以这里的核心用例
`test_secev030_*` 就是专门盯这一条：**清掉进程内状态后，封禁仍然生效**。
"""
import pytest

from app.core import guard
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models_security import SecurityEvent

from .conftest import auth, register


@pytest.fixture()
def admin(client):
    from app.modules.account.models import User

    user = register(client, "13800060001", "安全管理员")
    with SessionLocal() as db:
        row = db.get(User, user["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    return user


def bad_login(client, phone="13900099999", password="wrong-password", token=""):
    return client.post("/api/v1/auth/login",
                       json={"phone": phone, "password": password,
                             "captcha_token": token})


def simulate_other_replica():
    """模拟「请求打到了另一个副本」：那个进程的内存里什么都没有。

    这正是改造前失效的场景——封禁只活在处理上一次请求的那个进程里。
    """
    guard.reset()


def events(kind=None, ip=None):
    with SessionLocal() as db:
        q = db.query(SecurityEvent)
        if kind:
            q = q.filter(SecurityEvent.kind == kind)
        if ip:
            q = q.filter(SecurityEvent.ip == ip)
        return q.all()


@pytest.fixture()
def low_threshold(monkeypatch):
    """把阈值调低，避免用几十次真实请求撑出一个封禁。"""
    monkeypatch.setattr(settings, "AUTH_FAIL_BAN_THRESHOLD", 3)
    monkeypatch.setattr(settings, "CAPTCHA_AFTER_FAILURES", 0)   # 本组不测验证码
    guard.reset()
    yield
    guard.reset()


# ---------- SECEV-030 换个进程仍然被封（洞的直接反面） ----------
def test_secev030_ban_survives_a_process_restart(client, low_threshold):
    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD):
        bad_login(client)
    assert bad_login(client).status_code == 403      # 已封

    simulate_other_replica()
    r = bad_login(client)
    assert r.status_code == 403, "改造前这里会放行——封禁只活在上一个进程的内存里"
    assert r.json()["detail"]["code"] == "temporarily_banned"


def test_secev032_failures_accumulate_across_replicas(client, low_threshold):
    """失败计数也必须共享，否则 N 个副本把有效阈值放大了 N 倍。"""
    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD - 1):
        bad_login(client)
        simulate_other_replica()          # 每一次都「换个副本」
    assert guard.ban_remaining("testclient") == 0     # 还没到阈值

    bad_login(client)                     # 最后一次，跨副本累计达标
    simulate_other_replica()
    assert guard.ban_remaining("testclient") > 0, \
        "分散在不同副本的失败必须合并计算"


def test_secev031_unban_takes_effect_globally(client, admin, low_threshold):
    """解封一次全局生效。

    改造前解封只作用于当前副本：被误封的公司出口 IP 之后还有 (N-1)/N 概率
    被拒，用户报「有时候能登录有时候不能」，客服根本复现不出来。
    """
    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD):
        bad_login(client)
    assert bad_login(client).status_code == 403

    r = client.post("/api/v1/admin/security/unban", json={"ip": "testclient"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text

    simulate_other_replica()
    assert guard.ban_remaining("testclient") == 0
    # 解封留痕：删掉记录就没法回答「这个 IP 什么时候被封过、谁解的」
    assert events("unban", "testclient")
    assert events("ban", "testclient"), "封禁记录本身保留"


def test_the_unban_endpoint_is_not_blocked_by_the_ban_itself(client, admin, low_threshold):
    """**补救入口不能被它要补救的东西挡住。**

    实现时被自己的测试逮到的一个真实缺陷：解封接口也走全局写限流中间件，
    而中间件按 IP 拒绝被封的来源。误封整个公司出口 IP 时，管理员很可能
    就坐在那个 IP 后面——补救路径恰好在最需要它的时候不可用。
    """
    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD):
        bad_login(client)
    # 普通写操作确实被封住了（前置条件：封禁真的生效）
    assert bad_login(client).status_code == 403

    # 但解封入口必须可达——它仍然要求管理员身份，不是一扇敞开的门
    r = client.post("/api/v1/admin/security/unban", json={"ip": "testclient"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text


def test_secev035_successful_login_clears_the_failure_counter(client, low_threshold):
    """偶发手滑不该累积成封禁。"""
    user = register(client, "13900088888", "手滑用户")
    assert user
    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD - 1):
        bad_login(client, phone="13900088888")
    assert guard.recent_failures("testclient") > 0

    ok = client.post("/api/v1/auth/login",
                     json={"phone": "13900088888", "password": "pass123456"})
    assert ok.status_code == 200, ok.text
    assert guard.recent_failures("testclient") == 0


# ---------- SECEV-004 写入量有界 ----------
def test_secev036_failure_records_per_window_are_bounded_by_the_threshold(
    client, low_threshold,
):
    """封禁检查在计数**之前**，所以被封的 IP 不会再产生新的失败记录。

    这不是巧合，是把顺序排对了才有的性质：否则攻击者可以靠刷失败把表撑爆。
    """
    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD * 5):
        bad_login(client)

    rows = events("auth_failure", "testclient")
    assert len(rows) <= settings.AUTH_FAIL_BAN_THRESHOLD, \
        f"单窗口内写入 {len(rows)} 条，超过阈值说明被封后仍在计数"


# ---------- SECEV-033/034 人机验证 ----------
@pytest.fixture()
def sandbox_captcha(monkeypatch):
    from app.vendors import registry

    monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "sandbox")
    monkeypatch.setattr(settings, "CAPTCHA_AFTER_FAILURES", 2)
    monkeypatch.setattr(settings, "AUTH_FAIL_BAN_THRESHOLD", 20)  # 别让封禁抢戏
    registry.reset()
    guard.reset()
    yield
    registry.reset()
    guard.reset()


def test_secev033_captcha_is_required_after_the_soft_threshold(client, sandbox_captcha):
    from app.vendors.captcha import SandboxCaptcha

    for _ in range(settings.CAPTCHA_AFTER_FAILURES):
        assert bad_login(client).status_code == 400     # 普通的凭据错误

    # 到软阈值：没有验证码令牌就被拦下，且给的是可执行的错误码
    blocked = bad_login(client)
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "captcha_required"

    # 带正确令牌可以继续（继续之后仍然是密码错误，但**不是**验证码拦截）
    good = bad_login(client, token=SandboxCaptcha.expected("testclient"))
    assert good.status_code == 400
    assert good.json()["detail"]["code"] == "bad_credentials"


def test_secev011_captcha_gives_a_real_person_a_way_out_instead_of_a_ban(
    client, sandbox_captcha,
):
    """验证码是给被误伤的人一条自证的路，不是多加一道墙。

    没有它时风控的唯一升级手段是封禁——手滑输错几次的真人和撞库脚本
    得到的处置完全一样。有了它：真人过一下验证就能继续登录。
    """
    from app.vendors.captcha import SandboxCaptcha

    register(client, "13900077777", "真人")
    for _ in range(settings.CAPTCHA_AFTER_FAILURES):
        bad_login(client, phone="13900077777")

    # 密码想起来了，但已经到软阈值——带上验证码照样能登进去，没有被封
    ok = client.post("/api/v1/auth/login",
                     json={"phone": "13900077777", "password": "pass123456",
                           "captcha_token": SandboxCaptcha.expected("testclient")})
    assert ok.status_code == 200, ok.text
    assert guard.ban_remaining("testclient") == 0


def test_secev013_wrong_captcha_counts_as_a_failure(client, sandbox_captcha):
    """否则可以用无限次错误验证码把真正的登录尝试藏在噪音里。"""
    for _ in range(settings.CAPTCHA_AFTER_FAILURES):
        bad_login(client)
    before = guard.recent_failures("testclient")

    assert bad_login(client, token="wrong-token").status_code == 403
    assert guard.recent_failures("testclient") > before
    assert events("captcha_failed", "testclient")


def test_secev034_passthrough_provider_still_records_the_event(client, monkeypatch):
    """直通实现下也要留痕，否则没接真实供应商时风控趋势完全看不见。"""
    from app.vendors import registry

    monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "none")
    monkeypatch.setattr(settings, "CAPTCHA_AFTER_FAILURES", 2)
    monkeypatch.setattr(settings, "AUTH_FAIL_BAN_THRESHOLD", 20)
    registry.reset()
    guard.reset()

    for _ in range(settings.CAPTCHA_AFTER_FAILURES + 1):
        bad_login(client)

    assert events("captcha_required", "testclient"), "直通也必须记录触发"
    assert events("captcha_passed", "testclient"), "直通的结果是通过，同样记录"
    registry.reset()


def test_no_captcha_is_honestly_named_as_not_enforcing():
    """叫 Default/Simple 会让人以为「至少有点用」，而它的作用是零。"""
    from app.vendors.captcha import NoCaptcha, SandboxCaptcha

    assert NoCaptcha.name == "none"
    assert NoCaptcha.enforcing is False
    assert SandboxCaptcha.enforcing is True
    # 沙箱实现必须**真的会拒**——只返回 True 的桩换供应商那天才第一次执行到
    # 失败分支，而那正是最不能出错的时刻
    assert SandboxCaptcha().verify("nonsense", "1.2.3.4") is False
    assert SandboxCaptcha().verify(SandboxCaptcha.expected("1.2.3.4"), "1.2.3.4") is True


def test_captcha_provider_appears_in_the_vendor_panel(client, admin):
    """SEC-021 此前文档写着「抽象位已留」——并没有留。现在面板里能看到它。"""
    body = client.get("/api/v1/admin/vendors", headers=auth(admin)).json()
    kinds = {row["kind"]: row for row in body["vendors"]}
    assert "captcha" in kinds, "人机验证要在供应商面板里如实标注，别再只写在文档里"
    assert kinds["captcha"]["grade"] in ("mock", "sandbox", "production")


# ---------- SECEV-020/037 看板 ----------
def test_secev020_board_reads_shared_state(client, admin, low_threshold):
    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD):
        bad_login(client)
    simulate_other_replica()      # 看板所在的「副本」没有任何本地状态

    board = client.get("/api/v1/admin/security", headers=auth(admin)).json()
    assert any(b["ip"] == "testclient" for b in board["banned"])
    assert board["banned"][0]["reason"], "封禁要说清是因为什么"
    assert board["threshold"] == settings.AUTH_FAIL_BAN_THRESHOLD
    assert "captcha_after" in board


def test_secev037_board_requires_admin(client, requester):
    assert client.get("/api/v1/admin/security",
                      headers=auth(requester)).status_code == 403
    assert client.post("/api/v1/admin/security/unban", json={"ip": "1.2.3.4"},
                       headers=auth(requester)).status_code == 403


# ---------- SECEV-006 保留期 ----------
def test_secev006_purge_keeps_disposition_records(client, low_threshold):
    """清理高频噪音，但封禁与解封是运营处置留痕，保留期到了也不清。"""
    from datetime import timedelta

    from app.modules.account.models import utcnow

    for _ in range(settings.AUTH_FAIL_BAN_THRESHOLD):
        bad_login(client)
    assert events("ban", "testclient")

    old = utcnow() - timedelta(days=90)
    with SessionLocal() as db:
        db.query(SecurityEvent).update({"created_at": old}, synchronize_session=False)
        db.commit()

    from .conftest import JOB_HEADERS

    r = client.post("/api/v1/events/jobs/purge-security", headers=JOB_HEADERS)
    assert r.status_code == 200, r.text
    assert events("ban", "testclient"), "封禁处置记录不该被保留期清掉"
    assert events("auth_failure", "testclient") == []


def test_purge_security_requires_job_token(client):
    assert client.post("/api/v1/events/jobs/purge-security").status_code == 403
