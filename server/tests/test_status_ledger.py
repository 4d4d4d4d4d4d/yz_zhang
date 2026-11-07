"""状态台账不能过期（72 号 spec）。

每个 spec 末尾的「这一批没做的」都是**写那一批时的实况**，写完就冻在那儿了。
26 个 spec 里一共 101 条这样的记录，而其中 20 条早就被后面的批次做掉了——
一个今天来读这些 spec 的人，会得到一份系统性偏悲观的印象。

**逐批记缺口是诚实的；但只逐批记、不收口，诚实会慢慢变成误导。**

所以台账（72 号）要么跟着走，要么这里红。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPECS = REPO / "docs" / "specs"
LEDGER = SPECS / "72-status-ledger.md"

# 功能点编号形如 TASK-001 / AGT-070 / I18N-050 / APPB-051
ID_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,7}(?:-[A-Z]+)?-\d{3})\b")


# 「还没做」这一节的标题写法。
#
# 第一版只认「这一批没做的」五个字。放宽的由来：V121 写设计 spec 时把小节
# 叫成「这一**篇**没做的」（那三篇是设计，不是批次，「批」字不对），顺手
# 一比才发现**用户自己的 88 号 spec 用的是「后续设计，尚未交付」**——
# 于是它那一节里的 SPACE-020/024/025/026/027/028 **六条从来没被这个闸门看过**。
#
# 这与 V116 是同一个形状：我写的扫描器只认我当时的写法（那次是只认双引号）。
# **一个闸门漏掉的东西不会报错，它只是什么都不查**——而这次漏掉的，
# 恰好是整个产品方向的设计基准那一篇。
OPEN_SECTION_RE = re.compile(r"^##\s+.*(?:这一[批篇]没做的|尚未交付).*$", re.M)


def _open_section(text: str) -> str:
    """取出「还没做」那一节（到下一个 `##` 为止）。"""
    # 标题必须是固定的几种写法之一。
    # 16-traceability 里有形状相近的段落，抽出来的却是**已实现**的编号——
    # 闸门第一版因此把一堆做完的功能点当成缺口报了出来。
    m = OPEN_SECTION_RE.search(text)
    if not m:
        return ""
    body = text[m.end():]
    nxt = re.search(r"^##\s", body, re.M)
    return body[:nxt.start()] if nxt else body


def _declared_open_ids() -> dict[str, set[str]]:
    """全仓 spec 的「没做的」小节里提到的功能点编号 → 出现在哪些 spec。"""
    out: dict[str, set[str]] = {}
    for p in sorted(SPECS.glob("*.md")):
        if p.name in (LEDGER.name, "16-traceability.md"):
            continue
        for line in _open_section(p.read_text(encoding="utf-8")).split("\n"):
            if not re.match(r"^\s*-\s", line):
                continue
            # 只认**条目开头**的编号。正文里引用的编号（「见 TEAM-011 的理由」、
            # 「那是 KB-040 那条线」）是解释，不是缺口——第一版把它们也收了，
            # 于是台账被迫去交代一堆并不存在的欠账。
            head = re.sub(r"^\s*-\s*", "", line)[:28]
            for fid in ID_RE.findall(head):
                out.setdefault(fid, set()).add(p.name)
    return out


def test_ledger_scanner_actually_finds_ids():
    """扫不到等于全绿，是最糟的一种绿（V82 立的规矩）。"""
    found = _declared_open_ids()
    assert len(found) >= 40, f"只抽出 {len(found)} 个编号，提取逻辑可能坏了"
    # 几条已知一定在「没做的」里被提到过
    for known in ("CLI-071", "TEAM-063", "AGT-052"):
        assert known in found, f"扫不到已知编号 {known}"
    # 三种小节标题写法都要认。SPACE-025 只出现在 88 号 spec 的
    # 「后续设计，尚未交付」里，AI-DEC-023 只出现在 96 号的「这一篇没做的」里——
    # 把 OPEN_SECTION_RE 收回只认「这一批」，这两条就会同时消失。
    for known, why in (("SPACE-025", "88 号用的是「尚未交付」"),
                       ("AI-DEC-023", "96 号用的是「这一篇没做的」")):
        assert known in found, f"扫不到 {known}（{why}）——标题写法又漏了一种"
    # 反向：编一个不存在的编号，必须扫不到
    assert "NOPE-999" not in found


def test_every_open_item_appears_in_the_ledger():
    """各 spec 记下的每一个缺口编号，台账里都要有交代。

    交代有两种：还在「未实现」表里，或者在「已关闭」表里写明被谁做掉了。
    **新批次加了缺口而台账没记，这条就会红。**
    """
    ledger = LEDGER.read_text(encoding="utf-8")
    missing = {
        fid: where for fid, where in _declared_open_ids().items()
        if fid not in ledger
    }
    assert not missing, (
        "这些缺口编号在 spec 的「没做的」里记着，而 72 号台账里没有交代：\n  "
        + "\n  ".join(f"{fid}（出现在 {', '.join(sorted(w))}）"
                      for fid, w in sorted(missing.items()))
        + "\n要么补进「未实现」表，要么放进「已关闭」表并写明关掉它的批次。"
    )


def test_closed_items_say_which_batch_closed_them():
    """「已经做了」而不说是谁做的，等于又一句无人核对的话。

    已关闭那张表的每一行都必须带批次号（V\\d+）。
    """
    ledger = LEDGER.read_text(encoding="utf-8")
    m = re.search(r"^##\s*3\..*$", ledger, re.M)
    assert m, "台账里找不到「已关闭」那一节"
    section = ledger[m.end():]
    nxt = re.search(r"^##\s", section, re.M)
    if nxt:
        section = section[:nxt.start()]

    rows = [l for l in section.split("\n")
            if l.startswith("|") and "---" not in l and "旧 spec" not in l]
    assert len(rows) >= 10, f"已关闭表只有 {len(rows)} 行，看起来没抽对"
    for row in rows:
        assert re.search(r"V\d+", row), f"这一行没说是哪个批次关掉的：{row.strip()[:80]}"


def test_ledger_classifies_where_each_gap_is_stuck():
    """未实现必须分类：卡在外部（要持牌/账号/真机）、纯欠账、还是有意不做。

    不分类的清单会被当成「都还没做」，而「有意不做」和「缺个供应商账号」
    与「我们欠着」是三件完全不同的事。
    """
    ledger = LEDGER.read_text(encoding="utf-8")
    for heading in ("卡在外部", "卡在我们自己", "有意不做"):
        assert heading in ledger, f"台账缺「{heading}」这一类"


# ------------------------------------------------- GO-LIVE 的红线清单不能漏
def test_go_live_doc_lists_every_startup_blocker():
    """上线文档里的红线清单必须与 `startup_check` 真正拦的东西一致。

    这是同一类漂移的又一次：**文档说的和代码做的不是一回事**。
    加了一条拦截却不写进文档，运维就会在上线当天才第一次见到它；
    写了却没在代码里拦，那句话就是一句没人负责的承诺（V96 的教训）。
    """
    doc = (REPO / "docs" / "GO-LIVE.md").read_text(encoding="utf-8")
    src = (REPO / "server" / "app" / "vendors" / "registry.py").read_text(encoding="utf-8")

    start = src.index("def startup_check()")
    body = src[start:src.index("\ndef ", start + 10)]
    # 拦截理由里提到的每一个 PLATFORM_* 变量
    blockers = set(re.findall(r"PLATFORM_[A-Z_]+", body))
    assert len(blockers) >= 8, f"只抽出 {len(blockers)} 个红线变量，提取逻辑可能坏了"

    missing = sorted(b for b in blockers if b not in doc)
    assert not missing, (
        "`startup_check` 会因为这些变量拒绝启动，而 GO-LIVE.md 没有写它们：\n  "
        + "\n  ".join(missing)
        + "\n运维会在上线当天才第一次见到这些拦截。"
    )
