"""AGT-098 方法的版本历史（244 号 spec，V271）。

239 号让人看得出「改了之后变差了」，但看不到改了哪一步、也退不回去。现在改步骤之前把旧步骤存一份：
能看每一版的步骤、能退回某一版（退回本身也算一次修改，历史不丢）。
"""
from app.core.db import SessionLocal
from app.modules.notebook.models import NbMethodVersion
from tests.conftest import auth, register
from tests.test_method_stats import STEPS, _method

URL = "/api/v1/notebook/methods"
V2 = [{"title": "先列清单", "note": ""}] + STEPS


def test_history_keeps_old_steps_and_restore_is_itself_a_new_version(client, requester):
    m = _method(client, requester)
    h = client.get(f"{URL}/{m['id']}/versions", headers=auth(requester)).json()
    assert h == {"method_id": m["id"], "current": {"version": 1, "steps": STEPS}, "versions": [], "max_kept": 20}
    client.patch(f"{URL}/{m['id']}", json={"name": "改个名"}, headers=auth(requester))
    assert client.get(f"{URL}/{m['id']}/versions", headers=auth(requester)).json()["versions"] == [], "改名不存旧版"
    client.patch(f"{URL}/{m['id']}", json={"steps": V2}, headers=auth(requester))
    client.patch(f"{URL}/{m['id']}", json={"steps": V2[:1]}, headers=auth(requester))
    h = client.get(f"{URL}/{m['id']}/versions", headers=auth(requester)).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(h, "NbMethodHistory")
    assert h["current"] == {"version": 3, "steps": V2[:1]}
    assert [(v["version"], v["steps"]) for v in h["versions"]] == [(2, V2), (1, STEPS)], "旧版按版本号倒序"
    r = client.post(f"{URL}/{m['id']}/versions/1/restore", headers=auth(requester))
    assert r.status_code == 200 and r.json()["version"] == 4 and r.json()["steps"] == STEPS
    _assert_shape(r.json(), "NbMethod")
    h = client.get(f"{URL}/{m['id']}/versions", headers=auth(requester)).json()
    assert [v["version"] for v in h["versions"]] == [3, 2, 1], "退回也算一次修改：第 3 版存下来，历史不丢"
    same = client.post(f"{URL}/{m['id']}/versions/1/restore", headers=auth(requester))
    assert same.status_code == 409 and same.json()["detail"]["code"] == "nb_method_version_same"
    missing = client.post(f"{URL}/{m['id']}/versions/9/restore", headers=auth(requester))
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "nb_method_version_not_found"
    exp = client.get("/api/v1/users/me/export", headers=auth(requester)).json()["notebook"]["methods"]
    assert [v["version"] for v in exp[0]["old_versions"]] == [1, 2, 3]


def test_history_is_private_and_goes_away_with_the_method(client, requester):
    m = _method(client, requester)
    client.patch(f"{URL}/{m['id']}", json={"steps": V2}, headers=auth(requester))
    other = register(client, "13800344001", "别人")
    assert client.get(f"{URL}/{m['id']}/versions", headers=auth(other)).status_code == 404
    assert client.post(f"{URL}/{m['id']}/versions/1/restore", headers=auth(other)).status_code == 404
    plain = _method(client, requester, "没改过的")
    exp = client.get("/api/v1/users/me/export", headers=auth(requester)).json()["notebook"]["methods"]
    assert "old_versions" not in [x for x in exp if x["name"] == "没改过的"][0], "没改过步骤的导出与以前一样"
    assert plain["version"] == 1
    client.delete(f"{URL}/{m['id']}", headers=auth(requester))
    with SessionLocal() as db:
        assert db.query(NbMethodVersion).filter(NbMethodVersion.method_id == m["id"]).count() == 0, "删方法连旧版一起删"


def test_agt099_only_the_latest_old_versions_are_kept(client, requester, monkeypatch):
    """AGT-099（253 号 spec）历史只留最近若干个旧版；更早的删掉，版本号照旧递增、不复用。"""
    from app.modules.notebook import router as nb

    monkeypatch.setattr(nb, "METHOD_HISTORY_KEEP", 3)
    m = _method(client, requester)
    for i in range(5):
        client.patch(f"{URL}/{m['id']}", json={"steps": [{"title": f"第 {i} 种做法", "note": ""}]}, headers=auth(requester))
    h = client.get(f"{URL}/{m['id']}/versions", headers=auth(requester)).json()
    assert h["current"]["version"] == 6 and h["max_kept"] == 3
    assert [v["version"] for v in h["versions"]] == [5, 4, 3], "只留最近 3 个旧版"
    with SessionLocal() as db:
        assert db.query(NbMethodVersion).filter(NbMethodVersion.method_id == m["id"]).count() == 3
    other = _method(client, requester, "另一个方法")
    client.patch(f"{URL}/{other['id']}", json={"steps": V2}, headers=auth(requester))
    with SessionLocal() as db:
        assert db.query(NbMethodVersion).filter(NbMethodVersion.method_id == m["id"]).count() == 3, "清理只按同一个方法算"
        assert db.query(NbMethodVersion).filter(NbMethodVersion.method_id == other["id"]).count() == 1, "别的方法的旧版不被挤掉"
    assert client.post(f"{URL}/{m['id']}/versions/2/restore", headers=auth(requester)).status_code == 404, "清理掉的版本退不回去"
