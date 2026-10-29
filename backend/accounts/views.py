"""Djangoセッションとglobal CSRF検査を使うJSON認証API。"""
import json
from datetime import timedelta
from typing import cast

from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from accounts.models import User
from accounts.rate_limit import consume_attempt
from accounts.services import DuplicateAccount, create_account
from accounts.validation import normalized_email
from common.errors import error_response


def account(user: User) -> dict[str, str]:
    return {"id": str(user.pk), "username": user.username,
            "display_name": user.display_name, "email": user.email}


def method_error(request: HttpRequest, allowed: str) -> JsonResponse:
    response = error_response(request, 405)
    response["Allow"] = allowed
    return response


def auth_required(request: HttpRequest, code: str | None = None) -> JsonResponse:
    response = error_response(request, 401, code)
    response["WWW-Authenticate"] = "Session"
    return response


@csrf_protect
def csrf(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return method_error(request, "GET")
    return JsonResponse({"csrf_token": get_token(request)})


@csrf_protect
def me(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return method_error(request, "GET")
    if not request.user.is_authenticated:
        return auth_required(request)
    return JsonResponse(account(request.user))


def read_credentials(request: HttpRequest, registering: bool) -> dict[str, str] | JsonResponse:
    # readを上限付きにして、未知長/巨大bodyもhash前に拒否する。
    raw = request.read(16 * 1024 + 1)
    if len(raw) > 16 * 1024:
        return error_response(request, 413)
    if request.content_type != "application/json":
        return error_response(request, 415)
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return error_response(request, 400)
    fields = {"email", "password", "username", "display_name"} if registering else {"email", "password"}
    if not isinstance(value, dict) or set(value) != fields:
        return error_response(request, 400)
    if any(not isinstance(value[key], str) for key in fields):
        return error_response(request, 400)
    data = cast(dict[str, str], value)
    errors: dict[str, list[str]] = {}
    try:
        data["email"] = normalized_email(data["email"])
    except ValidationError:
        errors["email"] = ["有効なメールアドレスを入力してください。"]
    if not 1 <= len(data["password"]) <= 128:
        errors["password"] = ["パスワードを確認してください。"]
    if errors:
        return error_response(request, 400, field_errors=errors)
    return data


def authenticate_request(request: HttpRequest, registering: bool) -> HttpResponse:
    if request.method != "POST":
        return method_error(request, "POST")
    retry = consume_attempt(request.META.get("REMOTE_ADDR", ""))
    if retry is not None:
        response = error_response(request, 429)
        response["Retry-After"] = str(retry)
        return response
    if request.user.is_authenticated:
        return error_response(request, 409, "ALREADY_AUTHENTICATED")
    data = read_credentials(request, registering)
    if isinstance(data, JsonResponse):
        return data
    if registering:
        try:
            user = create_account(data["username"], data["email"], data["password"], data["display_name"])
        except ValidationError as exc:
            return error_response(request, 400, field_errors=exc.message_dict)
        except DuplicateAccount as exc:
            code = "DUPLICATE_USERNAME" if exc.field == "username" else "DUPLICATE_EMAIL"
            return error_response(request, 409, code, {exc.field: ["すでに使われています。"]})
    else:
        authenticated = authenticate(request, email=data["email"], password=data["password"])
        if authenticated is None:
            return auth_required(request, "INVALID_CREDENTIALS")
        user = authenticated
    login(request, user, backend="accounts.backends.EmailBackend")
    request.session.set_expiry(timezone.now() + timedelta(days=7))
    return JsonResponse(account(user), status=201 if registering else 200)


@transaction.non_atomic_requests
@csrf_protect
def signup(request: HttpRequest) -> HttpResponse:
    return authenticate_request(request, True)


@transaction.non_atomic_requests
@csrf_protect
def email_login(request: HttpRequest) -> HttpResponse:
    return authenticate_request(request, False)


@csrf_protect
def signout(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return method_error(request, "POST")
    logout(request)
    return HttpResponse(status=204)
