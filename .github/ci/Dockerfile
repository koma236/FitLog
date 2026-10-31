# Inspection only: reuse the exact dependency tree from the built frontend image.
ARG FRONTEND_IMAGE=fitlog-dev-frontend
FROM ${FRONTEND_IMAGE}
COPY .github/ci/ /ci/
COPY .github/workflows/ci.yml /ci/workflow.yml
COPY .ai-dev/project.toml /ci/project.toml
