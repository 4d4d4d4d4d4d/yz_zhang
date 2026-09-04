"""FIN-020~023 分利模式的法律边界（25 号 spec 第 C 节）。

「早期项目到完成如何分利」在法律上分两类，性质完全不同：

| 模式 | 性质 | 能不能做 |
|---|---|---|
| 按里程碑结算劳务报酬 / 一次性结算 / 变更单调整 | 合同履约 | ✅ |
| 按项目**收益分成**给执行者 | 可能构成合伙/投资 | ⚠️ 需个案法律意见 |
| **股权/期权式回报** | 涉众性金融 | ❌ 非持牌不得做 |
| 承诺**保本保收益** | 非法集资特征 | ❌ 绝对禁止 |

本模块把红线做成**发布环节的硬拦截**，而不是写在用户协议里指望没人踩。
"""
import re

from app.core.errors import bad_request

# FIN-020 计价方式白名单：只允许劳务对价，不接受任何收益分成与股权对价
ALLOWED_PRICING = ("fixed", "milestone", "hourly", "bidding")

# FIN-021 金融话术词表。**刻意与普通违禁词分开**：
# 这些词本身不下流也不违法，它们的问题是把一个劳务合同变成金融产品，
# 因此需要独立的拦截理由与提示文案，不能和「刷单」一类混为一谈。
FINANCE_TERMS = (
    "分红", "股权", "原始股", "期权", "股份", "干股",
    "保本", "保收益", "年化", "收益率", "回报率", "返息",
    "众筹", "募资", "集资", "投资理财", "代客理财",
    "虚拟币", "代币", "ICO", "挖矿收益",
)

# 「投资」单独处理：正常语境里也可能出现（如「投资人对接」），
# 只有与回报承诺连用时才构成问题
_INVEST_PATTERN = re.compile(
    r"投资.{0,8}(回报|收益|分红|保本)|(回报|收益|分红|保本).{0,8}投资"
)


def check_pricing(pricing: str) -> None:
    """FIN-020 计价方式硬约束。"""
    if pricing not in ALLOWED_PRICING:
        raise bad_request(
            f"不支持的计价方式「{pricing}」。平台仅支持劳务报酬结算"
            f"（{'/'.join(ALLOWED_PRICING)}），不接受收益分成或股权对价。",
            "pricing_not_allowed",
        )


def scan_finance_terms(text: str) -> str | None:
    """返回命中的金融话术词，未命中返回 None。"""
    for word in FINANCE_TERMS:
        if word in text:
            return word
    if _INVEST_PATTERN.search(text):
        return "投资回报承诺"
    return None


def assert_no_finance_offer(text: str) -> None:
    """FIN-021 文案风控：命中即拒绝发布，并说明**为什么**。

    只说「含违禁词」没有意义——发布者不知道自己踩的是金融合规红线，
    改个词还会再发一次。
    """
    hit = scan_finance_terms(text)
    if hit:
        raise bad_request(
            f"任务内容含「{hit}」等金融性表述。平台任务是劳务/服务合同，"
            f"报酬为劳务对价；涉及收益分成、股权期权或保本保收益的内容"
            f"属于涉众性金融，非持牌不得发布。请改为按工作量或里程碑计价。",
            "finance_offer_forbidden",
        )


# FIN-022 合约条款定性：把「这是劳务合同、不是投资」写进当事人合意里，
# 而不是只写在平台规则中。定性写进合同才有对抗力。
CONTRACT_NATURE_CLAUSE = (
    "性质声明: 本合同为承揽/服务合同，报酬系劳务对价，"
    "不构成任何投资、入股、合伙或保本保收益安排；"
    "双方之间不成立劳动关系。"
)
