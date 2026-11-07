"""SCN-143（213 号 spec）不承接中小学学科类有偿家教。

国家对学科类校外培训有严格管控：以「家政服务」「住家教师」「众筹私教」等名义变相开展的，教育部要求依法查处
（教监管厅函〔2021〕8号）。一个众包平台上「给孩子补数学」正好落在这里，所以发布时直接拒绝，并说清为什么、能走什么路。

规则只看三样同时出现：辅导类的词 + 学科 + 中小学或孩子的说法。钢琴、游泳这类非学科陪练，成人学英语、
大学生的专业课辅导，都不会被拦（缺其中一样）。纯文本规则，不调模型；拿不准的由运营人工复核。
"""
from __future__ import annotations

import re

from app.core.errors import bad_request

SUBJECTS = r"语文|数学|英语|物理|化学|生物|历史|地理|政治|道德与法治|奥数|作文"
TUTORING = re.compile(rf"家教|补课|补习|培优|辅导|补(?:{SUBJECTS})")
SUBJECT = re.compile(SUBJECTS)
SCHOOL_CHILD = re.compile(r"小学|初中|高中|初[一二三]|高[一二三]|[一二三四五六七八九]年级|小升初|中考|孩子|儿子|女儿")


def is_k12_subject_tutoring(text: str) -> bool:
    t = text or ""
    return bool(TUTORING.search(t) and SUBJECT.search(t) and SCHOOL_CHILD.search(t))


def assert_no_k12_tutoring(text: str) -> None:
    if is_k12_subject_tutoring(text):
        raise bad_request(
            "平台不承接中小学学科类有偿家教：国家对学科类校外培训有严格管控，以家政、私教等名义变相开展的都在查处之列。"
            "需要学科辅导的，请找有办学资质的培训机构；钢琴、游泳、运动这类非学科陪练可以照常发单。",
            "k12_subject_tutoring",
        )
