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
    assert {"spec-batch", "vision-sync", "regression", "live-demo"} <= {p.name for p in harness.SKILLS.iterdir()}


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
