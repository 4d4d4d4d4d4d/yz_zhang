"""CNT-014 / PRLX-042 App 侧视频沉浸流（46 号 spec）。

这个场景最容易做错、而且错了最致命的一条是：**同时播多个**。
每个解码中的视频都占一份硬件解码器与几十 MB 内存，滑过十条就能把中低端机
打到 OOM 或直接黑屏。所以这里的断言几乎全都围绕一件事——
**任何时刻有且只有一个 `<Video>` 在播**。

`app/` 仍未类型检查（DSPR-042），所以沿用 V70 的两道：
esbuild 真的解析一遍 + 对源码的属性断言。
"""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
APP = os.path.join(ROOT, "app")
VIDEO = os.path.join(APP, "VideoFeed.tsx")


def strip_comments(src: str) -> str:
    """去掉 // 行注释——断言钉的是代码，不是描述代码的散文。"""
    return "\n".join(line.split("//")[0] for line in src.splitlines())


def code() -> str:
    return strip_comments(open(VIDEO).read())


# ---------- 解析闸门（PRLX-002 已建，这里确认新文件也进得去） ----------
def test_video_feed_parses():
    exe = shutil.which("npx")
    if not exe:
        pytest.skip("环境里没有 npx")
    proc = subprocess.run(
        [exe, "--no-install", "esbuild", VIDEO, "--jsx=automatic", "--outfile=/dev/null"],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------- VID-001 有且只有一个在播 ----------
def test_vid001_only_the_active_page_plays():
    """每个解码中的视频占一份硬件解码器与几十 MB 内存——
    滑过十条就能把中低端机打到 OOM。"""
    src = code()
    assert "index === activeIndex" in src, "没有按当前页判定 active，可能多个同时播"
    assert "shouldPlay={shouldPlay}" in src
    assert "active && allowData" in src, "shouldPlay 没有把 active 算进去"


def test_vid002_viewability_threshold_is_high_enough():
    """阈值太低会在滑动中途短暂判定两条都可见，于是两个视频同时起播。"""
    src = code()
    assert "itemVisiblePercentThreshold: 90" in src


def test_vid003_leaving_a_page_explicitly_pauses():
    """依赖卸载来停播在快速滑动时不可靠——必须显式暂停。"""
    src = code()
    assert "pauseAsync" in src


def test_vid004_list_is_virtualized_not_a_scrollview():
    """视频比图片吃内存得多：离屏的整棵子树都要卸掉。"""
    src = code()
    assert "FlatList" in src and "ScrollView" not in src
    assert "removeClippedSubviews" in src
    assert "windowSize={3}" in src


def test_vid005_paging_is_one_video_per_screen():
    src = code()
    assert "pagingEnabled" in src
    assert "snapToInterval={SCREEN_H}" in src


# ---------- VID-010 流量提醒 ----------
def test_vid010_cellular_defaults_to_not_playing():
    """这条的代价是用户的钱，所以取不到网络类型时按「可能是流量」处理。"""
    src = code()
    assert "getNetworkStateAsync" in src
    assert "CELLULAR" in src
    # 判断函数的兜底必须是 true（＝当作蜂窝）
    fn = src.split("async function onCellular")[1].split("export function")[0]
    assert fn.count("return true") >= 2, "取不到网络类型时没有按「可能是流量」兜底"
    assert "继续播放（使用流量）" in src


# ---------- VID-020 断点续播 ----------
def test_vid020_resume_position_is_stored_locally():
    """这是每个人自己的观看进度：存本地，不占服务端，也不跟着账号跨设备。"""
    src = code()
    assert "AsyncStorage" in src
    assert "setPositionAsync" in src
    assert "MIN_RESUME_MS" in src, "快看完了还记位置，下次会跳到最后两秒"


def test_vid021_resume_happens_once_not_on_every_status_update():
    """每次 status 更新都恢复位置会让播放不停往回跳。"""
    src = code()
    assert "if (!active || resumed) return;" in src


# ---------- VID-030 无障碍与音频 ----------
def test_vid030_reduce_motion_disables_autoplay():
    """自动播放的运动画面对前庭敏感人群同样是诱因，WCAG 也要求可关闭。"""
    src = code()
    assert "isReduceMotionEnabled" in src
    assert "!reduceMotion || manualPlay" in src
    assert "已按系统设置关闭自动播放" in src, "悄悄不播，用户会以为 App 坏了"


def test_vid031_ios_silent_switch_does_not_mute_the_feed():
    """默认的 iOS 静音开关会让沉浸流没声音，用户以为视频坏了。"""
    src = code()
    assert "playsInSilentModeIOS: true" in src


def test_vid032_rate_change_does_not_change_pitch():
    src = code()
    assert "shouldCorrectPitch" in src
    assert "RATES = [1, 1.25, 1.5, 2]" in src


# ---------- VID-040 接进了 App ----------
def test_vid040_video_tab_is_wired_in():
    src = strip_comments(open(os.path.join(APP, "App.tsx")).read())
    assert "VideoFeedScreen" in src and "'video'" in src and "'视频'" in src


def test_vid041_new_dependencies_are_declared():
    """用了 expo-av / expo-network / AsyncStorage 就必须写进 package.json——
    否则真机上是「打开就崩」，而本环境的解析闸门看不出来（不做模块解析）。"""
    import json

    deps = json.load(open(os.path.join(APP, "package.json")))["dependencies"]
    for pkg in ("expo-av", "expo-network", "@react-native-async-storage/async-storage"):
        assert pkg in deps, f"{pkg} 没有声明在 app/package.json"
