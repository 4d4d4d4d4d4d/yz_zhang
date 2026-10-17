"""I18N-010 服务端的语言协商：**唯一解析点**（55 号 spec）。

服务端的多语种消息**这一批不做**——见 55 号 spec 第 1 节：
错误的稳定契约是 `code`，客户端按 code 出文案，服务端消息是兜底。
这里只负责把「用户想要哪个语种」解析出来并挂到请求上，
供将来需要按语种分支的地方（如导出的文书语种）使用。

做成单一解析点，是为了避免「每个端点各自读一次 Accept-Language 再各自
匹配一遍」——那种写法迟早在某处匹配规则不一致，而且不会有任何东西报错。
"""
from fastapi import Header

# 与 packages/core/src/i18n.ts 的 SUPPORTED_LOCALES 一致（有测试对齐）
SUPPORTED_LOCALES = ("zh-CN", "en")
DEFAULT_LOCALE = "zh-CN"


def resolve_locale(accept_language: str = "", user_preference: str = "") -> str:
    """协商顺序：**用户偏好优先于浏览器设置**。

    他明确选过的，不该被浏览器的 Accept-Language 覆盖——
    很多人的浏览器语言并不是他想看的语言（公司统一装机、二手设备等）。

    `zh-TW` 回落 `zh-CN` 是一个**产品决定**：简繁差异不只是字形，
    但在没有繁体文案之前，回落到简体比回落到英文好。
    """
    candidates = [user_preference or ""]
    for part in (accept_language or "").split(","):
        candidates.append(part.split(";")[0].strip())
    for raw in candidates:
        tag = (raw or "").lower()
        if tag.startswith("zh"):
            return "zh-CN"
        if tag.startswith("en"):
            return "en"
    return DEFAULT_LOCALE


def locale_dep(accept_language: str = Header(default="", alias="Accept-Language")) -> str:
    """FastAPI 依赖。用户偏好需要用户上下文，由端点自行叠加。"""
    return resolve_locale(accept_language)
