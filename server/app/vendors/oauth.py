"""ACC-003 第三方登录（微信 / Apple / Google）。

原始 spec 的备注写着：「**App 端 Apple 登录为上架合规必需**」——
App Store 审核要求：只要你提供了任何第三方登录，就必须同时提供 Sign in with
Apple。所以这一条不是「体验加分项」，是**上架的前置条件**。

三家的服务端流程同形：客户端拿到一个 code/identity_token，服务端拿它去换
一个**稳定的第三方用户标识**（subject）。差异在端点与字段名，
所以抽象成一个 `verify()`。
"""
import json
import urllib.request
from typing import Protocol

from .base import VendorError, VendorResult

#: 与 spec 对齐的三家。新增一家只要在这里加名字并实现 verify。
SUPPORTED = ("wechat", "apple", "google")


class OAuthProvider(Protocol):
    name: str
    #: 真的会去第三方校验（而不是信客户端说的）
    verifies: bool

    def verify(self, provider: str, credential: str) -> VendorResult:
        """返回 {"subject": 稳定唯一标识, "nickname": 可选昵称}。"""


class MockOAuth:
    """开发/CI：把凭据本身当 subject。

    **绝不可上生产**——它等于「客户端说自己是谁就是谁」，
    任何人都能冒充任意账号。生产自检把 oauth 与其它 P0 能力一视同仁。
    """

    name = "mock"
    verifies = False

    def verify(self, provider: str, credential: str) -> VendorResult:
        if provider not in SUPPORTED:
            raise VendorError("unsupported_provider", f"不支持的登录方式：{provider}",
                              retryable=False)
        if len(credential) < 6:
            raise VendorError("bad_credential", "凭据无效", retryable=False)
        return VendorResult(ok=True, external_ref=credential, status="succeeded",
                            data={"subject": f"{provider}:{credential}",
                                  "nickname": "", "verified": False})


class HttpOAuth:
    """真实形态：把凭据 POST 给一个校验端点，换回 subject。

    微信 `code2Session`、Apple 的 `/auth/token` + id_token 校验、
    Google 的 `tokeninfo` 形状不同，但都是「拿凭据换 subject」。
    接入时在这里按 provider 分支映射字段即可，业务侧不动。
    """

    name = "http"
    verifies = True

    def __init__(self) -> None:
        from app.core.config import settings

        self.endpoint = settings.OAUTH_ENDPOINT
        self.token = settings.OAUTH_TOKEN

    def verify(self, provider: str, credential: str) -> VendorResult:
        if provider not in SUPPORTED:
            raise VendorError("unsupported_provider", f"不支持的登录方式：{provider}",
                              retryable=False)
        if not self.endpoint:
            raise VendorError("oauth_not_configured",
                              "PLATFORM_OAUTH_PROVIDER=http 但没有配 PLATFORM_OAUTH_ENDPOINT",
                              retryable=False)
        payload = json.dumps({"provider": provider, "credential": credential}).encode()
        req = urllib.request.Request(self.endpoint, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                out = json.loads(resp.read())
        except Exception as exc:
            raise VendorError("oauth_upstream", f"第三方登录校验失败：{exc}",
                              retryable=True) from exc
        subject = out.get("subject")
        if not subject:
            # 换不到 subject 就**必须失败**，不能退化成「相信客户端」
            raise VendorError("oauth_no_subject", "第三方未返回用户标识", retryable=False)
        return VendorResult(ok=True, external_ref=str(subject), status="succeeded",
                            data={"subject": f"{provider}:{subject}",
                                  "nickname": out.get("nickname", ""), "verified": True})
