"""SCN-326 发单拦下伪造证件证明印章、做假流水、虚开买卖发票（437 号 spec，V464）。

第七十三轮场景发掘准备「签证材料准备」包时发现：「帮我做一份假的银行流水」「伪造在职证明」「办个假证」「虚开增值税专用发票」
一条都不拦。伪造、变造、买卖国家机关证件印章，伪造公司印章、身份证件（《刑法》第二百八十条），
虚开发票（第二百零五条、第二百零五条之一）都可能触犯刑法。
放行：识别、核验、举报假证假票；到税务机关代开发票；整理翻译真实材料；跑腿去银行打流水；证件照修图；
真的请假（「请假的诊断证明」「病假条」）；否定说法。误拦走 V363 的人工复核。
"""
import pytest

from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_multiday_slots import _post

API = "/api/v1"


@pytest.mark.parametrize("text,kind", [
    ("帮我办个假证", "forged_documents"), ("伪造在职证明", "forged_documents"),
    ("帮我做一份假的银行流水", "forged_documents"), ("代开假发票", "forged_documents"),
    ("帮我P一张假的收入证明", "forged_documents"), ("PS 一下身份证上的出生日期", "forged_documents"),
    ("做假学历", "forged_documents"), ("仿造毕业证", "forged_documents"), ("私刻一个公章", "forged_documents"),
    ("虚开增值税专用发票", "forged_documents"), ("收购发票", "forged_documents"), ("做假账应付税务", "forged_documents"),
    ("银行流水不够帮忙做假", "forged_documents"),        # 对象在前、动作在后
    ("收入证明帮我做高一点", "forged_documents"),
    # 放行：识别、核验、举报；代开发票；真实材料；跑腿；修图；真的请假；否定说法；和发票无关的「买」
    ("怎么识别假证", None), ("帮我核验发票真伪", None), ("教我辨别假发票", None), ("举报假证贩子", None),
    ("发票作假怎么举报", None), ("买到假证被骗了怎么办", None), ("假发票怎么识别", None),
    ("去税务局代开发票", None), ("签证材料整理和翻译，用真实材料", None), ("整理护照签证复印件", None),
    ("去银行帮我打印银行流水", None), ("帮我P一下证件照换底色", None), ("APP 里上传身份证", None),
    ("帮我去医院拿请假的诊断证明", None), ("病假条帮我送到学校", None), ("不做假流水，只整理", None),
    ("买东西要发票", None), ("流水线工人招聘", None), ("帮我把在职证明送到公司盖章", None),
    # 之前几轮的边界照旧
    ("定位老婆的手机", "covert_spying"), ("帮我把车的里程调回五万公里", "odometer_fraud"), ("本店不刷单", None),
])
def test_what_the_forgery_guard_catches(text, kind):
    assert restricted_errand(text) == kind


def test_publishing_stops_forgery_and_points_to_real_materials_and_review(client, requester):
    r = _post(client, requester, title="签证材料", description="帮我做一份假的银行流水，签证要用", category="跑腿")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "forged_documents", r.text
    msg = r.json()["detail"]["message"]
    assert "税务机关代开" in msg and "真实材料" in msg and "申请人工复核" in msg
    ok = _post(client, requester, title="签证材料", description="帮我整理签证材料、翻译户口本，用真实材料", category="跑腿")
    assert ok.status_code in (200, 201), ok.text
    rv = client.post(f"{API}/tasks/errand-reviews", json={"title": "签证材料", "description": "帮我做一份假的银行流水，签证要用",
                                                           "explanation": "写错了，是要去银行打印真实流水"}, headers=auth(requester))
    assert rv.status_code == 200 and rv.json()["kind_label"] == "伪造证件假流水假发票", rv.text


def test_every_pack_template_still_passes_the_guard():
    """161 个场景包模板里写着「证件」「发票」「签证」的不少（证件照、代开发票、报价单）：新规则一个都不误拦。"""
    import json

    from app.modules.packs.service import SEEDS

    hit = []
    for f in sorted(SEEDS.glob("*.json")):
        for t in json.loads(f.read_text(encoding="utf-8"))["task_templates"]:
            if restricted_errand(f"{t['title']} {t['description']}"):
                hit.append((f.stem, t["title"]))
    assert not hit, hit
