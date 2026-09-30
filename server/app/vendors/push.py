"""NTF-002 / IM-008 推送通道。

改造前通知只有站内信：`notification/service.py` 第一行就写着
「生产追加 APNs/FCM/短信通道」，但那句话从 MVP 写到现在都没有兑现。

后果不是「体验差一点」。这套系统里有**错过就无法挽回**的通知：
被诉方的答辩期是 48 小时，逾期即缺席裁决（DSPR-020）。
用户不主动打开 App，站内信就等于没发——**一个只存在于站内的答辩提醒，
和没有提醒差别不大**，而这恰恰是 V63 那一批想解决的问题的另一半。

三态与其它供应商一致：none（不发，仅记账）/ sandbox（形态真实的桩）/
真实通道（APNs / FCM / 极光 / 个推，走同一个 HTTP 形态）。
"""
import json
import urllib.request
from typing import Protocol

from .base import VendorError, VendorResult


class PushProvider(Protocol):
    name: str
    #: 真的会把消息推到设备上（而不是只记一笔）
    delivers: bool

    def send(self, tokens: list[str], title: str, body: str,
             data: dict | None = None) -> VendorResult:
        """向一批设备令牌推送。返回成功/失效令牌，失效的由调用方清理。"""


class NoPush:
    """缺省：不发任何东西，只如实返回「没有通道」。

    **不假装成功**——返回 `delivered=0` 且列出未送达的令牌，
    这样 `/admin/vendors` 面板与验收脚本都能看见「推送其实没接」。
    """

    name = "none"
    delivers = False

    def send(self, tokens, title, body, data=None) -> VendorResult:
        return VendorResult(ok=True, external_ref="", status="succeeded",
                            data={"delivered": 0, "skipped": len(tokens),
                                  "reason": "no_push_provider"})


class SandboxPush:
    """形态真实的桩：按平台分组、逐个令牌返回结果、模拟失效令牌。

    真实通道对「令牌失效」的处理是运维上最容易忽略的一环——
    设备卸载后令牌会永久失效，不清理就会年复一年地推给不存在的设备。
    所以桩实现刻意把失效令牌这条路径造出来（以 `expired-` 开头的令牌）。
    """

    name = "sandbox"
    delivers = True

    def send(self, tokens, title, body, data=None) -> VendorResult:
        invalid = [t for t in tokens if t.startswith("expired-")]
        ok = [t for t in tokens if t not in invalid]
        return VendorResult(ok=True, external_ref=f"sbx-push-{len(ok)}", status="succeeded",
                            data={"delivered": len(ok), "invalid_tokens": invalid})


class HttpPushProvider:
    """真实通道的通用形态：把消息 POST 给一个网关端点。

    APNs / FCM / 极光 / 个推 的服务端接口形状都是「带鉴权头 POST 一个 JSON」，
    差异在字段名与鉴权方式。接哪一家只改 `PLATFORM_PUSH_ENDPOINT` 与
    `PLATFORM_PUSH_TOKEN`，必要时在这里加一层字段映射——
    业务侧代码一行都不用动。
    """

    name = "http"
    delivers = True

    def __init__(self, endpoint: str = "", token: str = "", timeout: float = 5.0) -> None:
        from app.core.config import settings

        self.endpoint = endpoint or settings.PUSH_ENDPOINT
        self.token = token or settings.PUSH_TOKEN
        self.timeout = timeout

    def send(self, tokens, title, body, data=None) -> VendorResult:
        if not self.endpoint:
            raise VendorError("push_not_configured",
                              "PLATFORM_PUSH_PROVIDER=http 但没有配 PLATFORM_PUSH_ENDPOINT",
                              retryable=False)
        payload = json.dumps({
            "tokens": tokens, "title": title, "body": body, "data": data or {},
        }).encode()
        req = urllib.request.Request(self.endpoint, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                out = json.loads(raw) if raw else {}
        except Exception as exc:
            # 推送失败**必须可重试**：它走发件箱，业务事务已经提交了
            raise VendorError("push_upstream", f"推送网关不可用：{exc}", retryable=True) from exc
        return VendorResult(ok=True, external_ref=str(out.get("id", "")), status="succeeded",
                            data={"delivered": out.get("delivered", len(tokens)),
                                  "invalid_tokens": out.get("invalid_tokens", [])})
