"""SCN-202 交付附授权清单（329 号 spec，V356）：执行方逐项登记用到的音乐、素材、字体、模板与授权来源。

剪辑、建站两个场景包都要求「交付附授权清单」，以前只能写在文字里，查不到、对不上。现在：
执行方在托管期间逐项登记、删掉登记错的；合约双方都看得到；放款以后清单就定了；合约以外的人看不到。
"""
from app.core.db import SessionLocal
from app.modules.contract.models import Contract
from tests.conftest import auth, register
from tests.test_batch_release import _three_stage

API = "/api/v1"


def test_executor_lists_licenses_and_both_parties_see_them(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_shape

    cid, _ = _three_stage(client, requester, worker)
    L = f"{API}/contracts/{cid}/licenses"
    assert client.get(L, headers=auth(requester)).json() == []
    r = client.post(L, json={"kind": "music", "title": " 《夏日》 ", "source": " 某曲库商用授权 ", "scope": "仅限抖音"},
                    headers=auth(worker))
    assert r.status_code == 201, r.text
    _assert_shape(r.json()[0], "ContractLicenseItem")
    assert [(x["kind"], x["title"], x["source"], x["scope"]) for x in r.json()] == [("music", "《夏日》", "某曲库商用授权", "仅限抖音")]
    client.post(L, json={"kind": "font", "title": "思源黑体", "source": "开源 OFL"}, headers=auth(worker))
    seen = client.get(L, headers=auth(requester)).json()
    assert [x["title"] for x in seen] == ["《夏日》", "思源黑体"] and seen[1]["scope"] == "", "发单人看得到"
    r = client.delete(f"{L}/{seen[0]['id']}", headers=auth(worker))
    assert r.status_code == 200 and [x["title"] for x in r.json()] == ["思源黑体"]


def test_only_the_executor_edits_only_while_funded_and_outsiders_see_nothing(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    L = f"{API}/contracts/{cid}/licenses"
    item = {"kind": "image", "title": "首页大图", "source": "客户提供"}
    r = client.post(L, json=item, headers=auth(requester))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_party", "发单人不能替执行方登记"
    for bad in ({**item, "kind": "song"}, {**item, "source": "x"}, {**item, "title": ""}, {**item, "extra": 1}):
        assert client.post(L, json=bad, headers=auth(worker)).status_code == 422, bad
    first = client.post(L, json=item, headers=auth(worker)).json()[0]
    assert client.delete(f"{L}/{first['id']}", headers=auth(requester)).status_code == 403, "发单人不能删"
    stranger = register(client, "13600003561", "路人")
    assert client.get(L, headers=auth(stranger)).status_code == 403, "合约以外的人看不到"
    other, _ = _three_stage(client, requester, worker)
    assert client.delete(f"{API}/contracts/{other}/licenses/{first['id']}", headers=auth(worker)).status_code == 404, "别的合约名下删不到"
    with SessionLocal() as db:
        c = db.get(Contract, cid)
        c.status = "released"
        db.commit()
    r = client.post(L, json=item, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_active", "放款以后清单就定了"
    assert client.delete(f"{L}/{first['id']}", headers=auth(worker)).status_code == 409
    assert len(client.get(L, headers=auth(requester)).json()) == 1, "放款后照样看得到"
