# Build from the repository root. Keep dependency layers before application code.
FROM node:24-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS frontend
WORKDIR /usr/src/app/apps/frontend
ENV CLI_WIDTH=80
COPY apps/frontend/package.json apps/frontend/yarn.lock ./
RUN --mount=type=cache,id=librephotos-yarn,target=/usr/local/share/.cache/yarn \
    sed -i "s@https://registry.yarnpkg.com/@https://registry.npmjs.org/@g" yarn.lock && \
    yarn config set registry https://registry.npmjs.org && \
    yarn install --frozen-lockfile --network-timeout 120000
COPY packages/api-client/ /usr/src/app/packages/api-client/
COPY apps/frontend/ ./
RUN yarn run build

FROM reallibrephotos/librephotos-base:1.5.1@sha256:9dcf24396235ef8832fe1e5c1bcbe76eca57f5a954d2b0ad3a85179ed0783435
WORKDIR /code
COPY apps/backend/requirements*.txt /code/
RUN --mount=type=cache,id=librephotos-pip,target=/root/.cache/pip \
    pip install --break-system-packages -r requirements.txt -r requirements.unified.txt
COPY apps/backend/ /code/
COPY --from=frontend /usr/src/app/apps/frontend/dist /code/frontend_build/
COPY deploy/docker/backend/entrypoint.sh /entrypoint.sh
RUN mkdir -p /code/static && chmod +x /entrypoint.sh
# Revision metadata must not invalidate the dependency or frontend build layers.
ARG GIT_HASH=unknown
ARG IMAGE_TAG=local
ENV GIT_HASH=${GIT_HASH} IMAGE_TAG=${IMAGE_TAG} SERVE_FRONTEND=true
ENV WEB_CONCURRENCY=1 WEB_MAX_REQUESTS=2000
RUN printf '%s\n' "$GIT_HASH" > /code/frontend_build/git_hash.txt
EXPOSE 8001
CMD ["/entrypoint.sh"]
