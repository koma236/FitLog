"""Seed oracle: exactly two synthetic, unusable-password accounts, no overwrite."""
import pytest
from django.contrib.auth.hashers import is_password_usable

from accounts.models import User
from operations.demo_seed import ACCOUNTS, seed
from operations.deployment_contract import DeploymentError

pytestmark = pytest.mark.django_db(transaction=True)


def test_seed_is_idempotent_and_never_makes_privileged_users() -> None:
    seed()
    before = list(User.objects.order_by('username').values())
    seed()
    assert list(User.objects.order_by('username').values()) == before
    assert len(before) == 2
    for user in User.objects.all():
        assert not user.is_staff and not user.is_superuser
        assert not is_password_usable(user.password)
        assert user.email.endswith('.invalid')


def test_seed_collision_rolls_back_both_accounts() -> None:
    user = User(id=ACCOUNTS[1]['id'], username='existing_person', email='existing@example.invalid',
                display_name='Existing')
    user.set_unusable_password()
    user.save()
    with pytest.raises(DeploymentError):
        seed()
    assert User.objects.count() == 1
    user.refresh_from_db()
    assert user.username == 'existing_person'


def test_seed_does_not_repair_modified_fixture() -> None:
    seed()
    User.objects.filter(id=ACCOUNTS[0]['id']).update(is_staff=True)
    with pytest.raises(DeploymentError):
        seed()
    assert User.objects.get(id=ACCOUNTS[0]['id']).is_staff
