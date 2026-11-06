"""Counter oracles derive networks independently from the public protocol."""
import hashlib
import hmac
from datetime import UTC, datetime

import pytest
from django.conf import settings

from accounts.models import AuthRateLimit
from operations.deployment_contract import DeploymentError
from operations.deployment_verify import ip_observation


@pytest.mark.django_db
@pytest.mark.parametrize(('address', 'network', 'spoof', 'spoof_network'), [
    ('192.0.2.7', '192.0.2.7/32', '198.51.100.8', '198.51.100.8/32'),
    ('2001:db8:1234:5678::1', '2001:db8:1234:5678::/64', '2001:db8:9999::1', '2001:db8:9999::/64'),
])
def test_fixed_window_baseline_and_one_real_attempt(
    address: str, network: str, spoof: str, spoof_network: str,
) -> None:
    window = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
    for value, count in ((network, 4), (spoof_network, 1)):
        digest = hmac.new(settings.AUTH_RATE_LIMIT_HMAC_KEY.encode(), value.encode(),
                          hashlib.sha256).hexdigest()
        AuthRateLimit.objects.create(ip_digest=digest, window_start=window, count=count)
    data = {'expected_ip': address, 'spoof_ip': spoof, 'window': window.isoformat(),
            'before': 4, 'spoof_before': 1}
    ip_observation(data, baseline=True)
    with pytest.raises(DeploymentError):
        ip_observation(data)
    digest = hmac.new(settings.AUTH_RATE_LIMIT_HMAC_KEY.encode(), network.encode(),
                      hashlib.sha256).hexdigest()
    AuthRateLimit.objects.filter(ip_digest=digest).update(count=5)
    ip_observation(data)
    AuthRateLimit.objects.filter(ip_digest=digest).update(count=6)
    with pytest.raises(DeploymentError):
        ip_observation(data)
