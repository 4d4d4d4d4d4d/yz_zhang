"""SCN-164（294 号 spec）跑腿代办里两类平台不能接的活：替人代开 / 代买处方药与精神类药品，倒卖号源与票证。

- 处方药凭处方、由医生面诊开具；安眠药等第二类精神药品只能患者本人面诊、凭处方限量购买。受托替人去医院
  代开、转交这类药，曾有跑腿与驿站人员被以贩卖毒品罪判刑。代买感冒药、退烧药这类非处方药不在此列。
- 加价倒卖医院号源、演出门票是倒卖票证，涉嫌违法；正常的代排队、代取号（不加价转卖）不在此列。

- SCN-177（303 号 spec）：给没有驾照的人陪练学车。没有驾驶证在道路上驾驶是无证驾驶；学车只能在驾校教练车上、
  由有资格的教练随车指导。已经拿到驾照、找人陪着练胆或实习期上高速（V329「陪驾」）不在此列；去驾校报名学车也不在此列。

- SCN-210（331 号 spec）：代写学位论文、代考。教育部《学位论文作假行为处理办法》把购买、出售、由他人代写、为他人
  代写学位论文都列为作假行为，组织或参与买卖、代写的个人与网站由主管机关查处；替考、代考扰乱考试秩序。
  文案、简历、公众号文章这类普通代写不在此列；论文的润色建议、查资料、讲解方法也不在此列。
- SCN-211（331 号 spec）：刷单、刷好评、写虚假评价。组织虚假交易、编造用户评价帮人做虚假宣传，违反《反不正当竞争法》
  《电子商务法》。真实用户写真实体验的内容合作（写明是合作）不在此列。

- SCN-218（335 号 spec）：刷粉刷量、买卖租借账号。网信办「清朗」系列专项行动持续打击流量造假、网络水军、
  批量账号与账号买卖，并要求「一人一号、一企两号」。做内容、投正规广告涨粉不在此列。

和 k12.py 一样：纯文本规则，只看词同时出现，不调模型；拿不准的由运营人工复核。
"""
from __future__ import annotations

import re

from app.core.errors import bad_request

_ACT = r"代开|代买|代购|代拿|代取|帮我开|帮我买|帮忙开|帮忙买|替我开|替我买"
_RX = (r"处方药|处方|安眠药|精神类?药|镇静药|阿普唑仑|艾司唑仑|佐匹克隆|唑吡坦|地西泮|劳拉西泮|曲马多|"
       r"右美沙芬|复方甘草片|可待因")
RX_DRUG = re.compile(rf"(?:{_ACT})[^。；\n]{{0,12}}(?:{_RX})")
TICKET = re.compile(r"号源|专家号|挂号|门诊号|门票|演唱会票|演出票|球票|火车票")
RESALE = re.compile(r"加价|倒卖|转卖|高价|溢价|囤号|囤票|炒票")
NO_LICENSE = re.compile(r"没有?驾照|无驾照|没有?驾驶证|无驾驶证|没(?:拿到|考到?|考过)驾照|还没(?:考|拿)?驾照|"
                        r"驾照(?:还)?没(?:考|拿到|下来|考下来)|无证驾驶|不用驾照|无证(?:学车|练车|开车)")
PRACTICE = re.compile(r"陪练|练车|学车|教我开|教开车|教我驾驶|陪我开|上路练|练手")
SCHOOL = re.compile(r"驾校|教练车")
SKIP_SCHOOL = re.compile(r"不(?:去|报|上|想去|想报|用去|用报)驾校|绕过驾校|比驾校便宜|代替驾校|不走驾校")
# SCN-210 代写学位论文、代考
GHOST = re.compile(r"(?:代写|代做|代笔|帮我写|替我写|枪手)[^。；\n]{0,8}(?:毕业论文|学位论文|硕士论文|博士论文|本科论文|毕业设计|毕设|论文)|"
                   r"(?:毕业论文|学位论文|硕士论文|博士论文|毕设|论文)[^。；\n]{0,6}(?:代写|代做|包过|包查重)|"
                   r"代考|替考|替我考|帮我考试|枪手考")
