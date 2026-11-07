"""Run through the backend manage.py shell to check the real HTTP renderer.

The expected bytes come from docs/fl-01-foundation-design.md, not aws_boundary.
No AWS or product-data writes. The caller holds the shared runtime lock.
"""
import hashlib
import json

from django.test import Client

response = Client().get('/api/health/live', HTTP_HOST='localhost', HTTP_ACCEPT='application/json')
assert response.status_code == 200, 'HEALTH_RESPONSE_STATUS_MISMATCH'
assert response.content == b'{"status":"ok"}', 'HEALTH_RESPONSE_BYTES_MISMATCH'
print(json.dumps({'health_wire_contract': 'pass', 'body_bytes': len(response.content),
                  'body_sha256': hashlib.sha256(response.content).hexdigest(), 'aws': 'not_run'}))
