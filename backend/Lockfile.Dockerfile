# Dependency resolution only. Not a check and not part of application startup.
ARG PYTHON_IMAGE=python:3.13.18-slim-bookworm@sha256:4178fea840d0d85a1f4d4e768b4cc2ad71b5df43954e1836650c6d239039a4a3
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS resolve
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
WORKDIR /work
COPY backend/pyproject.toml ./
RUN uv lock --python /usr/local/bin/python
FROM scratch AS lockfile
COPY --from=resolve /work/uv.lock /uv.lock
