"""SEC-002 安全响应头。

每一条都对应一类真实攻击：
- nosniff        → 阻止浏览器把上传的图片按内容猜成脚本执行
- frame DENY     → 点击劫持
- CSP            → XSS 的最后一道防线（即便注入了脚本也加载不了外部资源）
- Referrer       → 防止把带 id 的内部 URL 泄露给第三方站点
- Permissions    → 关掉页面用不到的敏感能力（摄像头/麦克风由前端显式请求）
- HSTS           → 只在 prod 下发，开发用 HTTP 时发了会把本地浏览器锁死
"""
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings

CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self), camera=(self), microphone=()",
    "Content-Security-Policy": CSP,
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in HEADERS.items():
            response.headers.setdefault(key, value)
        if settings.ENV == "prod":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
