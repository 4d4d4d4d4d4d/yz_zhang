"""PACK-094（432 号 spec，V459）场景包变异工具：从测试文件推出变异、改坏后一定改回。

第五十四轮起每批 spec 写「scratchpad/mutXXX.py 共 N 处，全红」，那些脚本换个容器就没了。
scripts/pack_mutate.py 进了仓库；这里钉住两件事：推导出来的变异够全（三类都有），以及改坏之后无论红不红都改回原文。
"""
from pathlib import Path

import pytest

from scripts import pack_mutate as pm

TESTS = Path(__file__).parent


def test_derives_all_three_kinds_from_a_pack_test():
    muts = pm.derive(TESTS / "test_v458_packs.py")
    kinds = [m.kind for m in muts]
    assert kinds.count("forbidden") == 10 and kinds.count("tag") == 8 and kinds.count("category") == 2
    tag = next(m for m in muts if m.kind == "tag")
    assert tag.select == "phones10" and "随时连进来" in tag.old       # 按参数下标选到那一行
    cat = next(m for m in muts if m.kind == "category")
    assert cat.new.endswith('"required_cert": "x"}') and cat.select == ""


def test_a_category_that_already_needs_a_cert_is_mutated_by_dropping_it():
    """V459 首轮清点：给「空调加氟维修」「高空外窗外墙清洗」往前插 `"required_cert": "x"`，被后写的原资质覆盖，
    两处都没变红——是工具自己的等价变异，不是测试漏了。已有必选资质的改成去掉它。"""
    cat = next(m for m in pm.derive(TESTS / "test_v442_packs.py") if m.kind == "category" and "高空" in m.label)
    assert "required_cert" in cat.old and "required_cert" not in cat.new and "去掉" in cat.label


def test_every_recent_pack_test_can_be_mutated():
    files = sorted(TESTS.glob("test_v4[2-9]*_packs.py"))
    assert len(files) >= 20
    for f in files:
        muts = pm.derive(f)
        kinds = [m.kind for m in muts]
        assert kinds.count("tag") == 8 and kinds.count("forbidden") >= 8 and kinds.count("category") >= 1, (f.name, kinds)


def test_ambiguous_items_are_refused_not_guessed():
    with pytest.raises(LookupError):
        pm._remove_list_item('["甲", "甲"]', "甲")
    assert pm._remove_list_item('["甲", "乙"]', "甲") == ('"甲", ', "")


def test_run_one_reports_red_and_always_restores(tmp_path):
    data = tmp_path / "seed.txt"
    data.write_text("keep me", encoding="utf-8")
    probe = tmp_path / "test_probe_mutate.py"
    probe.write_text(f"def test_it():\n    assert open(r'{data}', encoding='utf-8').read() == 'keep me'\n", encoding="utf-8")
    killed = pm.Mutation("tag", data, "keep", "drop", "", "自检")
    assert pm.run_one(killed, probe) is True                  # 改坏了，测试红
    assert data.read_text(encoding="utf-8") == "keep me"      # 并且改回来了
    survives = pm.Mutation("tag", data, "me", "me", "", "等价变异")
    assert pm.run_one(survives, probe) is False
    assert data.read_text(encoding="utf-8") == "keep me"
