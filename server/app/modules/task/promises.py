"""SCN-185（311 号 spec）结果承诺：「保 offer」「包就业」「保过」「保录取」这一类。

录用、录取、考试与审批的结果由用人单位、学校、考试机构或主管部门决定，接单的人保证不了；「保 offer」套餐承诺落空后
退款扯皮的报道不少（310 号）。平台不拦（有人会写「不保 offer」，也有正当的「不通过退款」约定要人来判断），
只提示：发单时在说明体检里提醒，报名留言里写了的在发单人看到的报名列表上标出来。

纯文本规则，不调模型；前面 6 个字里有「不 / 没 / 无 / 非 / 拒绝 / 别」的不算（「不保 offer」「绝不承诺包过」）。
"""
from __future__ import annotations

import re

_PROMISE = re.compile(
    r"(?:保|包|保证|确保|承诺)\s*(?:拿到\s*)?(?:offer|录取|录用|就业|入职|过|拿证|上岸|通过|分配|中标)"
    r"|100\s*%\s*(?:录取|录用|通过|上岸|拿证)",
    re.I)
_NEGATION = re.compile(r"不|没|无|非|拒绝|别")

PROMISE_HINT = ("写了「保 offer / 包就业 / 保过」这类结果承诺：录用、录取、考试结果由用人单位、学校或考试机构决定，"
                "谁也保证不了。平台不支持结果承诺——请写清交付什么（改几版简历、练几次面试、讲几节课），按次托管、按次验收")
APPLICATION_FLAG = "这条报名承诺了结果（保 offer、包过之类）：录用、录取由对方机构决定，谁也保证不了，选人时多留个心"


def has_result_promise(text: str) -> bool:
    t = text or ""
    for m in _PROMISE.finditer(t):
        if not _NEGATION.search(t[max(0, m.start() - 6):m.start()]):
            return True
    return False
