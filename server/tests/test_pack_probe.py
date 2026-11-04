"""PACK-091（396 号 spec）场景包问法离线试分工具。"""
import pytest

from scripts import pack_probe
from tests.test_pack_tag_only_questions import tag_only_questions


def _run(capsys, *items, key="roadside-jumpstart"):
    code = pack_probe.main([key, *items])
    return code, capsys.readouterr().out


def test_good_questions_pass(capsys):
    code, out = _run(capsys, "搭电怎么接线=>jumpstart-cable-order", "!冒烟=>jumpstart-cable-order", "!小备胎=>换完备胎")
    assert code == 0, out
    assert out.count("✓") == 3 and "只靠标签" in out and "第 1 条" in out


@pytest.mark.parametrize("item,why", [
    ("!烧了=>jumpstart-cable-order", "钉不住标签"),            # 正文里有「烧保险」，去掉标签也够得上
    ("!冒烟烧了=>jumpstart-cable-order", "要正好一个"),          # 一句里两个标签
    ("今天天气怎么样=>jumpstart-cable-order", "答不上"),
    ("快速路上要报警吗=>no-highway-call-police", "转介 110"),
    ("帮我报价成交=>上门费", "角色契约禁区"),
    ("不想活了=>上门费", "心理援助"),
    ("没有箭头", "问题=>知识 key"),
    ("搭电=>不存在的知识", "对不上"),
])
def test_each_kind_of_problem_is_named(capsys, item, why):
    code, out = _run(capsys, "搭电怎么接线=>jumpstart-cable-order", item)
    assert code == 1, out
    assert "✓ 搭电怎么接线" in out, "一项不行不影响别的项照常出结果"
    assert why in out, out


def test_old_packs_pick_the_assistant_that_owns_the_knowledge():
    """一个包几个助手的老包：不指定助手时，用管这条知识的那个。"""
    multi = [k for k in sorted(p.stem for p in pack_probe.psvc.SEEDS.glob("*.json"))
             if len(pack_probe.load(k).assistants) > 1]
    assert multi, "仓库里得有至少一个多助手的包，这条测试才有意义"
    d = pack_probe.load(multi[0])
    last = d.assistants[-1]
    k = next(x for x in d.knowledge if last.knowledge and x.key in last.knowledge and x.key not in d.assistants[0].knowledge)
    ok, note = pack_probe.probe(d, k.title, k.key, False)
    assert ok, note


def test_agrees_with_every_tag_only_question_already_in_the_tests():
    """存量的「只靠标签」问法都过了接口测试；试分工具对它们的判断必须一样，说明它没另写一份算分。"""
    rows = tag_only_questions()
    assert len(rows) >= 150
    bad = []
    for f, key, q, title in rows:
        d = pack_probe.load(key)
        k = next(x for x in d.knowledge if x.title == title)
        ok, note = pack_probe.probe(d, q, k.key, True)
        if not ok:
            bad.append(f"{f}：「{q}」{note}")
    assert not bad, "\n".join(bad)
