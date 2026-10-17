"""Non-secret technical readiness inventory; never an approval to launch."""
from app.core.config import settings
from app.vendors.registry import (
    P0_KINDS, _REGISTRY, NON_PRODUCTION_NAMES, provider_grade,
)
from app.vendors.signature import _REGISTRY as signature_registry
from app.vendors.notary import _REGISTRY as notary_registry


def report(config=settings):
    checks = []
    def add(code, passed, detail, category='configuration'):
        checks.append({'code': code, 'passed': bool(passed), 'category': category, 'detail': detail})
    add('production_environment', config.ENV == 'prod', 'Actual process must run the strict production profile')
    add('postgres', config.DATABASE_URL.startswith(('postgresql:', 'postgresql+')), 'Business database is PostgreSQL')
    add('redis', bool(config.REDIS_URL), 'Shared rate limit/worker coordination configured; reachability requires runtime probe')
    add('jwt_secret', len(config.JWT_SECRET) >= 32 and config.JWT_SECRET != 'dev-secret-change-me', 'JWT secret is non-default and at least 32 characters')
    add('job_secret', len(config.JOB_TOKEN) >= 32 and config.JOB_TOKEN != 'dev-job-token-change-me', 'Worker secret is non-default and at least 32 characters')
    add('cors', bool(config.CORS_ORIGINS.strip()) and config.CORS_ORIGINS.strip() != '*', 'CORS restricted; production origins still require review')
    add('api_docs', not config.EXPOSE_DOCS, 'Public API documentation disabled')
    add('proxy_hops', config.TRUSTED_PROXY_HOPS == 1, 'Proxy trust matches the current one-proxy deployment')
    vendors = []
    for kind in P0_KINDS:
        name = getattr(config, f'{kind.upper()}_PROVIDER')
        available = sorted(n for n in _REGISTRY[kind] if n not in NON_PRODUCTION_NAMES[kind])
        grade = provider_grade(kind, name)
        vendors.append({'kind': kind, 'configured_grade': grade, 'registered_non_mock_implementations': available})
        add('provider_' + kind, grade == 'production', 'Non-mock registered provider selected; real acceptance still required',
            'integration' if not available else 'configuration')
    add('custody', config.LEDGER_BACKEND == 'custody', 'Real-money custody path selected and must be reconciled with licensed settlement provider', 'integration')
    add('signature', config.SIGNATURE_PROVIDER in signature_registry and config.SIGNATURE_PROVIDER not in ('platform', 'sandbox-ca'),
        'Production signing provider registered; asynchronous workflow and signed document archive acceptance required', 'integration')
    add('notary', config.NOTARY_PROVIDER in notary_registry and config.NOTARY_PROVIDER not in ('local', 'sandbox-notary'),
        'External evidence provider registered; checkpoint integrity alone is not legal validity', 'integration')
    add('tax_workflow', config.TAX_MODE in ('withholding', 'self_declared'), 'Tax/invoice workflow explicitly selected for the actual business model', 'business_decision')
    return {'scope': 'technical_configuration_only', 'environment': config.ENV,
        'checks_passed': sum(c['passed'] for c in checks), 'checks_total': len(checks),
        'configuration_ready': all(c['passed'] for c in checks), 'commercial_launch_approved': False,
        'checks': checks, 'vendors': vendors,
        'outside_this_report': ['provider end-to-end acceptance', 'operator/jurisdiction review', 'domain/TLS',
            'independent security audit', 'restore/load/incident drills', 'chain deployment/finality/key operations',
            'customer support and incident staffing', 'native mobile release'],
        'note': 'Passing configuration checks is necessary, not sufficient. This report never authorizes real-money launch.'}

