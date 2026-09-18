"""APP-002 App 发现流的视差滚动（45 号 spec）。

视差不是"加个动画"。在 React Native 上它有三条非做不可的约束，
每一条不这样做都会实打实地伤到人或伤到体验：

① **必须走 native driver**——否则每帧都在 JS 线程算，滚动时必掉帧。
② **必须尊重系统「减弱动态效果」**——开着这个开关的人里有相当一部分是
   前庭功能障碍者，大面积位移是明确的眩晕诱因。这是无障碍底线，不是加分项。
③ **滚动位置不能进 setState**——每帧重渲染整棵树，比不做视差还卡。

`app/` 仍未被 typecheck（DSPR-042），所以这里做两件事：
用 esbuild 真的解析一遍（能抓语法/JSX 错误，不需要装 expo），
再用字面量钉住上面三条属性。
"""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
APP = os.path.join(ROOT, "app")
DISCOVER = os.path.join(APP, "Discover.tsx")


def strip_comments(src: str) -> str:
    """去掉 // 行注释——断言钉的是代码，不是描述代码的散文（V58/V69 两次教训）。"""
    return "\n".join(line.split("//")[0] for line in src.splitlines())


def esbuild_ok(path: str) -> tuple[bool, str]:
    exe = shutil.which("npx")
    if not exe:
        pytest.skip("环境里没有 npx")
    proc = subprocess.run(
        [exe, "--no-install", "esbuild", path, "--jsx=automatic", "--outfile=/dev/null"],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    return proc.returncode == 0, proc.stdout + proc.stderr


# ---------- PRLX-001 App 源码真的能被解析 ----------
@pytest.mark.parametrize("name", ["App.tsx", "Discover.tsx"])
def test_prlx001_app_sources_parse(name):
    """比字面量检查强一档：能抓语法与 JSX 错误，且不需要装 expo/react-native。

    这不等于类型检查（DSPR-042 仍然开着），但「改完 App 连解析都不过」
    这一类错误从此不会溜到真机上才发现。
    """
    ok, out = esbuild_ok(os.path.join(APP, name))
    assert ok, f"{name} 解析失败：\n{out[:800]}"


def test_prlx001_the_parse_gate_actually_catches_a_broken_file(tmp_path):
    """闸门本身必须会红——否则它只是一个让人安心的摆设。"""
    bad = tmp_path / "Broken.tsx"
    bad.write_text("export function X() { return <div>unclosed }\n")
    ok, _ = esbuild_ok(str(bad))
    assert not ok


# ---------- PRLX-010 native driver ----------
def test_prlx010_scroll_animation_runs_on_the_native_driver():
    """JS driver 的视差在滚动时会肉眼可见地掉帧——滚动时 JS 线程本来就忙。"""
    code = strip_comments(open(DISCOVER).read())
    assert "Animated.event" in code
    assert "useNativeDriver: true" in code, "视差没走 native driver，滚动必卡"


def test_prlx011_only_transform_and_opacity_are_animated():
    """native driver **只能动 transform 与 opacity**。

    动了 height/top/backgroundColor 会在运行时抛
    "Style property 'x' is not supported by native animated module"——
    而那是真机上才炸，CI 看不见。
    """
    code = strip_comments(open(DISCOVER).read())
    # interpolate 的结果只应喂给 translateY / scale / opacity
    for prop in ("translateY", "scale", "opacity"):
        assert prop in code
    for forbidden in ("height: scrollY", "top: scrollY", "backgroundColor: scrollY"):
        assert forbidden not in code, f"{forbidden} 不能上 native driver"


def test_prlx012_scroll_position_never_goes_through_setstate():
    """每帧 setState 会让整棵树重渲染，比不做视差还卡。"""
    code = strip_comments(open(DISCOVER).read())
    assert "new Animated.Value(0)" in code
    # 滚动回调里不得出现 setState 类调用
    handler = code.split("Animated.event")[1][:400]
    assert "setState" not in handler and "setScroll" not in handler


# ---------- PRLX-020 无障碍：减弱动态效果 ----------
def test_prlx020_reduce_motion_is_respected():
    """开着这个开关的人里有相当一部分是前庭功能障碍者。

    大面积位移是明确的眩晕诱因——这是无障碍底线，不是加分项。
    """
    code = strip_comments(open(DISCOVER).read())
    assert "AccessibilityInfo" in code
    assert "isReduceMotionEnabled" in code
    assert "reduceMotionChanged" in code, "开关在使用中被打开时也要立刻生效"


def test_prlx021_reduce_motion_disables_parallax_completely_not_halfway():
    """开了开关就**完全关掉**，而不是「减半」——减半仍然会让人晕。"""
    code = strip_comments(open(DISCOVER).read())
    # 头部 transform 在 reduceMotion 时是空数组（没有任何位移）
    assert "reduceMotion ? [] :" in code
    # 卡片内配图位移在 reduceMotion 时是 0
    assert "reduceMotion ? 0 :" in code
    # 标题透明度在 reduceMotion 时恒为 1
    assert "reduceMotion ? 1 :" in code


def test_prlx022_reduce_motion_state_is_visible_to_the_user():
    """悄悄关掉动效，用户会以为是 App 坏了。"""
    code = strip_comments(open(DISCOVER).read())
    assert "已按系统设置关闭动效" in code


# ---------- PRLX-030 接进了 App ----------
def test_prlx030_discover_tab_is_wired_in():
    code = strip_comments(open(os.path.join(APP, "App.tsx")).read())
    assert "DiscoverScreen" in code
    assert "'discover'" in code
    assert "'发现'" in code
