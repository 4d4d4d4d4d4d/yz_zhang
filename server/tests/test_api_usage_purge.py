"""API-055 Key 用量记录的保留期清理（219 号 spec，V247）。

用量页最多看 90 天，而每把 Key 每天一行的用量记录以前永远留着。现在每天清一次 90 天以前的。
"""
from datetime import datetime, timedelta

from app.core.db import SessionLocal
from app.modules.openapi.models import ApiKeyUsage
from app.modules.openapi.usage import day_of, purge_usage
from tests.conftest import JOB_HEADERS


def test_rows_older_than_90_days_are_purged_recent_ones_stay(client):
    now = datetime(2030, 6, 1, 4, 0)
    with SessionLocal() as db:
        for d in (0, 1, 89, 90, 91, 200):
            db.add(ApiKeyUsage(key_id=7, day=day_of(now - timedelta(days=d)), count=1, rejected=0))
        db.commit()
        out = purge_usage(db, now)
        db.commit()
        left = sorted(r.day for r in db.query(ApiKeyUsage).filter(ApiKeyUsage.key_id == 7))
    assert out == {"purged": 2, "kept_from": day_of(now - timedelta(days=90))}
    assert left == sorted(day_of(now - timedelta(days=d)) for d in (0, 1, 89, 90)), "90 天以内（含第 90 天）都留着"


def test_the_job_endpoint_runs_and_needs_the_job_token(client):
    r = client.post("/api/v1/openapi/jobs/purge-usage", headers=JOB_HEADERS)
    assert r.status_code == 200 and set(r.json()) == {"purged", "kept_from"}
    assert client.post("/api/v1/openapi/jobs/purge-usage").status_code in (401, 403)
