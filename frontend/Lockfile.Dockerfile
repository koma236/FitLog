# Dependency resolution only. No lifecycle scripts, host node_modules or install.
ARG NODE_IMAGE=node:24.22.1-bookworm-slim@sha256:be8204d4bd327363357f532187b752ff62759c31bedf98e9e18fc08c9cbd605c
FROM ${NODE_IMAGE} AS resolve
WORKDIR /work
COPY frontend/package.json ./
RUN npm install --package-lock-only --ignore-scripts --no-audit --no-fund
FROM scratch AS lockfile
COPY --from=resolve /work/package-lock.json /package-lock.json
