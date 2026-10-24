"""SCN-164（294 号 spec）跑腿代办里两类平台不能接的活：替人代开 / 代买处方药与精神类药品，倒卖号源与票证。

- 处方药凭处方、由医生面诊开具；安眠药等第二类精神药品只能患者本人面诊、凭处方限量购买。受托替人去医院
  代开、转交这类药，曾有跑腿与驿站人员被以贩卖毒品罪判刑。代买感冒药、退烧药这类非处方药不在此列。
- 加价倒卖医院号源、演出门票是倒卖票证，涉嫌违法；正常的代排队、代取号（不加价转卖）不在此列。

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


def restricted_errand(text: str) -> str | None:
    t = text or ""
    if RX_DRUG.search(t):
        return "rx"
    if TICKET.search(t) and RESALE.search(t):
        return "resale"
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
