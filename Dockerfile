# syntax=docker/dockerfile:1
# =============================================================================
# Autokuća — produkcijska slika (jedna slika za sve klijente).
#   docker build -t autokuca:latest .
# Stage 1 instalira pinane ovisnosti u virtualno okruženje; stage 2 sadrži samo
# runtime (bez kompajlera, pip cachea, testova i dev alata) i radi kao korisnik `app`.
# =============================================================================

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install -r requirements.txt


FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="autokuca" \
      org.opencontainers.image.description="Web-platforma za autokuće (FastAPI + Jinja2)"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    DATA_DIR=/app/data \
    OVERRIDES_DIR=/app/overrides \
    WEB_CONCURRENCY=2

# fonts-dejavu-core: font s hrvatskim znakovima za generirane placeholder slike.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --home-dir /app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 0755 /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/data/media /app/data/outbox /app/data/backups /app/overrides \
    && chown -R app:app /app/data \
    && python -m compileall -q /app/app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/zdravlje', timeout=4)" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# Access log je isključen (IP adrese = osobni podaci); greške i dalje idu u log.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --no-access-log --no-server-header --no-proxy-headers"]
