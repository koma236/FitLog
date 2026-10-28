"""公開するのはhealthだけ。未実装APIはJSON404。"""
from django.urls import path, re_path

from common.errors import not_found
from common.health import LiveView, ReadyView

urlpatterns = [
    path("api/health/live", LiveView.as_view()),
    path("api/health/ready", ReadyView.as_view()),
    re_path(r"^api(?:/.*)?$", not_found),
]