# SCN-211 刷单、刷好评、虚假评价
FAKE_REVIEW = re.compile(r"刷单|刷好评|刷评价|刷销量|刷五星|买好评|虚假好评|虚假评价|假好评|编好评|代写好评|写好评返现|好评返现")
# SCN-218 刷粉刷量、买卖租借账号
FAKE_TRAFFIC = re.compile(r"刷粉|买粉|涨粉套餐|僵尸粉|刷量|刷播放|刷阅读|刷点赞|刷关注|刷流量|"
                          r"(?:买|卖|收|租|借|收购|出租)[^。；，,\n]{0,8}?(?:账号|帐号)|(?:买|卖|租)号(?!码)")
# 命中词前面 6 个字以内有否定词、且中间没有句读断开的不算：「不代写学位论文」「不是代写，只要润色」
# 「不刷单」「不刷粉刷量」（顿号、并列不算断开）；「不想自己写，代写毕业论文」中间有逗号，照拦
_NEGATED = re.compile(r"(?:不|禁止|严禁|拒绝|非)[^。；;，,！!？?\n]{0,4}$")


def _affirmed(pattern: re.Pattern, text: str) -> bool:
    """有一处命中、且它前面 6 个字以内不是否定说法，才算。"""
    return any(not _NEGATED.search(text[max(0, m.start() - 6):m.start()]) for m in pattern.finditer(text))


def restricted_errand(text: str) -> str | None:
    t = text or ""
    if RX_DRUG.search(t):
        return "rx"
    if TICKET.search(t) and RESALE.search(t):
        return "resale"
    if NO_LICENSE.search(t) and PRACTICE.search(t) and (not SCHOOL.search(t) or SKIP_SCHOOL.search(t)):
        return "learner"
    if _affirmed(GHOST, t):
        return "ghostwrite"
    if _affirmed(FAKE_REVIEW, t):
        return "fake_review"
    if _affirmed(FAKE_TRAFFIC, t):
        return "fake_traffic"
    return None


def assert_no_restricted_errand(text: str) -> None:
    kind = restricted_errand(text)
    if kind == "rx":
        raise bad_request(
            "平台不承接替人代开、代买处方药或安眠药等精神类药品：这类药要患者本人面诊、凭处方购买，"
            "受托代开、转交可能触犯刑法。需要买药请本人就医或在有资质的药店、互联网医院凭处方购买；"
            "代买感冒药、退烧药这类非处方药可以照常发单。",
            "errand_restricted",
        )
    if kind == "resale":
        raise bad_request(
            "平台不承接加价倒卖号源、门票：倒卖医院号源、演出门票涉嫌违法。"
            "只是请人帮自己排队、取号、不转让给别人的，可以照常发单，写清是谁本人使用。",
            "errand_restricted",
        )
    if kind == "learner":
        raise bad_request(
            "平台不承接给没有驾照的人陪练学车：没有驾驶证在道路上开车属于无证驾驶，学车只能在驾校的教练车上、"
            "由有资格的教练随车指导。请先到驾校报名学车；已经拿到驾照、想找人陪着练胆或实习期上高速的，可以照常发「陪驾」单。",
            "unlicensed_driving_practice",
        )
    if kind == "ghostwrite":
        raise bad_request(
            "平台不承接代写学位论文、代考：购买或由他人代写学位论文是论文作假，参与代写的人也会被查处，替考扰乱考试秩序。"
            "论文的润色建议、查资料、讲解研究方法可以照常发单，写清是辅导而不是代写；文案、简历这类普通写作也可以。",
            "academic_ghostwriting",
        )
    if kind == "fake_review":
        raise bad_request(
            "平台不承接刷单、刷好评、编写虚假评价：组织虚假交易、编造评价属于虚假宣传，违反反不正当竞争法与电子商务法。"
            "想让更多人看到真实体验，可以发「探店」「试用」类的内容合作，写明是合作、按真实体验写。",
            "fake_review",
        )
    if kind == "fake_traffic":
        raise bad_request(
            "平台不承接刷粉刷量、买卖或租借账号：流量造假、网络水军与账号买卖是网信部门持续整治的对象，"
            "账号也可能被平台封禁。想涨粉可以发内容策划、拍摄剪辑、账号代运营（账号在你名下）的单。",
            "fake_traffic",
        )
