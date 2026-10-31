"""SCN-133 代看房回报做成结构化表单（211 号 spec，V239）。

发单模板可以带「要上门几次」「每次要做的事」：从模板发单时预填，接单人回报时照着逐项勾（V203 的上门回报）。
代看房模板带上现场看房清单的六项；格式与发布任务同一套限制。
"""
import copy

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_v219_packs import KEY, _load, _publish

API = "/api/v1"


def test_rental_template_carries_the_viewing_checklist_into_the_card(client, requester):
    _publish(client)
    card = client.get(f"{API}/packs/{KEY}", headers=auth(requester)).json()
    tpl = card["assets"]["task_templates"][0]
    assert tpl["visits_planned"] == 1 and len(tpl["visit_checklist"]) == 6
    assert "出租人身份与证件名字" in tpl["visit_checklist"] and "水电燃气表读数" in tpl["visit_checklist"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(tpl, "PackTaskTemplateBrief")


def test_checklist_rules_match_task_publishing():
    d = copy.deepcopy(_load())
    d["task_templates"][0]["visit_checklist"] = ["这一项写得太长了已经超过了二十个字的限制了吧"]
    assert schema.validate(d)[0] is None, "每项最多 20 字"
    d["task_templates"][0]["visit_checklist"] = [f"第{i}项" for i in range(9)]
    assert schema.validate(d)[0] is None, "最多 8 项"
    d["task_templates"][0]["visit_checklist"] = [" 门牌 "]
    ok, problems = schema.validate(d)
    assert ok is not None and not problems and ok.task_templates[0].visit_checklist == ["门牌"], "去掉前后空白"
