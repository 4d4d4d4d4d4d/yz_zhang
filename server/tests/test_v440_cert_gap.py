"""SCN-294e（413 号 spec，V440）推荐里因为没证被排除了几个人、其中几个只差发单人加选的某一张。

408 号做了「要资质的单只推荐持证的人」，但发单人看不见被挡掉了多少：
推荐一个都没有时，他不知道是没人、还是自己加选的证把人全挡了。只给人数，不给是谁。
"""
from app.modules.task.service import ELECTRICIAN_CERT, HEIGHT_WORK_CERT, REFRIGERATION_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v435_recommend_certs import _approve, _recs

API = "/api/v1"


def _gap(client, who, tid):
    return client.get(f"{API}/tasks/{tid}/recommendations/cert-gap", headers=auth(who))


def test_gap_counts_excluded_and_who_only_misses_an_added_cert(client, requester):
    ops = make_admin(client, "13600044001", "审核")
    both = make_verified(client, "13600044002")
    height = make_verified(client, "13600044003")
    elec = make_verified(client, "13600044004")
    make_verified(client, "13600044005")
    for w, names in ((both, [HEIGHT_WORK_CERT, ELECTRICIAN_CERT]), (height, [HEIGHT_WORK_CERT]), (elec, [ELECTRICIAN_CERT])):
        for n in names:
            _approve(client, ops, w, n)
    t = _post(client, requester, title="展台背板 3 米高还要接灯", description="要上梯子接电", category="展台搭建",
              task_certs=[HEIGHT_WORK_CERT, ELECTRICIAN_CERT]).json()
    r = _gap(client, requester, t["id"])
    assert r.status_code == 200, r.text
    g = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(g, "RecommendationCertGap")   # SDK 声明的字段与真实响应一致
    assert g["required"] == [HEIGHT_WORK_CERT, ELECTRICIAN_CERT] and g["task_certs"] == [HEIGHT_WORK_CERT, ELECTRICIAN_CERT]
    assert g["eligible"] == 1 and g["excluded"] == g["pool"] - 1 and g["excluded"] >= 3
    # 只差高处作业证的是只有电工证的那位，反之亦然；两张都没有的不算「只差一张」
    assert g["only_missing"] == [{"cert": HEIGHT_WORK_CERT, "count": 1}, {"cert": ELECTRICIAN_CERT, "count": 1}]
    # 与推荐同一个候选池：推荐里正好是那一位
    assert set(_recs(client, requester, t["id"])) == {both["id"]}


def test_no_cert_needed_nothing_excluded(client, requester):
    make_verified(client, "13600044006")
    t = _post(client, requester, title="展位布置", description="只摆展品", category="展台搭建").json()
    g = _gap(client, requester, t["id"]).json()
    assert g["required"] == [] and g["excluded"] == 0 and g["only_missing"] == [] and g["eligible"] == g["pool"] >= 1


def test_category_required_cert_is_not_offered_as_relaxable(client, requester):
    make_verified(client, "13600044007")
    t = _post(client, requester, title="空调不制冷", description="挂机", category="空调加氟维修").json()
    g = _gap(client, requester, t["id"]).json()
    assert g["required"] == [REFRIGERATION_CERT] and g["task_certs"] == []
    assert g["excluded"] >= 1 and g["only_missing"] == []


def test_only_the_publisher_sees_the_gap(client, requester):
    other = make_verified(client, "13600044008")
    t = _post(client, requester, title="展台背板", description="3 米", category="展台搭建", task_certs=[HEIGHT_WORK_CERT]).json()
    assert _gap(client, other, t["id"]).status_code == 403
    assert _gap(client, requester, 999999).status_code == 404


def test_blocked_people_are_not_counted(client, requester):
    a = make_verified(client, "13600044009")
    t = _post(client, requester, title="展台背板", description="3 米", category="展台搭建", task_certs=[HEIGHT_WORK_CERT]).json()
    before = _gap(client, requester, t["id"]).json()["pool"]
    assert client.post(f"{API}/users/{a['id']}/block", headers=auth(requester)).status_code in (200, 201)
    after = _gap(client, requester, t["id"]).json()
    assert after["pool"] == before - 1 and after["excluded"] == after["pool"] - after["eligible"]
