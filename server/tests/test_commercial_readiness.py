from types import SimpleNamespace
from app.core.config import settings
from scripts.commercial_readiness import report


def test_report_distinguishes_missing_implementation_from_missing_configuration(monkeypatch):
    from app.vendors.registry import _REGISTRY
    config = SimpleNamespace(**{k: getattr(settings, k) for k in dir(settings) if k.isupper()})
    monkeypatch.setitem(_REGISTRY, 'sms', {'mock': object})
    config.SMS_PROVIDER = 'mock'
    before = report(config)
    assert next(c for c in before['checks'] if c['code'] == 'provider_sms')['category'] == 'integration'
    monkeypatch.setitem(_REGISTRY, 'sms', {'mock': object, 'approved-adapter': object})
    installed = report(config)
    assert next(c for c in installed['checks'] if c['code'] == 'provider_sms')['category'] == 'configuration'
    config.SMS_PROVIDER = 'approved-adapter'
    selected = report(config)
    assert next(c for c in selected['checks'] if c['code'] == 'provider_sms')['passed'] is True
    assert selected['commercial_launch_approved'] is False


def test_report_does_not_leak_secrets_or_connection_strings():
    import json
    config = SimpleNamespace(**{k: getattr(settings, k) for k in dir(settings) if k.isupper()})
    config.JWT_SECRET = 'jwt-secret-' + 'x' * 40
    config.JOB_TOKEN = 'worker-secret-' + 'y' * 40
    config.DATABASE_URL = 'postgresql://sensitive_user:private_db_password@host/database'
    config.REDIS_URL = 'redis://:private_redis_password@host/0'
    encoded = json.dumps(report(config))
    for secret in (config.JWT_SECRET, config.JOB_TOKEN, config.DATABASE_URL, config.REDIS_URL, 'private_db_password'):
        assert secret not in encoded
    assert report(config)['commercial_launch_approved'] is False


def test_readiness_is_admin_only_and_returns_runtime_inventory(client, requester):
    from tests.conftest import auth
    from app.core.db import SessionLocal
    from app.modules.account.models import User
    assert client.get('/api/v1/admin/vendors').status_code == 403
    assert client.get('/api/v1/admin/vendors', headers=auth(requester)).status_code == 403
    with SessionLocal() as db:
        user = db.get(User, requester['id'])
        user.is_admin = True
        db.commit()
    response = client.get('/api/v1/admin/vendors', headers=auth(requester))
    assert response.status_code == 200
    data = response.json()['commercial_readiness']
    assert data['commercial_launch_approved'] is False
    assert data['checks_total'] == len(data['checks'])
    assert data['checks_passed'] == sum(c['passed'] for c in data['checks'])
