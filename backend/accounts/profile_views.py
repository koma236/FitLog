"""会員間プロフィールAPI。公開可否の決定はサーバーだけで行う。"""
import re
from uuid import UUID

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect

from accounts.models import User
from accounts.profile_service import profile_response, update_profile
from accounts.profile_validation import decode_profile, validate_profile
from accounts.views import auth_required, method_error
from common.errors import error_response


@csrf_protect
def profile(request: HttpRequest, username: str = "me") -> JsonResponse:
    if not request.user.is_authenticated:
        return auth_required(request)
    allowed = "GET, PUT" if username == "me" else "GET"
    if request.method not in allowed.split(", "):
        return method_error(request, allowed)
    if request.method == "GET":
        users = User.objects.select_related("profile_health").filter(is_active=True)
        if username == "me":
            user = users.filter(pk=request.user.pk).first()
        else:
            user = users.filter(username=username).first() if re.fullmatch(r"[a-z0-9_]{3,30}", username) else None
        if user is None:
            return error_response(request, 404)
        return JsonResponse(profile_response(user, request.user))
    raw = request.read(16 * 1024 + 1)
    if len(raw) > 16 * 1024:
        return error_response(request, 413)
    if request.content_type != "application/json" or (request.content_params or {}).get("charset", "utf-8").lower() != "utf-8":
        return error_response(request, 415)
    try:
        owner = UUID(request.headers.get("X-Profile-Owner", ""))
    except ValueError:
        return error_response(request, 400, field_errors={"_form": ["入力内容を確認してください。"]})
    if owner != request.user.pk:
        return error_response(request, 409, "PROFILE_OWNER_CHANGED")
    try:
        value = decode_profile(raw)
    except (ValueError, RecursionError, UnicodeError):
        return error_response(request, 400, field_errors={"_form": ["入力内容を確認してください。"]})
    try:
        update = validate_profile(value)
    except ValidationError as exc:
        return error_response(request, 400, field_errors=exc.message_dict)
    return JsonResponse(update_profile(request.user, update))
