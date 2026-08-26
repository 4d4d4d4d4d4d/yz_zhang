"""VND-001/041/042 供应商注册表与启动自检。

`get_provider(kind)` 是业务侧唯一入口。新增供应商 = 在 `_REGISTRY` 里
登记一个实现类 + 设 `PLATFORM_<KIND>_PROVIDER` 环境变量。
"""
from app.core.config import settings

from .kyc import MockKycProvider
from .moderation import LocalModerationProvider
from .payment import MockPaymentProvider
from .sandbox import (
    SandboxCustodyPayment,
    SandboxKycProvider,
    SandboxModeration,
    SandboxSmsProvider,
    SandboxStorage,
)
from .sms import MockSmsProvider
from .storage import LocalStorageProvider
from .tax import CommissionedCollectionTax, LaborIncomeTax, NoWithholdingTax

# kind -> {provider_name: factory}
_REGISTRY: dict[str, dict[str, type]] = {
    "payment": {"mock": MockPaymentProvider, "sandbox": SandboxCustodyPayment},
    "sms": {"mock": MockSmsProvider, "sandbox": SandboxSmsProvider},
    "kyc": {"mock": MockKycProvider, "sandbox": SandboxKycProvider},
    "moderation": {"local": LocalModerationProvider, "sandbox": SandboxModeration},
    "storage": {"local": LocalStorageProvider, "sandbox": SandboxStorage},
    # TAX-002 三条路都是**真实算法**，不是桩：劳务报酬累进表与委托代征核定率
    # 都按现行规定实现。它们的「不可上生产」不在于算得不对，
    # 而在于缺少申报与缴库通道（见 TAX-013）与委托代征协议。
    "tax": {"none": NoWithholdingTax, "labor_income": LaborIncomeTax,
            "commissioned_collection": CommissionedCollectionTax},
}

# VND-042 生产必须接真实供应商的能力（涉及资金/身份/合规，模拟实现上线即事故）
P0_KINDS = ("payment", "sms", "kyc", "moderation")
# 各 kind 的缺省（退化）实现名
MOCK_NAMES = {"payment": "mock", "sms": "mock", "kyc": "mock", "moderation": "local",
              "storage": "local", "tax": "none"}
# STUB-002 **非生产实现集合**。判定从「等于 mock 名」改为「属于本集合」——
# 否则新增 sandbox 反而绕开了 V49 建立的上线红线。
# 补桩是为了让路径可测，**不能顺手削弱拦截**，这是本批次最容易做错的地方。
NON_PRODUCTION_NAMES = {
    kind: {MOCK_NAMES[kind], "sandbox", "mock", "local"} for kind in MOCK_NAMES
}


def provider_grade(kind: str, name: str | None = None) -> str:
    """STUB-003 三态：production / sandbox（形态真实但仍是桩）/ mock（退化实现）。"""
    name = name or configured_name(kind)
    if name == "sandbox":
        return "sandbox"
    if name in (MOCK_NAMES.get(kind), "mock", "local"):
        return "mock"
    return "production"

_instances: dict[str, object] = {}


def configured_name(kind: str) -> str:
    return getattr(settings, f"{kind.upper()}_PROVIDER", MOCK_NAMES.get(kind, "mock"))


def get_provider(kind: str):
    """按配置返回实现；未注册的名字回落到该 kind 的模拟实现（并在自检里报出）。"""
    if kind in _instances:
        return _instances[kind]
    name = configured_name(kind)
    impls = _REGISTRY.get(kind, {})
    factory = impls.get(name) or impls[MOCK_NAMES[kind]]
    _instances[kind] = factory()
    return _instances[kind]


def reset() -> None:
    """测试辅助：切换配置后清缓存。"""
    _instances.clear()


def missing_production_providers() -> list[str]:
    """VND-042/STUB-002 返回生产环境仍是**非生产实现**的 P0 能力清单。

    包含 sandbox：沙箱桩形态虽真，仍不接任何真实机构，上线即事故。
    """
    return [k for k in P0_KINDS if configured_name(k) in NON_PRODUCTION_NAMES[k]]


