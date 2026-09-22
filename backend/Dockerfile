FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_PORT=8000

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Container-level health check (no curl in slim image).  Shell form so
# $APP_PORT is expanded; override APP_PORT to change the listen port.
HEALTHCHECK --interval=10s --timeout=4s --start-period=5s --retries=5 \
    CMD python -c "import json,os,urllib.request; p=os.environ.get('APP_PORT','8000'); r=urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=3); assert json.load(r)['status']=='ok'"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
