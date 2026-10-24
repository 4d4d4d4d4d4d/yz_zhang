"""客户端源码扫描的**唯一一份实现**。

V91~V96 攒下了五张可达性声明表——`REMEDY_UI`（请先 X 就得有 X 的入口）、
`NOTICE_ACTIONS`（通知让你做的事得做得到）、`MUST_BE_REACHABLE`（按不到就有
后果的能力）、`ADMIN_CONSOLE`（运营侧必须可达）、以及 V95 加进前者的几条。
每张表都要回答同一个问题：**这个能力在某个端上真的被用上了吗？**

而实现出现了两份：`test_remedy_ui` 一份，`test_admin_console_reachability`
另写一份。这正是我在业务代码里反复引用的那条——
**第二份实现必然抄漏**（UI-075 / TEAM-021）。事实也是：第二份一开始只看
「有没有 `.method(`」，于是把 `<WithdrawReview />` 从页面上摘掉它照样是绿的，
而第一份后来加的「组件得挂上」那一层它没有。

所以合成一份，两条规则都在这里：

1. **调用得存在**（`.method(` 出现在该端的非测试源码里）；
2. **承载它的组件得被挂上**——组件写了没挂，对用户和没做是一回事。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SDK = REPO / "packages" / "core" / "src" / "client.ts"

# 端 -> 该端的源码文件。
# 排除测试：**测试里调过一次不等于用户点得到**。
CLIENT_SRC: dict[str, list[Path]] = {
    "web": [p for p in (REPO / "web" / "src").rglob("*.ts*") if ".test." not in p.name],
    "app": [p for p in (REPO / "app").glob("*.tsx") if ".test." not in p.name],
    # 运营后台单独算一个「端」：它的入口集合与用户侧完全不同，
    # 而 V96 之前它在所有闸门的覆盖范围之外。
    "admin": [REPO / "web" / "src" / "pages" / "Admin.tsx"],
}


def sources(client: str) -> str:
    """该端的全部源码。admin 额外跟进它 import 的本地组件——
    只扫一个文件会把「组件拆出去了」误判成「功能没了」。"""
    files = list(CLIENT_SRC[client])
    text = "\n".join(p.read_text(encoding="utf-8") for p in files if p.is_file())
    if client == "admin":
        base = CLIENT_SRC["admin"][0].parent
        for rel in re.findall(r"from '(\.{1,2}/[^']+)'", text):
            for cand in (base / rel, base / f"{rel}.tsx", base / f"{rel}.ts"):
                if cand.is_file():
                    text += "\n" + cand.read_text(encoding="utf-8")
    return text


def _mounted(src: str, method: str) -> bool:
    """调用它的那个组件，真的被挂到页面上了吗。

    红验教训：把 `<WithdrawReview />` 摘掉，组件函数还在文件里，
    只看 `.method(` 的闸门照样绿。
    """
    blocks = re.split(r"\n(?=(?:export (?:default )?)?function )", src)
    owners = []
    for b in blocks:
        if not re.search(r"\." + re.escape(method) + r"\s*\(", b):
            continue
        m = re.match(r"(?:export (?:default )?)?function (\w+)", b.lstrip())
        if m:
            owners.append(m.group(1))
    if not owners:
        # 调用不在任何 function 块里（模块顶层/箭头函数组件）——
        # 这类无法判断挂载，退回「调用存在即可」，不编造一个更强的结论。
        return True
    return any(
        o in ("Admin", "App") or re.search(r"<" + o + r"[\s/>]", src)
        for o in owners
    )


def calls(client: str, method: str) -> bool:
    """这个能力在该端上**真的被用上了**。"""
    src = sources(client)
    if not re.search(r"\." + re.escape(method) + r"\s*\(", src):
        return False
    return _mounted(src, method)


def sdk_has(method: str) -> bool:
    """SDK 上真的有这个方法。

    名字写错时，上面那些断言会永远红，而人只会以为是界面没做。
    """
    return re.search(r"^  " + re.escape(method) + r"\s*\(", SDK.read_text(encoding="utf-8"),
                     re.M) is not None


def server_source() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in (REPO / "server" / "app").rglob("*.py")
    )
