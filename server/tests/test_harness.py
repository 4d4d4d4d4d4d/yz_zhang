"""HARNESS 工程 harness 自身的闸门（根目录 CLAUDE.md，121 号 spec，skill spec-batch）。

用户要求：「在工程里建立一些基本的 harness skill 和 spec 文档库……合入代码实现能够跟 spec 对应……
最好能够通过 harness 和 skill 自动做 spec 和文档的迭代。」这里钉住：spec 都进索引、新 spec 有状态行、
待办格式与引用都对、skills 都有 frontmatter、CLAUDE.md 在；并对检查器自己做红验。
"""
import shutil

import pytest

from scripts import harness


def test_the_repo_passes_its_own_harness_check():
    problems = harness.check()
    assert not problems, "harness 检查不过：\n  " + "\n  ".join(problems)


def test_the_scanner_actually_sees_the_specs_backlog_and_skills():
    assert len(harness.spec_files()) >= 120
    rows = harness.backlog_rows()
    assert any(r["status"] == "todo" for r in rows) and any(r["status"] == "done" for r in rows)
    assert {"spec-batch", "vision-sync", "regression", "live-demo", "iterate"} <= {p.name for p in harness.SKILLS.iterdir()}


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """把 harness 指向一份临时副本，红验时不碰仓库里的真文件。"""
    specs = tmp_path / "specs"
    shutil.copytree(harness.SPECS, specs)
    shutil.copy(harness.BACKLOG, tmp_path / "BACKLOG.md")
    shutil.copytree(harness.SKILLS, tmp_path / "skills")
    shutil.copy(harness.CLAUDE, tmp_path / "CLAUDE.md")
    monkeypatch.setattr(harness, "SPECS", specs)
    monkeypatch.setattr(harness, "INDEX", specs / "README.md")
    monkeypatch.setattr(harness, "BACKLOG", tmp_path / "BACKLOG.md")
    monkeypatch.setattr(harness, "SKILLS", tmp_path / "skills")
    monkeypatch.setattr(harness, "CLAUDE", tmp_path / "CLAUDE.md")
    assert harness.check() == []
    return tmp_path


def test_red_an_unindexed_spec_is_caught(sandbox):
    (sandbox / "specs" / "999-orphan.md").write_text("\n# 999 孤儿\n\n> 状态：设计（V999）。\n", encoding="utf-8")
    assert any("999-orphan.md" in p and "索引" in p for p in harness.check())


def test_red_a_new_spec_without_status_line_is_caught(sandbox):
    p = sandbox / "specs" / "998-nostatus.md"
    p.write_text("\n# 998 没有状态\n", encoding="utf-8")
    idx = sandbox / "specs" / "README.md"
    idx.write_text(idx.read_text(encoding="utf-8") + "\n| 998 | x | [998-nostatus.md](./998-nostatus.md) | P0 |\n", encoding="utf-8")
    assert any("状态" in x and "998-nostatus.md" in x for x in harness.check())


def test_red_backlog_problems_are_caught(sandbox):
    b = sandbox / "BACKLOG.md"
    b.write_text(b.read_text(encoding="utf-8")
                 + "| V990 | 引用了不存在的 spec | 997 | todo | x |\n| V991 | 状态写错 | — | 进行中 | x |\n"
                 + "| — | 没排批次却是待办 | — | todo | x |\n", encoding="utf-8")
    probs = "\n".join(harness.check())
    assert "997" in probs and "进行中" in probs and "没排批次" in probs


def test_red_done_batch_whose_spec_is_still_a_design_is_caught(sandbox):
    (sandbox / "specs" / "996-design.md").write_text("\n# 996 x\n\n> 状态：设计（V996）。\n", encoding="utf-8")
    idx = sandbox / "specs" / "README.md"
    idx.write_text(idx.read_text(encoding="utf-8") + "\n| 996 | x | [996-design.md](./996-design.md) | P0 |\n", encoding="utf-8")
    b = sandbox / "BACKLOG.md"
    b.write_text(b.read_text(encoding="utf-8") + "| V996 | 声称做完 | 996 | done | x |\n", encoding="utf-8")
    assert any("996-design.md" in p and "done" in p for p in harness.check())


def test_red_a_skill_without_frontmatter_is_caught(sandbox):
    d = sandbox / "skills" / "broken"
    d.mkdir()
    (d / "SKILL.md").write_text("# 没有 frontmatter\n", encoding="utf-8")
    assert any("broken" in p for p in harness.check())


def test_new_spec_scaffolds_the_next_number_and_indexes_it(sandbox):
    top = max(harness.spec_number(p) for p in harness.spec_files())
    path = harness.new_spec("测试用的新篇", "V999", "TST-001~002", slug="harness-selftest")
    assert path.name == f"{top + 1}-harness-selftest.md"
    text = path.read_text(encoding="utf-8")
    assert "> 状态：设计（V999）。编号 TST-001~002。" in text and "## 6. 闸门与红验" in text
    assert f"](./{path.name})" in (sandbox / "specs" / "README.md").read_text(encoding="utf-8")
    assert harness.check() == []


