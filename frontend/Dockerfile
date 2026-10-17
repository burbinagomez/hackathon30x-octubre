# Multi-stage (R-docker): node solo existe en el build; el final es Caddy sirviendo dist/.
FROM node:22.23.3-alpine AS builder
# Único ARG: Railway solo pasa al build lo declarado, así nada más llega al bundle (R2).
ARG VITE_API_URL
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2.11.7-alpine
# El binario trae cap_net_bind_service: como no root, un runtime que bloquee file capabilities
# rompe el exec recién en Railway. Con puerto > 1024 no hace falta.
RUN apk add --no-cache libcap && setcap -r /usr/bin/caddy && apk del libcap \
    && adduser -D -H web && chown -R web:web /data /config
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /app/dist /srv
USER web
HEALTHCHECK CMD wget -q --spider http://127.0.0.1:${PORT:-8080}/health || exit 1
