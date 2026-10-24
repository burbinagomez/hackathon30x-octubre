# Multi-stage (R-docker): node solo existe en el build; el final es alpine con el binario de Caddy sirviendo dist/.
FROM node:26.12.0-alpine AS builder
# Solo estos ARG: Railway pasa al build lo declarado, así nada más llega al bundle (R2).
# La publishable key de Supabase es pública por diseño (constitución 2.0.0); jamás una sb_secret_.
ARG VITE_API_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# El binario trae cap_net_bind_service: como no root, un runtime que bloquee file capabilities
# rompe el exec recién en Railway. Con puerto > 1024 no hace falta. Se saca acá y se copia solo
# el binario: hacer setcap en el final duplicaba los 46 MB en otra capa (111 → 56 MB).
FROM caddy:2.11.7-alpine AS caddy
RUN apk add --no-cache libcap && setcap -r /usr/bin/caddy

FROM alpine:3.23.6
RUN apk add --no-cache ca-certificates \
    && adduser -D -H web && mkdir -p /data /config && chown web:web /data /config
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /app/dist /srv
ENV XDG_CONFIG_HOME=/config XDG_DATA_HOME=/data
USER web
# wget de busybox, sin instalar curl.
HEALTHCHECK CMD wget -q --spider http://127.0.0.1:${PORT:-8080}/health || exit 1
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