# ---------- ITER-001 迭代范式（skill iterate，用户 2026-10-14）：打钩、更新 spec、没做的要有去处 ----------
def _add_spec(sandbox, num, body):
    (sandbox / "specs" / f"{num}-x.md").write_text(body, encoding="utf-8")
    idx = sandbox / "specs" / "README.md"
    idx.write_text(idx.read_text(encoding="utf-8") + f"\n| {num} | x | [{num}-x.md](./{num}-x.md) | P0 |\n", encoding="utf-8")


def _add_row(sandbox, row):
    b = sandbox / "BACKLOG.md"
    b.write_text(b.read_text(encoding="utf-8") + row + "\n", encoding="utf-8")


def test_red_implemented_spec_whose_batch_is_not_ticked_is_caught(sandbox):
    _add_spec(sandbox, 995, "\n# 995 x\n\n> 状态：本批实现（V995）。\n\n## 7. 没做的\n\n- 无\n")
    _add_row(sandbox, "| V995 | 做完了没打钩 | 995 | todo | x |")
    assert any("V995" in p and "打钩" in p for p in harness.check())


def test_red_done_batch_without_open_items_section_is_caught(sandbox):
    _add_spec(sandbox, 994, "\n# 994 x\n\n> 状态：本批实现（V994）。\n\n## 6. 闸门\n")
    _add_row(sandbox, "| V994 | 做完了 | 994 | done | x |")
    assert any("994-x.md" in p and "没做的" in p for p in harness.check())


def test_red_open_item_without_a_home_is_caught(sandbox):
    _add_spec(sandbox, 993, "\n# 993 x\n\n> 状态：本批实现（V993）。\n\n## 7. 没做的\n\n- **ZZQ-110** 还欠一件事\n")
    _add_row(sandbox, "| V993 | 做完了 | 993 | done | x |")
    assert any("ZZQ-110" in p and "去处" in p for p in harness.check())
    _add_row(sandbox, "| V9931 | ZZQ-110 排进来了 | — | todo | x |")
    assert not any("ZZQ-110" in p for p in harness.check())


def test_closeout_lists_what_is_still_unticked():
    items = dict((text, ok) for ok, text in harness.closeout("V152"))
    assert all(items.values()), items
    missing = harness.closeout("V9999")
    assert not missing[0][0] and any(text.startswith("下一批") for _, text in missing)


def test_red_closeout_vision_row_for_ui_and_no_ui_batches(sandbox, monkeypatch):
    """141 号收尾补的规则：有界面的批次要「两端已接」；spec 第 4 节写明不涉及界面的（安全、运维），带批次号即可。"""
    vision = sandbox / "VISION.md"
    vision.write_text("| V-1 | 甲 | — | 部分 | V9981 安全加固 |\n| V-2 | 乙 | — | 部分 | V9982 只有网页 |\n", encoding="utf-8")
    monkeypatch.setattr(harness, "VISION", vision)
    key = "VISION 对照行写「两端已接」并带批次号（spec 第 4 节写明不涉及界面的，带批次号即可）"
    _add_spec(sandbox, 9981, "\n# 9981 x\n\n> 状态：本批实现（V9981）。\n\n## 4. 两端\n\n无界面。\n\n## 7. 没做的\n\n- 无\n")
    _add_row(sandbox, "| V9981 | 安全 | 9981 | done | x |")
    assert dict((t, ok) for ok, t in harness.closeout("V9981"))[key] is True
    _add_spec(sandbox, 9982, "\n# 9982 x\n\n> 状态：本批实现（V9982）。\n\n## 4. 两端\n\n- Web：一个新页面\n\n## 7. 没做的\n\n- 无\n")
    _add_row(sandbox, "| V9982 | 有界面 | 9982 | done | x |")
    assert dict((t, ok) for ok, t in harness.closeout("V9982"))[key] is False, "有界面却只写了「部分」，不能算收尾"


def test_red_a_ledger_id_used_twice_in_the_same_section_is_caught(sandbox):
    """DOC-020（V215）同一段两行同号是撞号；详情段与逐条索引各一行是有意的，不报。"""
    ledger = sandbox / "specs" / harness.LEDGER_NAME
    text = ledger.read_text(encoding="utf-8")
    assert "| CONC-062 |" in text and text.count("| CONC-062 |") == 2, "详情段与逐条索引各一行：不算撞号"
    ledger.write_text(text.replace("| PAY-047 |", "| PAY-044 |"), encoding="utf-8")
    problems = harness.check()
    assert any("PAY-044" in p and "撞号" in p and "逐条索引" in p for p in problems), problems
