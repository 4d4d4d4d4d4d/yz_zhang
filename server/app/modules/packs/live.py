"""小店直播场景包的话术自查（209 号 spec 第 3 节，SCN-142）。

直播间、短视频里最容易踩线的不是商品，是**顺嘴说出来的那几个词**：「全网最低」「第一」「根治」、随手写的「原价」。
这里只做一件事：读用户自己贴进来的那段话术，按词表标出要看的词、为什么要看、出处是什么。
纯文本规则，不调模型、不读任何人的数据、不断定某句话一定违规——改不改由用户自己决定，拿不准的去问专业的人。
"""
from __future__ import annotations

import re

AD_LAW_9 = "《广告法》第九条第（三）项"
AD_LAW_17 = "《广告法》第十七条"
PRICE_RULE = "《明码标价和禁止价格欺诈规定》"

# （类别，认得出的写法，为什么要看，出处）。顺序就是给用户看的顺序：先绝对化用语，再功效，再价格
RULES: tuple[tuple[str, re.Pattern, str, str], ...] = (
    ("绝对化用语", re.compile(r"全网最低|史上最低|最低价|最便宜|最高级|最佳|最好|最强|最优|最低|第一|国家级|世界级|顶级|极品"
                          r"|唯一|独家|首选|绝无仅有|100%|百分之百"),
     "广告不得使用「国家级」「最高级」「最佳」这类用语，换成能说清楚、能证明的事实", AD_LAW_9),
    ("功效承诺", re.compile(r"根治|治愈|治疗|药到病除|包治|立刻见效|立即见效|一次见效|无副作用|抗癌|防癌|降血压|降血糖|消炎"),
     "除医疗、药品、医疗器械广告外，不得涉及疾病治疗功能、不得用医疗用语；食品、化妆品不说治病", AD_LAW_17),
    ("价格与限时", re.compile(r"原价|划线价|最后一天|最后\s*\d+\s*[单件个]|仅剩|限时|马上涨价|明天涨价"),
     "原价要有成交依据，限时、限量、涨价要真实，优惠条件写全", PRICE_RULE),
)


def script_check(text: str) -> dict:
    """返回 {hits: [{word, kind, why, source}]}：同一个词只报一次，按类别顺序。"""
    t = text or ""
    hits, seen = [], set()
    for kind, pat, why, source in RULES:
        for m in pat.finditer(t):
            w = m.group(0)
            if w in seen:
                continue
            seen.add(w)
            hits.append({"word": w, "kind": kind, "why": why, "source": source})
    return {"hits": hits}
