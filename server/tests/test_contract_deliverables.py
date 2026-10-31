"""SCN-166 交付文件托管在平台：原图放款完毕前锁着（297 号 spec，V324）。

活动跟拍最常见的两种纠纷——「先交片后不付」与「付了不交片」——都是因为成片在私下传。现在执行方把预览图和原图都传到
合约上：预览图发布方马上能看；原图只有执行方能取，合约放款完毕后发布方才能下载，匿名链接也随之失效。
"""
import base64

from tests.conftest import auth, register
from tests.test_batch_release import URL as RELEASE, _three_stage

API = "/api/v1"


def _upload(client, user, seed: bytes) -> str:
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + seed * 96).decode()
    r = client.post(f"{API}/files", json={"content_type": "image/png", "data_base64": png}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()["ref"]


def test_originals_stay_locked_until_the_contract_is_paid_out(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    D = f"{API}/contracts/{cid}/deliverables"
    pre, orig = _upload(client, worker, b"\x11"), _upload(client, worker, b"\x22")
    p = client.post(D, json={"ref": pre, "kind": "preview"}, headers=auth(worker))
    o = client.post(D, json={"ref": orig, "kind": "original"}, headers=auth(worker))
    assert p.status_code == 201 and o.status_code == 201, (p.text, o.text)
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(o.json(), "ContractDeliverable")
    rows = {r["kind"]: r for r in client.get(D, headers=auth(requester)).json()}
    assert rows["preview"]["locked"] is False and rows["preview"]["url"] == f"/api/v1/files/{pre}"
    assert rows["original"]["locked"] is True and rows["original"]["url"] is None, "发布方在放款前拿不到原图地址"
    oid = rows["original"]["id"]
    r = client.get(f"{D}/{oid}/file", headers=auth(requester))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "deliverable_locked" and "放款后" in r.json()["detail"]["message"]
    assert client.get(f"{API}/files/{orig}").status_code == 403, "原图的匿名能力链接失效"
    assert client.get(f"{API}/files/{pre}").status_code == 200, "预览图照旧能看"
    assert client.get(f"{D}/{oid}/file", headers=auth(worker)).status_code == 200, "执行方随时能取自己的原图"
    mine = {r["kind"]: r for r in client.get(D, headers=auth(worker)).json()}
    assert mine["original"]["locked"] is False

    for i in (1, 2, 3):
        assert client.post(f"{API}/contracts/{cid}/milestones/{i}/deliver", headers=auth(worker)).status_code == 200
    rel = client.post(RELEASE.format(cid=cid), json={"idxs": [1, 2, 3], "expected_total_cents": 90000}, headers=auth(requester))
    assert rel.status_code == 200 and rel.json()["status"] == "released"
    after = {r["kind"]: r for r in client.get(D, headers=auth(requester)).json()}
    assert after["original"]["locked"] is False and after["original"]["url"] == f"/api/v1/contracts/{cid}/deliverables/{oid}/file"
    got = client.get(f"{D}/{oid}/file", headers=auth(requester))
    assert got.status_code == 200 and got.content.startswith(b"\x89PNG") and got.headers["cache-control"] == "no-store, private"


def test_only_the_contractor_attaches_their_own_files_and_only_parties_see_them(client, requester, worker):
    cid, _ = _three_stage(client, requester, worker)
    D = f"{API}/contracts/{cid}/deliverables"
    mine = _upload(client, requester, b"\x33")
    r = client.post(D, json={"ref": mine, "kind": "preview"}, headers=auth(requester))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_party", "发布方不能往交付里挂文件"
    r = client.post(D, json={"ref": mine, "kind": "original"}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "deliverable_file_not_found", "不能挂别人传的图"
    outsider = register(client, "13800410001", "路人")
    assert client.get(D, headers=auth(outsider)).status_code == 403
    assert client.post(D, json={"ref": mine, "kind": "thumbnail"}, headers=auth(worker)).status_code == 422
