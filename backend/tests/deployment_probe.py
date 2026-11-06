"""Production-module/real app-role oracle inside the owned PG17 TLS fixture."""
import os
import subprocess
import sys

from operations.contract import SecretValues


def probe(values: SecretValues) -> None:
    env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'config.production', 'FITLOG_ENV': 'production',
           'DJANGO_SECRET_KEY': values.django, 'AUTH_RATE_LIMIT_HMAC_KEY': values.hmac,
           'FITLOG_PUBLIC_HOST': 'dfixture.cloudfront.net', 'PRIVATE_MEDIA_BACKEND': 's3',
           'PRIVATE_MEDIA_BUCKET': 'fitlog-demo-test-media',
           'PRIVATE_MEDIA_EXPECTED_OWNER': '123456789012', 'AWS_REGION': 'ap-northeast-1',
           'POSTGRES_HOST': 'db-valid', 'POSTGRES_DB': 'fitlog', 'POSTGRES_USER': 'fitlog_app',
           'POSTGRES_PASSWORD': values.password, 'POSTGRES_SSLROOTCERT': '/fixtures/ca.pem',
           'FITLOG_VERIFY_INPUT': '{"mode":"database","parameters":{}}'}
    script = '''
import contextlib, io, json
import django
django.setup()
from operations.deployment_step import StepContext, database_guard, run_step, main
from operations.deployment_verify import database_permissions
from operations.deployment_contract import DeploymentError
from accounts.models import User
context = StepContext('11111111-1111-4111-8111-111111111111', 'db-valid', 'fitlog-demo-test')
database_guard(context)
database_permissions()
for step in ('migrate', 'seed', 'seed', 'check', 'verify'):
    out, err = io.StringIO(), io.StringIO()
    args = ['--step', step, '--run-id', context.run_id, '--expected-host',
            'fixture.ap-northeast-1.rds.amazonaws.com', '--environment', context.environment]
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(args, runner=lambda chosen, ignored: run_step(chosen, context))
    assert code == 0 and err.getvalue() == ''
    assert json.loads(out.getvalue()) == {'event':'deployment_step_completed',
                                        'step':step,'run_id':context.run_id}
assert User.objects.count() == 2
assert not any(user.has_usable_password() for user in User.objects.all())
try:
    database_guard(StepContext(context.run_id, 'wrong', context.environment))
except DeploymentError:
    pass
else:
    raise AssertionError('Wrong database target was accepted')
print('deployment-production-probe-ok')
'''
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True,
                            text=True, timeout=90)
    assert result.returncode == 0 and result.stdout.strip() == 'deployment-production-probe-ok', \
        'Deployment production/PG17 probe failed (private diagnostics suppressed)'
    print('Production deployment wrapper/seed/app TLS/DB permissions: OK')
