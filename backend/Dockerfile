# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.13.18-slim-bookworm@sha256:4178fea840d0d85a1f4d4e768b4cc2ad71b5df43954e1836650c6d239039a4a3
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE}
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
# Missing lock is a build failure; never resolve dependencies during verification.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --all-groups --no-install-project
COPY backend/ ./
COPY docs/api/openapi.json /app/contracts/openapi.json
RUN groupadd --system fitlog && useradd --system --gid fitlog --home-dir /app fitlog \
    && chown -R fitlog:fitlog /app
USER fitlog
EXPOSE 8000
CMD ["uv", "run", "--frozen", "--no-sync", "python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
