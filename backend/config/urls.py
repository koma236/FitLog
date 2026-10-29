"""healthと最小認証のルーティング。未実装APIはJSON404。"""
from django.urls import path, re_path

from accounts import profile_views
from accounts import views as auth
from common.errors import not_found
from common.health import LiveView, ReadyView

urlpatterns = [
    path("api/auth/csrf", auth.csrf),
    path("api/auth/signup", auth.signup),
    path("api/auth/login", auth.email_login),
    path("api/auth/logout", auth.signout),
    path("api/auth/me", auth.me),
    path("api/users/me", profile_views.profile),
    path("api/users/<str:username>", profile_views.profile),
    path("api/health/live", LiveView.as_view()),
    path("api/health/ready", ReadyView.as_view()),
    re_path(r"^api(?:/.*)?$", not_found),
]
