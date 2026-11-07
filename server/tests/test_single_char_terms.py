"""SCN-109 检索：切完虚词剩下的单字不按整词计分（199 号 spec，V226）。

「报税 和 社保 的 事」去掉「的」之后剩「报税」「和」「社保」「事」：「和」「事」几乎哪条笔记里都有，
以前各按整词算 3 分，一条讲「和事佬」的闲聊能排到报税指南前面。现在：查询里还有多字词时单字只算 1 分；
只搜一个字（「税」）时照旧，个人知识库的短查询不受影响。个人知识库与服务包知识检索共用这一套。
"""
from app.modules.notebook.models import NbNote
from app.modules.notebook.service import score, terms


def _note(title, body):
    return NbNote(title=title, body=body, tags=[], url="")


def test_single_chars_count_one_point_when_the_query_has_real_words():
    ts = dict((t, w) for t, w, _ in terms("报税 和 社保 的 事"))
    assert ts == {"报税": 3, "和": 1, "社保": 3, "事": 1}


def test_unrelated_notes_full_of_common_characters_fall_behind():
    q = terms("报税 和 社保 的 事")
    guide = _note("个体户报税", "每季度报税前先对账")
    chat = _note("和事佬", "和他们说了这事，事情过去了")
    old = [(t, 3, g) for t, _, g in q]          # 以前：单字也按整词 3 分
    assert score(chat, old) > score(guide, old), "以前闲聊排在报税指南前面"
    assert score(guide, q) > score(chat, q), "现在报税指南在前"


def test_a_single_character_query_still_works():
    ts = terms("税")
    assert ts == [("税", 3, 0)], "只搜一个字时照旧按整词"
    assert score(_note("个税", "年度汇算"), ts) > 0


def test_latin_and_digits_are_unchanged():
    ts = dict((t, w) for t, w, _ in terms("PSD 和 源文件"))
    assert ts["psd"] == 3 and ts["源文件"] == 3 and ts["和"] == 1
