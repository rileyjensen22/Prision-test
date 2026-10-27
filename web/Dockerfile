# Build from the repository root:  docker build -f web/Dockerfile .
# Builds the production bundle (with the kiosk Content-Security-Policy) and serves it with nginx,
# which also forwards /api to the API container.
FROM node:22-slim AS build
WORKDIR /app
COPY web/package*.json ./
# Behind a proxy that inspects TLS, build with ISD_EXTRA_CA=/path/to/ca.pem.
COPY deploy/build-ca /tmp/build-ca
RUN if [ -f /tmp/build-ca/extra-ca.pem ]; then export npm_config_cafile=/tmp/build-ca/extra-ca.pem; fi; \
    npm ci
COPY web/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
HEALTHCHECK --interval=5s --timeout=3s --retries=20 CMD wget -q --spider http://127.0.0.1/ || exit 1
