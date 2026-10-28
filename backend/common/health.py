"""healthのDB確認と公開ビュー。"""
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


def live() -> Response:
    return Response({"status": "ok"})


def database_ready() -> bool:
    """readyのトランザクション内だけstatement timeoutを短縮する。"""
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '2000ms'")
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    return False
            executor = MigrationExecutor(connection)
            return not executor.migration_plan(executor.loader.graph.leaf_nodes())
    except DatabaseError:
        return False


class LiveView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        return live()


class ReadyView(LiveView):
    def get(self, request: Request) -> Response:
        if database_ready():
            return Response({"status": "ok"})
        return Response({"status": "unavailable"}, status=503)
