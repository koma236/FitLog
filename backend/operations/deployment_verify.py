"""Bounded read/denial probes; no private values or raw AWS exceptions escape."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

from operations.deployment_aws import Api, Gateway
from operations.deployment_contract import REGION, DeploymentError, matches, require
from operations.deployment_step import StepContext


def denied(api: Api, service: str, operation: str, **kwargs: Any) -> None:
    """NotFound/transport errors and unexpected success are failures, not denials."""
    try:
        api.call(service, operation, **kwargs)
    except Exception as error:
        response = getattr(error, 'response', {})
        require(response.get('Error', {}).get('Code') in ('AccessDenied', 'AccessDeniedException'))
        return
    raise DeploymentError()


def permission_probes(api: Api, environment: str, data: dict[str, Any]) -> None:
    """Operator must freeze and verify the existing token immediately beforehand.

    PutSecretValue cannot modify a version identified by an existing token:
    https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_PutSecretValue.html
    Never generate a new token here. Confirm the safety on a disposable fixture
    first; the metadata acknowledgement is not a substitute for human approval.
    """
    require(set(data) == {'account', 'application_secret', 'master_secret', 'version',
                          'fixture_verified'})
    require(data['fixture_verified'] is True and matches(r'[0-9]{12}', data['account']))
    require(str(uuid.UUID(data['version'])) == data['version'])
    prefix = f"arn:aws:secretsmanager:{REGION}:{data['account']}:secret:"
    require(matches(re.escape(prefix + environment + '/application-') + r'[A-Za-z0-9]{6}',
                    data['application_secret']))
    require(matches(re.escape(prefix) + r'rds!db-[A-Za-z0-9-]+', data['master_secret']))
    denied(api, 'secretsmanager', 'get_secret_value', SecretId=data['master_secret'],
           VersionStage='AWSCURRENT')
    denied(api, 'secretsmanager', 'put_secret_value', SecretId=data['application_secret'],
           ClientRequestToken=data['version'], SecretString='fitlog-public-denial-probe-not-json')


def database_permissions() -> None:
    """Catalog and real protected-object denials under app credentials."""
    from django.db import DatabaseError, connection, transaction

    with connection.cursor() as cursor:
        cursor.execute('SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls '
                       'FROM pg_roles WHERE rolname = session_user')
        require(cursor.fetchone() == (False, False, False, False, False))
        cursor.execute("SELECT pg_has_role(session_user, 'fitlog_admin', 'MEMBER')")
        require(cursor.fetchone() == (False,))
    for statement in ('SET ROLE fitlog_admin',
                      'SELECT operation FROM _fitlog_bootstrap.initialization'):
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(statement)
        except DatabaseError as error:
            # Django wraps the psycopg error; only SQLSTATE insufficient_privilege
            # proves rejection (not a missing table/column or transaction failure).
            require(getattr(error.__cause__, 'sqlstate', None) == '42501')
        else:
            raise DeploymentError()


def ip_observation(data: dict[str, Any], baseline: bool = False) -> None:
    """Compare the exact pre-recorded UTC window and IPv4 /32 or IPv6 /64 counter."""
    from django.conf import settings

    from accounts.models import AuthRateLimit
    from accounts.rate_limit import ip_network

    require(set(data) == {'expected_ip', 'spoof_ip', 'window', 'before', 'spoof_before'})
    require(type(data['before']) is int and 0 <= data['before'] < 10
            and type(data['spoof_before']) is int and data['spoof_before'] >= 0)
    window = datetime.fromisoformat(data['window'])
    require(window.tzinfo is not None and window.second == 0 and window.microsecond == 0)
    key = settings.AUTH_RATE_LIMIT_HMAC_KEY.encode()
    digests = [hmac.new(key, ip_network(data[name]).encode(), hashlib.sha256).hexdigest()
               for name in ('expected_ip', 'spoof_ip')]
    require(digests[0] != digests[1])
    counts = [AuthRateLimit.objects.filter(ip_digest=digest, window_start=window)
              .values_list('count', flat=True).first() or 0 for digest in digests]
    require(counts == [data['before'] + (0 if baseline else 1), data['spoof_before']])


def s3_probe(api: Api, context: StepContext, account: str) -> None:
    """Operate only on this run's synthetic keys; never list or alter user images."""
    bucket = f'{context.environment}-media-{account}-{REGION}'
    outside = f'deployment-probes/{context.run_id}.txt'
    for operation, extra in (('get_object', {}), ('put_object', {'Body': b'public-fixture'}),
                             ('delete_object', {})):
        denied(api, 's3', operation, Bucket=bucket, Key=outside,
               ExpectedBucketOwner=account, **extra)
    inside = f'images/deployment-probes/{context.run_id}.txt'
    payload = b'fitlog-public-deployment-fixture'
    api.call('s3', 'put_object', Bucket=bucket, Key=inside, Body=payload,
             ExpectedBucketOwner=account, IfNoneMatch='*')
    try:
        result = api.call('s3', 'get_object', Bucket=bucket, Key=inside, ExpectedBucketOwner=account)
        body = result['Body']
        try:
            require(body.read(len(payload) + 1) == payload)
        finally:
            body.close()
    finally:
        api.call('s3', 'delete_object', Bucket=bucket, Key=inside, ExpectedBucketOwner=account)


def verify_from_environment(context: StepContext) -> None:
    """Fixed modes selected through non-secret, operator-validated metadata only."""
    from django.core.management import call_command

    data = json.loads(os.environ.get('FITLOG_VERIFY_INPUT', '{}'))
    require(isinstance(data, dict) and set(data) == {'mode', 'parameters'})
    mode, parameters = data['mode'], data['parameters']
    require(isinstance(parameters, dict))
    call_command('migrate', check_unapplied=True, interactive=False, verbosity=0)
    if mode == 'database':
        require(not parameters)
    elif mode == 'permissions':
        api = Gateway.connect()
        permission_probes(api, context.environment, parameters)
        database_permissions()
        s3_probe(api, context, parameters['account'])
    elif mode in ('ip', 'ip-baseline'):
        ip_observation(parameters, baseline=mode == 'ip-baseline')
    else:
        raise DeploymentError()