def startup_check() -> None:
    """生产环境启动自检：P0 能力仍是模拟实现则拒绝启动。

    这是刻意的「难用」——把上线前必须完成的对接变成硬性拦截，
    而不是一行只有开发者看得见的日志。
    """
    if settings.ENV != "prod":
        return
    problems: list[str] = []
    missing = missing_production_providers()
    if missing:
        detail = ", ".join(f"{k}({configured_name(k)})" for k in missing)
        problems.append(f"以下 P0 能力仍是非生产实现（mock/sandbox），禁止上线：{detail}")
    # LAW-001/010 签名与存证同样不得停留在桩实现
    if settings.SIGNATURE_PROVIDER in ("platform", "sandbox-ca"):
        problems.append(
            f"PLATFORM_SIGNATURE_PROVIDER={settings.SIGNATURE_PROVIDER} 为非生产实现："
            "平台见证签名与沙箱 CA 都不构成《电子签名法》的可靠电子签名"
        )
    if settings.NOTARY_PROVIDER in ("local", "sandbox-notary"):
        problems.append(
            f"PLATFORM_NOTARY_PROVIDER={settings.NOTARY_PROVIDER} 为非生产实现："
            "自算哈希链与沙箱存证都没有真实的司法采信力"
        )
    # FIN-052 上线红线：平台自建账本托管资金 = 资金池 + 二清（无证从事支付结算）。
    # 这不是配置疏忽，是业务不能这样做，因此拦截理由要写清楚。
    if settings.LEDGER_BACKEND != "custody":
        problems.append(
            "PLATFORM_LEDGER_BACKEND 仍为 internal：平台自建账本托管用户资金"
            "涉嫌资金池与二清（无证从事支付结算），不得用于真实交易。"
            "请接入持牌机构存管后设为 custody"
        )
    # TAX-001/044 上线红线：向自然人支付报酬而不代扣个税，平台作为扣缴义务人
    # 面临应扣未扣税款 50%~3 倍的罚款（《税收征收管理法》第六十九条）。
    # 允许你选择 self_declared（执行方自行申报开票），但**必须是显式选择**——
    # 默认的 none 意味着「没人想过这件事」，那才是真正的风险。
    if settings.TAX_MODE not in ("withholding", "self_declared"):
        problems.append(
            f"PLATFORM_TAX_MODE={settings.TAX_MODE}：未决定个税方案。"
            "平台向自然人支付报酬即为扣缴义务人，应扣未扣将被处应扣未扣税款"
            "50% 至 3 倍罚款。请设为 withholding（平台代扣）或 "
            "self_declared（执行方为个体户/企业自行申报并开票）"
        )
    if settings.TAX_MODE == "withholding" and settings.TAX_PROVIDER == "none":
        problems.append(
            "PLATFORM_TAX_MODE=withholding 但 PLATFORM_TAX_PROVIDER=none："
            "声明了要代扣却没有配置扣缴规则，等于没扣"
        )
    if settings.JWT_SECRET == "dev-secret-change-me":
        problems.append("PLATFORM_JWT_SECRET 仍是默认值")
    if settings.JOB_TOKEN == "dev-job-token-change-me":
        problems.append("PLATFORM_JOB_TOKEN 仍是默认值")
    if settings.DATABASE_URL.startswith("sqlite"):
        problems.append("生产不得使用 SQLite，请配置 PLATFORM_DATABASE_URL 指向 Postgres")
    # SEC-030/003 边界配置
    if settings.CORS_ORIGINS.strip() == "*":
        problems.append("PLATFORM_CORS_ORIGINS 不得为 *，请收紧到白名单域名")
    if settings.EXPOSE_DOCS:
        problems.append("生产不应暴露 API 文档（PLATFORM_EXPOSE_DOCS=1）")
    if settings.TRUSTED_PROXY_HOPS <= 0:
        problems.append(
            "PLATFORM_TRUSTED_PROXY_HOPS 未设置：反代后取不到真实客户端 IP，"
            "按 IP 的限流与封禁将全部失效"
        )
    if problems:
        raise RuntimeError("生产环境配置自检未通过：\n- " + "\n- ".join(problems))


def status() -> list[dict]:
    """VND-041 后台展示：各 kind 当前实现、是否模拟、熔断状态。"""
    from .base import circuit_state

    out = []
    for kind in _REGISTRY:
        name = configured_name(kind)
        grade = provider_grade(kind, name)
        out.append({
            "kind": kind,
            "provider": name,
            "grade": grade,                      # production / sandbox / mock
            "is_mock": grade != "production",     # 兼容既有调用方
            "circuit": circuit_state(f"{kind}:{name}"),
        })
    return out
