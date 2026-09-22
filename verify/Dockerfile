# Verification image: contains both toolchains so the one-shot `verify`
# service can run backend unit tests, backend/frontend builds and live
# API/HTTP smoke checks against the real running containers.
FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /verify

# Python deps for the unit tests (fastapi TestClient needs httpx).
COPY backend/requirements.txt /srv/backend/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /srv/backend/requirements.txt
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1

# Pre-install frontend deps so `npm run build` runs offline in the verify run.
COPY web/package.json web/package-lock.json* /srv/web/
RUN cd /srv/web && (npm ci || npm install)

# Sources under test.
COPY backend /srv/backend
COPY web /srv/web
COPY verify /verify

RUN chmod +x /verify/entrypoint.sh

CMD ["/verify/entrypoint.sh"]
