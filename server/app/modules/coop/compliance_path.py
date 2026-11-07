"""COOP-040 合规路径引擎：**告诉你需要什么，而不是拦住你**。

需求说得很清楚——合规是路径上的一步，需要什么文件就生成什么、
需要什么资质就去办。所以这里做的是**判定 + 生成 + 指引**，不是拒绝。

与 `finance/compliance.py` 的关系要说清楚，两者方向相反但不冲突：

- `finance/compliance.py` 管的是**任务发布**：任务报酬必须是劳务对价，
  出现「分红/股权/保本」就拒绝。那条红线不动——它防的是
  「面向不特定多数人发行可分享收益的权益」。
- 这里管的是**合作体内部**：已实名的成员之间、按已确认贡献、
  分已经到账的钱。这是合作内部分配，不是公开发行。

两者靠三条结构性设计分开（见 50 号 spec 第 3 节）：邀请制、只分已实现收益、
份额不可转让。**那三条在代码里是硬的**，这个引擎只负责把「还需要办什么」
讲清楚。
"""
from dataclasses import dataclass, field

# 这些阈值是**提示触发点**，不是许可线。越过了只是说「该去办某件事了」。
MANY_MEMBERS = 10
LARGE_CUMULATIVE_DISTRIBUTION_CENTS = 5_000_000      # 累计分配 ¥50,000

RISK_DISCLOSURE_VERSION = "2026-09-01"

# COOP-030 风险揭示书的四条必备内容。
# **是常量不是运营可改的文案**：这几条一旦被改软，整个模式的性质就变了。
RISK_DISCLOSURE_POINTS = (
    "份额由已确认贡献计算得出，会**随他人后续贡献而稀释**；",
    "合作体**可能不产生任何收益**，你的投入可能没有任何回报；",
    "分配只来自合作体**已经实际收到**的收入，平台不承诺、不保证任何回报；",
    "份额**不可转让、不可赎回**，不构成投资、股权、债权或任何金融产品。",
)

RISK_DISCLOSURE_TITLE = "早期合作风险揭示书"


@dataclass
class PathItem:
    key: str
    title: str
    why: str
    status: str                    # ready / todo / na
    action: str = ""


@dataclass
class CompliancePath:
    documents: list[PathItem] = field(default_factory=list)
    registrations: list[PathItem] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "documents": [vars(i) for i in self.documents],
            "registrations": [vars(i) for i in self.registrations],
            "notices": self.notices,
            # COOP-053 **不假装这是法律意见。**
            "disclaimer": (
                "以上为基于合作体当前属性生成的结构化提示与文书模板，"
                "**不是法律意见**。文书是否适用、如何修改，"
                "以及是否需要办理相应登记或资质，请由执业律师就个案出具意见。"
            ),
        }


def evaluate(*, member_count: int, has_funds: bool, distributed_total_cents: int,
             distribution_count: int, category_required_cert: str = "") -> CompliancePath:
    """按合作体的**客观属性**判定，不靠人填问卷。

    每一项都写明「为什么需要」——只给一张清单而不说理由，
    用户不知道哪些能省、哪些不能，最后要么全不做要么全找律师。
    """
    path = CompliancePath()

    # ---- 必备文书 ----
    path.documents.append(PathItem(
        key="risk_disclosure", title=RISK_DISCLOSURE_TITLE,
        why="合作有风险且份额会被稀释，加入前必须让每个人知道",
        status="ready", action="成员加入前签署（系统强制）",
    ))
    path.documents.append(PathItem(
        key="cooperation_agreement", title="合作协议",
        why="约定贡献如何计价、份额如何计算、收益如何分配、争议如何解决",
        status="ready", action="由全体成员签署",
    ))
    path.documents.append(PathItem(
        key="contribution_confirmation", title="贡献确认书",
        why="份额的唯一依据是已确认贡献，确认过程本身要有书面留痕",
        status="ready" if member_count >= 2 else "todo",
        action="每笔贡献由另一名成员确认时自动生成" if member_count >= 2
               else "至少需要 2 名成员，否则没有人能确认贡献",
    ))
    if distribution_count > 0:
        path.documents.append(PathItem(
            key="distribution_statement", title="收益分配方案与确认书",
            why="分配依据（份额快照）与实际到账金额必须可核对",
            status="ready", action="每次分配自动生成",
        ))
        path.notices.append(
            "分配所得的税务定性（经营所得 / 劳务报酬）可能影响申报方式，"
            "当前按劳务报酬口径代扣，**具体定性建议咨询税务专业人士**。"
        )

    # ---- 是否触达需要办理的门槛 ----
    if member_count > MANY_MEMBERS:
        path.registrations.append(PathItem(
            key="entity_registration", title="考虑设立经营主体",
            why=f"成员已超过 {MANY_MEMBERS} 人，人数较多时以自然人合作方式"
                f"对外签约、开票、承担责任都会变得困难",
            status="todo", action="咨询后办理个体工商户 / 合伙企业 / 公司登记",
        ))
    if distributed_total_cents > LARGE_CUMULATIVE_DISTRIBUTION_CENTS:
        path.registrations.append(PathItem(
            key="tax_registration", title="经营主体与税务登记",
            why=f"累计分配已超过 ¥{LARGE_CUMULATIVE_DISTRIBUTION_CENTS / 100:,.0f}，"
                f"持续性经营收入通常需要以经营主体名义申报",
            status="todo", action="咨询税务师后办理登记",
        ))
    if has_funds:
        path.documents.append(PathItem(
            key="fund_management", title="资金管理约定",
            why="合作体有共同资金池，谁能动、怎么动、动多少要事先写清楚",
            status="ready", action="并入合作协议",
        ))
    if category_required_cert:
        path.registrations.append(PathItem(
            key="category_certification", title=f"「{category_required_cert}」职业资质",
            why="合作体所在类目属于受限类目，承接业务前需要具备相应资质",
            status="todo", action="由具备资质的成员完成平台资质核验",
        ))

    return path


def risk_disclosure_text(venture_name: str) -> str:
    lines = [f"《{RISK_DISCLOSURE_TITLE}》（版本 {RISK_DISCLOSURE_VERSION}）",
             f"合作体：{venture_name}", "", "在加入本合作体前，请确认你已理解："]
    lines += [f"{i}. {p}" for i, p in enumerate(RISK_DISCLOSURE_POINTS, 1)]
    lines += ["", "签署即表示你已阅读并理解上述全部内容。"]
    return "\n".join(lines)
