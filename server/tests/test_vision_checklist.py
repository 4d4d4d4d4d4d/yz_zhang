"""远景对照表不能过期（`docs/VISION.md`）。

用户问过三次「这个平台是否满足我的需求」。前两次我都是现场量一遍、
在回答里列个表格，然后那张表就随对话滚走了——下一次再问，再量一遍。

所以把愿景原话与逐条状态落成一页。而一页**手写状态**的对照表必然漂移
（V111 已经为此立过计数闸门），且漂移的方向是危险的那一侧：
接上了没改、或者没接上却写着已接，读的人都会得到错的整体判断。

这一篇让那张表自己去对账：声称「两端已接」的，就去数 web 与 App 里
真实的 SDK 调用。
"""
import re
from pathlib import Path

import pytest

from tests.clientscan import calls

REPO = Path(__file__).resolve().parents[2]
VISION = REPO / "docs" / "VISION.md"

# 状态词表。**值是判据，不是标签**——每个词都对应一条可执行的检查。
STATUS_RULES = {
    "两端已接": "列出的方法在 web 与 app 都要有真实调用",
    "仅 web": "web 有、app 没有；接上了而这里没改同样是过期",
    "仅后端": "列出的方法三端都不该有调用",
    "未实现": "不检查方法（还没有方法可查），只要求写明缺什么",
    "部分": "混合状态，不逐方法检查；要求「还缺什么」一栏说清边界",
}


def _rows() -> list[dict]:
    """解析第 2 节那张对照表。"""
    text = VISION.read_text(encoding="utf-8")
    out: list[dict] = []
    for line in text.split("\n"):
        if not line.startswith("| V-"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        out.append({
            "id": cells[0],
            "item": cells[1],
            "methods": re.findall(r"`(\w+)`", cells[2]),
            # 状态允许带批次注记（「两端已接（V122）」）——那是有用的信息，
            # 剥掉括号再比词表，而不是逼着表里不许写是哪一批接上的。
            "status": re.sub(r"（[^）]*）", "", cells[3]).strip(),
            "gap": cells[4],
        })
    return out


def test_vision_scanner_actually_finds_the_rows():
    """扫不到等于全绿，是最糟的一种绿。"""
    rows = _rows()
    assert len(rows) >= 10, f"只抽出 {len(rows)} 行，解析逻辑可能坏了"
    ids = [r["id"] for r in rows]
    # 用户复述的那六条必须在
    for need in ("V-1", "V-2", "V-3", "V-4", "V-6"):
        assert need in ids, f"对照表里找不到 {need}"
    # 至少有一行真的列了方法，否则「按方法核对」这件事根本没发生
    assert any(r["methods"] for r in rows), "没有任何一行列出 SDK 方法"


def test_vision_every_row_has_a_known_status():
    """状态必须是固定词表里的一个。

    自由措辞的状态列没法核对，于是会慢慢变成「基本完成」「接近可用」
    这类谁也说不清的话。
    """
    for row in _rows():
        assert row["status"] in STATUS_RULES, (
            f"{row['id']}（{row['item']}）的状态「{row['status']}」不在词表里："
            f"{sorted(STATUS_RULES)}"
        )


def test_vision_every_row_says_what_is_still_missing():
    """每一行都要写清还缺什么。

    **一行只写「已实现」的愿景条目是误导**：V-2 日常协作两端都接了，
    而真实支付与实名供应商都还没有——少了这句话，读的人会以为能收钱了。
    """
    for row in _rows():
        assert len(row["gap"]) >= 8, (
            f"{row['id']}（{row['item']}）没说还缺什么：「{row['gap']}」"
        )


@pytest.mark.parametrize("row", [r for r in _rows() if r["status"] == "两端已接"],
                         ids=lambda r: r["id"])
def test_vision_claimed_both_ends_are_really_reachable(row):
    """声称两端已接的，去数真实调用——不信那一行字。"""
    assert row["methods"], f"{row['id']} 声称两端已接，却没列任何方法可核对"
    for method in row["methods"]:
        for client in ("web", "app"):
            assert calls(client, method), (
                f"{row['id']}（{row['item']}）在 VISION.md 里写着「两端已接」，"
                f"而 {client} 里找不到 `{method}` 的调用。"
                "要么把那一行的状态改对，要么把它接上"
            )


@pytest.mark.parametrize("row", [r for r in _rows() if r["status"] == "仅 web"],
                         ids=lambda r: r["id"])
def test_vision_claimed_web_only_is_still_web_only(row):
    """声称仅 web 的，确实 web 有而 App 没有。

    **这一条是双向的。** 哪天 App 接上了而这一行还写着「仅 web」，
    它同样会红——过期不分方向。
    """
    assert row["methods"], f"{row['id']} 声称仅 web，却没列任何方法可核对"
    on_web = [m for m in row["methods"] if calls("web", m)]
    on_app = [m for m in row["methods"] if calls("app", m)]
    assert on_web, (
        f"{row['id']}（{row['item']}）写着「仅 web」，而 web 里一个方法都没调："
        f"{row['methods']}。它其实是「仅后端」"
    )
    assert not on_app, (
        f"{row['id']}（{row['item']}）写着「仅 web」，而 App 已经调上了 "
        f"{on_app}——这一行过期了，改成「两端已接」"
    )


@pytest.mark.parametrize("row", [r for r in _rows() if r["status"] == "仅后端"],
                         ids=lambda r: r["id"])
def test_vision_claimed_backend_only_has_no_client(row):
    """声称仅后端的，三端都不该有调用——接上了就该改这一行。"""
    for method in row["methods"]:
        wired = [c for c in ("web", "app", "admin") if calls(c, method)]
        assert not wired, (
            f"{row['id']}（{row['item']}）写着「仅后端」，而 {wired} 已经在调 "
            f"`{method}`——这一行过期了"
        )


def test_vision_quotes_the_user_verbatim_and_says_where_from():
    """原话那一节要带出处与日期。

    **不写出处的「用户原话」等于我替他说的话。** 哪天要核对我有没有
    理解偏，得能回到那一句的来源去看。
    """
    text = VISION.read_text(encoding="utf-8")
    assert "PRODUCT-DIRECTION.md" in text, "没说定位那段出自用户亲自写的哪一篇"
    for date in ("2026-10-07", "2026-10-09", "2026-10-10"):
        assert date in text, f"缺 {date} 那次的出处"
    # 几句标志性的原话必须在（改写它们就失去了「对照」的意义）
    for quote in ("今晚帮忙遛狗", "做一个机器人", "skilltool",
                  "知识图谱体系不可能把每个样本都添加", "todolist"):
        assert quote in text, f"原话里少了「{quote}」"


def test_vision_lists_the_launch_blockers_it_does_not_cover():
    """第 3 节必须在：不在愿景里、但上线前绕不过去的那些。

    只列愿景条目会给出一个危险的印象——**功能都做完了就能上线**。
    资金存管、个税方案、可靠电子签名这些不是功能，是做这门生意要有的东西。
    """
    text = VISION.read_text(encoding="utf-8")
    for must in ("资金存管", "个税", "电子签名", "GO-LIVE.md"):
        assert must in text, f"第 3 节缺「{must}」"
