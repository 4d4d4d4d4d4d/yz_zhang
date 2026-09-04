"""OPS-011 内部定时任务鉴权：cron 端点必须携带共享密钥，杜绝公开裸调用。

这些 job 会改动资金与状态（自动放款/合约作废/任务下架/纠纷升级/评分结算等），
此前完全无鉴权——任何人都能触发。回归钉住：无 token / 错 token 一律 403。
"""
import pytest

from .conftest import JOB_HEADERS

JOB_ENDPOINTS = [
    "/api/v1/tasks/jobs/auto-accept",
    "/api/v1/tasks/jobs/expire-tasks",
    "/api/v1/tasks/jobs/settle-reviews",
    "/api/v1/tasks/jobs/deadline-alerts",
    "/api/v1/tasks/jobs/purge-locations",
    "/api/v1/contracts/jobs/expire-unsigned",
    "/api/v1/disputes/jobs/escalate-overdue",
]


@pytest.mark.parametrize("path", JOB_ENDPOINTS)
def test_job_endpoint_requires_token(client, path):
    # 无 token → 403
    r = client.post(path)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "invalid_job_token", path
    # 错 token → 403
    r = client.post(path, headers={"X-Job-Token": "wrong-token"})
    assert r.status_code == 403, path
    # 正确 token → 放行（200）
    r = client.post(path, headers=JOB_HEADERS)
    assert r.status_code == 200, f"{path}: {r.text}"


def test_regular_user_token_does_not_bypass(client, requester):
    from .conftest import auth

    # 登录用户但无 job token 也不行（job 鉴权与用户身份正交）
    r = client.post("/api/v1/tasks/jobs/auto-accept", headers=auth(requester))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "invalid_job_token"
