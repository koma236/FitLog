"""Single-environment, recording-free approval; offline and no AWS SDK imports."""
from datetime import datetime, timezone
from decimal import Decimal
import re
import uuid

import aws_contract as base

FIELDS = base.FIELDS - {'campaign_id'}
STEPS = ['journey', 'cleanup']


def validate(data, now=None):
    """Validate the dedicated contract, retaining the original B/C evidence oracles."""
    try:
        base.require(isinstance(data, dict) and set(data) == FIELDS)
        base.require(type(data['schema_version']) is int and data['schema_version'] == 1)
        for key in ('run_id', 'bootstrap_id'):
            base.require(str(uuid.UUID(data[key])) == data[key])
        patterns = {
            'test_run': r'[a-f0-9]{12}', 'account': r'[0-9]{12}',
            'environment': r'fitlog-demo-[a-z0-9]+(?:-[a-z0-9]+)*',
            'source': r'[a-f0-9]{40}', 'image_digest': r'sha256:[a-f0-9]{64}',
            'frontend_sha256': r'[a-f0-9]{64}',
            'origin': r'https://[a-z0-9]{1,63}\.cloudfront\.net',
            'lease_id': r'[A-Za-z0-9_-]{8,80}',
        }
        for key, pattern in patterns.items():
            base.require(isinstance(data[key], str) and re.fullmatch(pattern, data[key]))
        base.require(len(data['environment']) <= 24 and data['region'] == 'ap-northeast-1')
        approval = data['approval']
        base.require(isinstance(approval, dict) and set(approval) == {'reference', 'steps', 'budget_usd'})
        base.require(isinstance(approval['reference'], str)
                     and re.fullmatch(r'[A-Za-z0-9_:#./-]{8,160}', approval['reference']))
        base.require(approval['steps'] == STEPS)
        budget = approval['budget_usd']
        base.require(isinstance(budget, str) and re.fullmatch(r'[0-9]{1,6}(\.[0-9]{1,2})?', budget))
        base.require(Decimal('0') < Decimal(budget) <= Decimal('5'))
        start, end = base.timestamp(data['starts_at']), base.timestamp(data['expires_at'])
        base.require(start <= (now or datetime.now(timezone.utc)) < end)
        base.require(300 < (end - start).total_seconds() <= 2700)
        base.validate_handoff(data)
        base.require(isinstance(data['evidence'], list) and base.boundary_status(data)['status'] != 'fail')
        return data
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise base.Invalid() from None


def binding(data):
    return {**base.identity(data), 'handoff': data['handoff'],
            'approval_reference': data['approval']['reference']}


def initialize(folder, data):
    """Create one environment's immutable ledger, never a dummy second environment."""
    folder = base.protected(folder, True)
    base.exclusive_json(folder / 'binding.json', {'schema_version': 1, 'binding': binding(data)})


def claim(folder, data):
    """Consume before any client starts, including attempts that subsequently fail."""
    folder = base.protected(folder, True)
    base.require(base.load(folder / 'binding.json') == {'schema_version': 1, 'binding': binding(data)})
    base.exclusive_json(folder / 'attempt.json', {'schema_version': 1, 'binding': binding(data),
                        'test_run': data['test_run'], 'lease_id': data['lease_id'], 'status': 'consumed'})
