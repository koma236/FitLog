"""サーバー計算・公開情報の射影と本人更新のtransaction境界。"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction

from accounts.models import ProfileHealth, User
from accounts.profile_validation import ENERGY_KEYS, HEALTH_KEYS, PROFILE_KEYS, ProfileUpdate
from media_assets.presentation import avatar


def energy(health: ProfileHealth) -> dict[str, int | None]:
    result: dict[str, int | None] = dict.fromkeys(ENERGY_KEYS)
    if health.age is None or not 19 <= health.age <= 59 or health.height_cm is None or health.weight_kg is None or health.formula is None:
        return result
    bmr = 10 * health.weight_kg + Decimal("6.25") * health.height_cm - 5 * health.age + (5 if health.formula == "male" else -161)
    if bmr <= 0:
        return result
    result["bmr"] = int(bmr.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    factors = {"low": Decimal("1.5"), "medium": Decimal("1.75"), "high": Decimal("2.1")}
    if health.activity is not None and health.activity in factors:
        result["tdee"] = result["intake"] = int((bmr * factors[health.activity]).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return result


def profile_response(user: User, actor: User) -> dict[str, Any]:
    try:
        health = user.profile_health
    except ProfileHealth.DoesNotExist:
        health = ProfileHealth(user=user)
    owner = user.pk == actor.pk
    values = {"height": f"{health.height_cm:.1f}" if health.height_cm is not None else None,
              "weight": f"{health.weight_kg:.1f}" if health.weight_kg is not None else None,
              "age": health.age, "formula": health.formula, "activity": health.activity}
    flags = {key: bool(getattr(health, key + "_public")) for key in PROFILE_KEYS}
    response: dict[str, Any] = {"viewer_id": str(actor.pk), "avatar": avatar(user), "id": str(user.pk), "username": user.username, "display_name": user.display_name,
                                "bio": user.bio, "is_owner": owner,
                                "health": {key: values[key] for key in HEALTH_KEYS if owner or flags[key]},
                                "energy": {key: value for key, value in energy(health).items() if owner or flags[key]}}
    if owner:
        response["visibility"] = {key: "public" if flags[key] else "private" for key in PROFILE_KEYS}
    return response


def update_profile(actor: User, update: ProfileUpdate) -> dict[str, Any]:
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=actor.pk, is_active=True)
        user.display_name, user.bio = update.display_name, update.bio
        user.save(update_fields=["display_name", "bio"])
        health, _ = ProfileHealth.objects.get_or_create(user=user)
        health.height_cm, health.weight_kg = update.height, update.weight
        health.age, health.formula, health.activity = update.age, update.formula, update.activity
        for key, public in update.visibility.items():
            setattr(health, key + "_public", public)
        health.save()
        # get_or_create caches the reverse relation; use the saved instance explicitly.
        user.profile_health = health
        response = profile_response(user, actor)
    return response
