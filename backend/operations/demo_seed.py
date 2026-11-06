"""Synthetic fixtures only. Invoke through deployment_step's production DB guard."""
from typing import TypedDict
from uuid import UUID

from django.db import connection, transaction
from django.db.models import Q

from accounts.models import User
from operations.deployment_contract import require


class SeedAccount(TypedDict):
    id: UUID
    username: str
    email: str
    display_name: str


ACCOUNTS: tuple[SeedAccount, ...] = (
    {'id': UUID('f109b700-0000-4000-8000-000000000001'), 'username': 'fitlog_demo_athlete',
     'email': 'athlete@fitlog-demo.invalid', 'display_name': 'デモ アスリート'},
    {'id': UUID('f109b700-0000-4000-8000-000000000002'), 'username': 'fitlog_demo_trainer',
     'email': 'trainer@fitlog-demo.invalid', 'display_name': 'デモ トレーナー'},
)


def seed() -> None:
    """Identical fixtures are no-ops; collisions never repair or overwrite data."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(5207, 1)')
        missing = []
        for values in ACCOUNTS:
            existing = list(User.objects.select_for_update().filter(
                Q(id=values['id']) | Q(username__iexact=values['username'])
                | Q(email__iexact=values['email']),
            ))
            if not existing:
                missing.append(values)
                continue
            require(len(existing) == 1)
            user = existing[0]
            require(all(getattr(user, key) == value for key, value in values.items())
                    and not user.has_usable_password() and not user.is_staff
                    and not user.is_superuser and user.is_active and user.bio == ''
                    and user.last_login is None)
            require(not hasattr(user, 'profile_health'))
        for values in missing:
            user = User(id=UUID(str(values['id'])), username=str(values['username']),
                        email=str(values['email']), display_name=str(values['display_name']),
                        is_staff=False, is_superuser=False, is_active=True)
            user.set_unusable_password()
            user.save(force_insert=True)
