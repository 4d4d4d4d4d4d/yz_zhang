"""APPB-052b lint 不能只是装上（81 号 spec）。

探针：**全仓没有任何 lint**——没有配置、没有依赖、没有脚本。
而 `web/src/pages/Square.tsx` 里躺着一行：

    // eslint-disable-next-line react-hooks/exhaustive-deps

**一条为不存在的检查写下的豁免注释。** 它与这一路反复出现的那个形状
（写下来的承诺没人核对）是同一件事的反面：**豁免了，而没有人在检查。**

所以这一篇钉三件事：
1. lint 真的在 CI 里跑（两个 job 各自跑，因为 app 不在根 workspaces 里）；
2. 每条 `eslint-disable` 引用的规则**必须真的被配置着**——否则它又变成
   一条没人核对的豁免；
3. 规则表里那几条「刻意关掉」的必须写明理由（值是原因，不是开关）。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "eslint.config.mjs"
CI = REPO / ".github" / "workflows" / "ci.yml"


def _client_sources() -> dict[str, str]:
    out = {}
    for root in (REPO / "web" / "src", REPO / "packages" / "core" / "src"):
        for p in root.rglob("*.ts*"):
            out[str(p.relative_to(REPO))] = p.read_text(encoding="utf-8")
    for p in (REPO / "app").glob("*.tsx"):
        out[str(p.relative_to(REPO))] = p.read_text(encoding="utf-8")
    return out


def test_appb052_lint_config_exists_and_is_not_empty():
    """扫不到等于全绿，是最糟的一种绿。"""
    assert CONFIG.exists(), "根上没有 eslint 配置"
    src = CONFIG.read_text(encoding="utf-8")
    assert "react-hooks" in src, "没配 hook 规则——那是这个仓最需要的一类"
    assert "no-unused-vars" in src


def test_appb052_ci_lints_every_client_source_tree():
    """要钉的不是「跑了几次 lint」，是**三个端的源码都被扫到**。

    第一版断言「CI 里至少有两处 npm run lint」——照着它写，App job 里就得
    再装一份 eslint，而 lint 是纯静态的、不需要 react-native 在位，
    那个 job 每多一个依赖都要多下一次（APPB-050 正在说的事）。
    **闸门要钉住目的，不是钉住某一种做法。**
    """
    import json

    ci = CI.read_text(encoding="utf-8")
    assert "npm run lint" in ci, "CI 里根本没跑 lint"
    root = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    cmd = root["scripts"]["lint"]
    for tree in ("packages/core/src", "web/src", "app"):
        assert tree in cmd, f"lint 的范围里没有 {tree}——那一端就是自由的"
    # lint 要排在测试前面：它几秒钟跑完，先失败能省掉后面几分钟
    front = ci[ci.index("frontend:"):]
    lint_at = front.index("npm run lint")
    test_at = front.index("npm test")
    assert lint_at < test_at, "lint 应当排在测试之前（快的先跑）"


def test_appb052_lint_scripts_exist():
    import json

    root = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    assert "lint" in root.get("scripts", {}), "根上没有 lint 脚本"
    app = json.loads((REPO / "app" / "package.json").read_text(encoding="utf-8"))
    # app 里**刻意没有** lint 脚本：它没装 eslint，留一条跑不起来的脚本
    # 比没有更糟（`command not found` 会让人以为是环境坏了）
    assert "lint" not in app.get("scripts", {}), \
        "app 里有 lint 脚本却没有 eslint 依赖——它跑起来只会报 command not found"


def test_appb052_every_disable_comment_names_a_configured_rule():
    """**豁免的那条规则必须真的被配置着。**

    `Square.tsx` 那一行豁免的是 `react-hooks/exhaustive-deps`——在这一批之前
    它豁免的是一个不存在的检查。允许这种注释留着，下一个人会以为
    「这里有人看过、并且决定放过」，而事实是**没有人看过**。
    """
    config = CONFIG.read_text(encoding="utf-8")
    offenders = []
    for path, src in _client_sources().items():
        for m in re.finditer(r"eslint-disable(?:-next-line|-line)?\s+([^\s*/]+)", src):
            rule = m.group(1).rstrip(",")
            if rule not in config:
                offenders.append(f"{path}: {rule}")
    assert not offenders, (
        "这些 eslint 豁免引用了配置里没有的规则——豁免了一个没人在检查的东西：\n  "
        + "\n  ".join(offenders)
    )


def test_appb052_disabled_rules_say_why():
    """「刻意关掉」的规则必须写明理由（V90：声明表的值是原因，不是开关）。

    否则半年后没人知道这条是「想清楚了不要」还是「当时懒得修」。
    """
    src = CONFIG.read_text(encoding="utf-8")
    tail = src[src.index("刻意关掉"):] if "刻意关掉" in src else ""
    assert tail, "配置里没有「刻意关掉」那一节"
    lines = tail.split("\n")
    for i, line in enumerate(lines):
        if "'off'" not in line:
            continue
        # 往上找几行：理由写在紧邻的注释、或这一块开头的块注释里都算。
        # 第一版只看紧邻的上一行，于是把一条**确实写了理由**的规则报成了
        # 「没写理由」——闸门的判据比它要守护的规矩更死，就会开始骗人。
        window = [l.strip() for l in lines[max(0, i - 4):i]]
        assert any(l.startswith("//") for l in window), \
            f"这条规则关掉了却没写理由：{line.strip()}"


def test_appb052_lint_is_not_bypassed_in_ci():
    """`--quiet` / `|| true` 会让 lint 变成摆设。"""
    ci = CI.read_text(encoding="utf-8")
    for bad in ("npm run lint || true", "lint --quiet", "continue-on-error: true"):
        assert bad not in ci, f"CI 里的 lint 被绕过了：{bad}"
