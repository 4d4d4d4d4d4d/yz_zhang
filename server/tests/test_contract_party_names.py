"""SC-030 合约正文写出双方是谁（V140 真浏览器演示发现：写的是「用户1 / 用户2」）。"""
from tests.conftest import auth, topup


def test_contract_names_both_parties_with_masked_real_names(client, requester, worker):
    from app.core.db import SessionLocal
    from app.modules.account.models import User
    from tests.test_task_flow import match_and_fund, publish_task

    topup(client, requester, 40000)
    task = publish_task(client, requester)
    cid = match_and_fund(client, requester, worker, task)
    terms = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()["terms"]
    with SessionLocal() as db:
        r, w = db.get(User, requester["id"]), db.get(User, worker["id"])
        line = next(x for x in terms.splitlines() if x.startswith("发布方"))
        assert r.nickname in line and w.nickname in line
        assert f"平台账号 {r.id}" in line and f"平台账号 {w.id}" in line
        assert r.real_name[0] + "*" in line                 # 姓加星号，够核对
        assert r.real_name not in line or len(r.real_name) == 1   # 全名不摊给对方
        assert "用户" + str(r.id) + " /" not in line
