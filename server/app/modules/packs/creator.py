"""创作者场景包的需求单体检（137 号 spec，SCN-101）。

自由设计、文案、剪辑最常见的扯皮不是手艺，是**需求单里没写的那几项**：用在哪、多大、交什么格式、
哪天要、改几稿、版权给到哪一步。没写的那一项，到交付时就变成「再改一版」或「这个不能商用吗」。

这里只做一件事：读用户自己贴进来的那段文字，按九项清单看哪几项没写，给出该追问甲方的话。
纯文本规则，不调模型、不读任何人的数据、不替谁回话——草稿由用户自己决定发不发。
"""
from __future__ import annotations

import re

# （项，认得出的写法，没写时该追问的话）。顺序就是追问的顺序：先定做什么，再定怎么交、怎么算钱
ITEMS: tuple[tuple[str, re.Pattern, str], ...] = (
    ("用途", re.compile(r"用途|用在|用于|场景|投放|印刷|线上|线下|海报|包装|门头|朋友圈|公众号|抖音|小红书|官网|展会"),
     "这个东西用在哪儿（印刷、线上投放还是门店）？"),
    ("数量", re.compile(r"\d+\s*(张|款|个|套|条|篇|页|支|版)|几张|几款|一套|一组|数量"),
     "一共要几样（几张、几款、几条）？"),
    ("尺寸规格", re.compile(r"尺寸|规格|像素|分辨率|比例|\d+\s*(px|mm|cm|毫米|厘米)|\d+\s*[x×*]\s*\d+|A[345]\b|横版|竖版|时长|\d+\s*秒"),
     "尺寸或规格是多少（像素、毫米、比例、时长）？"),
    ("文件格式", re.compile(r"格式|源文件|分层|PSD|AI\s*文件|PDF|PNG|JPG|SVG|MP4|MOV|Word|PPT", re.I),
     "要交什么格式，要不要源文件？"),
    ("交期", re.compile(r"截止|交付|交稿|之前|以前|天内|周内|号前|月底|周[一二三四五六日天]|deadline|\d+\s*月\s*\d+\s*[日号]", re.I),
     "哪天要初稿、哪天要定稿？"),
    ("改稿次数", re.compile(r"修改|改稿|改\s*\d+\s*次|几稿|\d+\s*稿|轮"),
     "包含几次修改？超出的怎么算（建议走变更单）？"),
    ("版权授权", re.compile(r"版权|授权|商用|著作权|买断|署名|独家"),
     "版权怎么约定：买断、独家授权还是只授权这一次使用？能不能放进我的作品集？"),
    ("参考", re.compile(r"参考|样例|案例|风格|喜欢|类似|竞品|调性"),
     "有没有喜欢或不喜欢的参考？"),
    ("预算", re.compile(r"预算|报价|费用|价格|\d+\s*(元|块|万)|¥|￥"),
     "预算大概多少，是否分期付？"),
)


def brief_check(text: str) -> dict:
    """返回 {present, missing, questions, score}；score 是写到的项数 / 9。"""
    t = text or ""
    present, missing, questions = [], [], []
    for name, pat, ask in ITEMS:
        if pat.search(t):
            present.append(name)
        else:
            missing.append(name)
            questions.append(ask)
    return {"present": present, "missing": missing, "questions": questions,
            "score": round(len(present) / len(ITEMS), 2)}
