"""PRLX-050~057 视觉运动层的四条闸门（79 号 spec）。

用户要的是「科技感」，而这一批的风险不在做不出效果，在**效果伤到功能**：

- 视差的本质是元素随滚动移动，而移动的元素包括按钮。
  **一个在手指底下漂移的按钮不是效果，是功能缺陷**——
  而钱包、提现、签署这几个页面上点错一下的代价是钱。
- `prefers-reduced-motion` 开着的人里有相当一部分是前庭功能障碍者，
  大面积位移是明确的眩晕诱因，**减半仍然会让人难受**。

所以这几条不靠「记得别在那儿用」，靠表 + 扫描。
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "web" / "src"
APP = REPO / "app"
MOTION_TSX = WEB / "Motion.tsx"
STYLES = WEB / "styles.css"

# PRLX-050 **不许有位移动效**的页面 -> 为什么。
#
# 值是**理由**而不是布尔（V90 那条：声明表的值是原因，不是开关）——
# 写成 True/False 的话，下一个人会顺手把某一行改掉。
MOTION_FORBIDDEN: dict[str, str] = {
    "pages/Wallet.tsx": "提现与充值按钮在手指底下漂移，点错一下的代价是钱",
    "pages/TaskDetail.tsx": "签署、验收、发起纠纷都在这一页，误触的后果不可逆",
    "pages/Teams.tsx": "支出审批与驳回在这里，按错一个就是批了一笔钱",
    "pages/Admin.tsx": "封禁、放款、结算——运营侧的每个按钮都有后果",
    "pages/Verify.tsx": "核验结论提交后直接影响放款",
    "pages/Login.tsx": "登录页要的是快，不是好看；动效只会推迟第一次输入",
}

# 运动层里只许出现这些会被动画/滚动驱动的属性
ALLOWED_ANIMATED = ("transform", "opacity")
# 一眼就该拒绝的：这些属性参与滚动动画会触发重排
REFLOW_PROPS = ("top:", "left:", "right:", "bottom:", "width:", "height:",
                "margin", "padding", "font-size")


def _web_sources() -> dict[str, str]:
    return {
        str(p.relative_to(WEB)): p.read_text(encoding="utf-8")
        for p in WEB.rglob("*.tsx") if ".test." not in p.name
    }


# ---------------------------------------------------- 扫描器自己先会红
def test_prlx_scanner_sees_the_motion_layer():
    """扫不到等于全绿，是最糟的一种绿。"""
    assert MOTION_TSX.exists(), "运动层组件不在预期位置"
    src = MOTION_TSX.read_text(encoding="utf-8")
    for token in ("TechBackdrop", "ParallaxHero", "Reveal", "prefers-reduced-motion"):
        assert token in src, f"运动层里找不到 {token}"
    css = STYLES.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css, "样式里没有 reduced-motion 分支"
    # 反向：编一个不存在的名字必须扫不到
    assert "NopeNotAComponent" not in src


def test_prlx_motion_is_actually_used_somewhere():
    """闸门不能只证明「没人用」——效果得真的接上了。"""
    users = [f for f, src in _web_sources().items()
             if "ParallaxHero" in src or "Reveal" in src or "TechBackdrop" in src]
    assert len(users) >= 3, f"运动层几乎没有被用上：{users}"


# ---------------------------------------------------- PRLX-050 禁区
@pytest.mark.parametrize("page", sorted(MOTION_FORBIDDEN))
def test_prlx050_money_and_signing_pages_have_no_motion(page):
    """`{page}`：不许出现视差与入场位移。"""
    src = (WEB / page).read_text(encoding="utf-8")
    for banned in ("ParallaxHero", "Reveal"):
        assert banned not in src, (
            f"{page} 用了 {banned}，而它在禁区表里：{MOTION_FORBIDDEN[page]}"
        )


def test_prlx050_the_forbidden_table_says_why():
    """理由不能是一句空话，也不能是布尔值。"""
    assert len(MOTION_FORBIDDEN) >= 5
    for page, why in sorted(MOTION_FORBIDDEN.items()):
        assert (WEB / page).exists(), f"禁区表里留了一个不存在的页面：{page}"
        assert len(why) >= 12, f"{page} 的理由太短：{why}"


# ---------------------------------------------------- PRLX-052 只动 transform/opacity
def test_prlx052_scroll_driven_styles_only_touch_transform_and_opacity():
    """动 top / height / margin 会在滚动时触发重排——做出来比不做还卡。

    扫的是样式表里**用到 `--sy`（滚动量变量）的那些规则块**：
    它们是真正被滚动驱动的，其余静态样式不受这条限制。
    """
    css = STYLES.read_text(encoding="utf-8")
    blocks = re.findall(r"\{[^}]*--sy[^}]*\}", css)
    assert blocks, "样式里没有任何滚动驱动的规则？扫描逻辑可能坏了"
    for block in blocks:
        for prop in REFLOW_PROPS:
            assert prop not in block, (
                f"滚动驱动的规则里出现了会触发重排的 {prop}：{block[:120]}"
            )
        assert any(a in block for a in ALLOWED_ANIMATED), \
            f"滚动驱动的规则里没有 transform/opacity：{block[:120]}"


def test_prlx053_scroll_handler_does_not_setstate():
    """滚动回调里 setState 会让整棵树每帧重渲染（45 号 PRLX-030）。

    运动层里滚动监听只允许写 CSS 变量。
    """
    src = MOTION_TSX.read_text(encoding="utf-8")
    handler = src[src.index("function useScrollVar"):src.index("/** 全站固定背景")]
    assert "setProperty" in handler, "滚动量不是写进 CSS 变量的？"
    assert "requestAnimationFrame" in handler, "没有 rAF 节流"
    assert "setState" not in handler and "useState" not in handler, \
        "滚动路径上出现了 state 写入——每帧重渲染比不做视差还卡"


# ---------------------------------------------------- PRLX-051 reduced-motion
def test_prlx051_reduced_motion_is_off_not_halved():
    """完全关闭，不是减半。

    减半的位移对前庭功能障碍者仍然是位移。所以 CSS 里那一段必须是
    `transform: none`，而不是一个更小的系数。
    """
    css = STYLES.read_text(encoding="utf-8")
    m = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.+?)\n\}", css, re.S)
    assert m, "样式里没有 reduced-motion 分支"
    block = m.group(1)
    assert "transform: none" in block, "reduced-motion 下没有把位移清零"
    assert "translate" not in block, "reduced-motion 分支里还留着位移"

    # 组件侧也要：Reveal 直接到终态，hero 不挂滚动监听
    src = MOTION_TSX.read_text(encoding="utf-8")
    assert "if (reduce) { setShown(true); return; }" in src, \
        "Reveal 在 reduced-motion 下没有直接到终态"
    assert "useScrollVar(ref, !reduce)" in src, \
        "reduced-motion 下还在挂滚动监听"


# ---------------------------------------------------- PRLX-057 App 只有一份实现
def test_prlx057_app_has_exactly_one_reduce_motion_implementation():
    """三条约束（native driver / 完全关闭 / 不 setState）抄第二遍必然漏一条。"""
    defs = []
    for p in APP.glob("*.tsx"):
        if ".test." in p.name:
            continue
        if re.search(r"function useReduceMotion\b", p.read_text(encoding="utf-8")):
            defs.append(p.name)
    assert defs == ["motion.tsx"], f"`useReduceMotion` 的定义应当只有一处，实际：{defs}"


def _without_comments(src: str) -> str:
    """去掉注释再扫。

    第一版直接在全文里找 `useNativeDriver`，结果命中了一段**解释它为什么
    重要的注释**——扫描器把文档当成了代码。满口假警报的闸门会被人关掉
    （V82 立过这条），所以宁可先把注释剥掉。
    """
    out = []
    for line in src.split("\n"):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        out.append(line.split("//")[0] if "//" in line and "://" not in line else line)
    return "\n".join(out)


def test_prlx057_discover_reuses_the_shared_helpers():
    """发现流必须用共享实现，而不是自己留一份。"""
    src = (APP / "Discover.tsx").read_text(encoding="utf-8")
    assert "from './motion'" in src, "Discover 没有复用共享运动层"
    code = _without_comments(src)
    assert "Animated.event(" not in code, \
        "Discover 里又自己建了一个滚动驱动——那一层应当只在 motion.tsx 里"
    assert "interpolate(" not in code, \
        "Discover 里又自己写了一份 hero 变换（第二份实现必然抄漏）"


def test_prlx057_native_driver_only_animates_allowed_props():
    """native driver 下动 transform/opacity 之外的属性会在**真机上**抛错。

    CI 看不见这种错误，所以这里从源码上拦住。
    """
    src = (APP / "motion.tsx").read_text(encoding="utf-8")
    assert "useNativeDriver: true" in src
    # 同样先剥注释：注释里正解释着「不能动 height/top」
    animated = re.findall(
        r"(translateY|scale|opacity|height|width|top|left|backgroundColor)",
        _without_comments(src))
    bad = {a for a in animated if a in ("height", "width", "top", "left", "backgroundColor")}
    assert not bad, f"运动层里动了 native driver 不支持的属性：{sorted(bad)}"
