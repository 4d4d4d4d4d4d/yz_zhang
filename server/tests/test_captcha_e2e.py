"""CAP-030~035 人机验证的端到端闭环（34 号 spec）。

**这是我上上批（V56）自己挖的坑。** 服务端加了人机验证阶梯：
`CaptchaProvider` 抽象、软阈值、事件留痕、错误验证码计入失败，还写了测试。

但是没有任何一个客户端能满足这道门：

    packages/core/src/client.ts:
      login(phone, password) { ... { phone, password } }   # 没有 captcha_token
    web/src/pages/Login.tsx:   没有任何验证码 UI

默认 `CAPTCHA_PROVIDER=none` 是直通实现，所以当前一切正常。
但 `docs/OPERATIONS.md` 明明白白建议「配 PLATFORM_CAPTCHA_PROVIDER 接第三方」——
**运维照做，全站登录立刻半死**：任何连续输错 3 次密码的用户都交不出令牌，
被锁在门外直到窗口过期，然后重复。

我建这道阶梯的理由是「给被误伤的真人一条自证的路」。
没有客户端支持时，它反而变成了一堵比封禁更早生效的墙。
"""
import pytest

from app.core import guard
from app.core.config import settings
from app.vendors import registry

from .conftest import register


def bad_login(client, phone="13900055555", token=""):
    return client.post("/api/v1/auth/login",
                       json={"phone": phone, "password": "wrong-password",
                             "captcha_token": token})


@pytest.fixture()
def enforcing_captcha(monkeypatch):
    """按运维文档的建议接上一个**会真的拦人**的验证码实现。"""
    monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "sandbox")
    monkeypatch.setattr(settings, "CAPTCHA_AFTER_FAILURES", 2)
    monkeypatch.setattr(settings, "CAPTCHA_SITE_KEY", "test-site-key")
    monkeypatch.setattr(settings, "AUTH_FAIL_BAN_THRESHOLD", 20)  # 别让封禁抢戏
    registry.reset()
    guard.reset()
    yield
    registry.reset()
    guard.reset()


# ---------- CAP-030 端到端：客户端真的能过这道门 ----------
def test_cap030_documented_client_flow_can_actually_get_through(client, enforcing_captcha):
    """按文档流程走一遍：提交 → 收到 captcha_required → 拉配置 → 带令牌重试。

    这是缺口的直接反面。改造前第三步无路可走——SDK 不发这个字段，
    网页上也没有能填的地方。
    """
    from app.vendors.captcha import SandboxCaptcha

    register(client, "13900055555", "真人")

    # 1) 先失败到软阈值
    for _ in range(settings.CAPTCHA_AFTER_FAILURES):
        assert bad_login(client).status_code == 400

    # 2) 服务端要求验证，并给出可执行的错误码
    blocked = bad_login(client)
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "captcha_required"

    # 3) 客户端据此拉配置（**无需登录**——登录页还没有 token）
    cfg = client.get("/api/v1/auth/captcha-config").json()
    assert cfg["enforcing"] is True
    assert cfg["site_key"] == "test-site-key"

    # 4) 带令牌重试 → 真的登进去了
    ok = client.post("/api/v1/auth/login",
                     json={"phone": "13900055555", "password": "pass123456",
                           "captcha_token": SandboxCaptcha.expected("testclient")})
    assert ok.status_code == 200, ok.text
    assert ok.json()["token"]


def test_cap032_config_endpoint_needs_no_login(client):
    """登录页还没有 token，这个端点必须公开。"""
    r = client.get("/api/v1/auth/captcha-config")
    assert r.status_code == 200
    assert set(r.json()) == {"provider", "enforcing", "site_key", "script_url"}


def test_cap033_config_does_not_leak_whether_this_ip_is_under_suspicion(
    client, enforcing_captcha,
):
    """配置端点**不能**变成风控状态的探测器。

    如果它告诉调用方「你现在需不需要验证」，任何人都能拿它来试探
    某个 IP 有没有触发风控。正确顺序是反应式：先提交，被拒了再渲染。
    """
    before = client.get("/api/v1/auth/captcha-config").json()
    for _ in range(settings.CAPTCHA_AFTER_FAILURES + 1):
        bad_login(client)
    after = client.get("/api/v1/auth/captcha-config").json()

    assert before == after, "触发风控前后配置端点的响应必须一模一样"
    assert "required" not in str(after)
    assert "failures" not in str(after)


# ---------- CAP-020/034 机器闸门 ----------
def test_cap034_production_refuses_enforcing_captcha_without_a_site_key(monkeypatch):
    """一个客户端渲染不出来的强制验证 = 把全站用户锁在门外。

    所以它必须是硬拦截，而不是一行只有开发者看得见的日志。
    """
    monkeypatch.setattr(settings, "ENV", "prod")
    monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "sandbox")
    monkeypatch.setattr(settings, "CAPTCHA_SITE_KEY", "")
    with pytest.raises(RuntimeError) as exc:
        registry.startup_check()
    assert "PLATFORM_CAPTCHA_SITE_KEY" in str(exc.value)
    assert "锁在门外" in str(exc.value)


def test_passthrough_captcha_does_not_need_a_site_key(monkeypatch):
    """直通实现不拦人，也就不需要客户端渲染任何东西——不该被这条闸门误伤。"""
    monkeypatch.setattr(settings, "ENV", "prod")
    monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "none")
    monkeypatch.setattr(settings, "CAPTCHA_SITE_KEY", "")
    try:
        registry.startup_check()
    except RuntimeError as exc:
        assert "CAPTCHA_SITE_KEY" not in str(exc)   # 别的项没配是另一回事


# ---------- CAP-035 默认配置不回归 ----------
def test_cap035_default_configuration_behaves_exactly_as_before(client):
    """默认 none 直通：登录流程与改造前完全一致。"""
    register(client, "13900056666", "普通用户")
    # 3 次而不是 5 次：登录端点本身有 5/60s 的账号维度限流（SEC-011），
    # 用满会撞上限流而不是验证码，测的就不是这里想测的东西了
    for _ in range(3):
        assert bad_login(client, "13900056666").status_code == 400   # 只是凭据错误

    ok = client.post("/api/v1/auth/login",
                     json={"phone": "13900056666", "password": "pass123456"})
    assert ok.status_code == 200, ok.text


def test_login_still_accepts_a_request_without_the_captcha_field(client):
    """老客户端不带这个字段也要能登录——加字段不能变成破坏性变更。"""
    register(client, "13900057777", "老客户端")
    r = client.post("/api/v1/auth/login",
                    json={"phone": "13900057777", "password": "pass123456"})
    assert r.status_code == 200, r.text
