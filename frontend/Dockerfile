# syntax=docker/dockerfile:1
ARG NODE_IMAGE=node:24.22.1-bookworm-slim@sha256:be8204d4bd327363357f532187b752ff62759c31bedf98e9e18fc08c9cbd605c
FROM ${NODE_IMAGE}
WORKDIR /app
ENV NPM_CONFIG_UPDATE_NOTIFIER=false
# Missing lock is a build failure; do not fall back to npm install.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN chown -R node:node /app
USER node
EXPOSE 5173
CMD ["npm", "run", "dev"]
