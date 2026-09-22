# --- build stage -----------------------------------------------------------
FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm ci || npm install
COPY web/index.html web/vite.config.ts web/tsconfig.json web/tsconfig.node.json ./
COPY web/src ./src
RUN npm run build

# --- serve stage -----------------------------------------------------------
# nginx:alpine renders /etc/nginx/templates/*.template with envsubst at start.
FROM nginx:1.27-alpine AS serve
RUN apk add --no-cache wget
COPY web/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

ENV WEB_HTTP_PORT=8080 \
    API_UPSTREAM=api:8000
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=4s --start-period=5s --retries=5 \
    CMD wget -qO- "http://127.0.0.1:${WEB_HTTP_PORT}/" >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
