#!/bin/sh
# Autokuća — entrypoint kontejnera `app`.
# 1) SECRET_KEY (ako nije zadan: generira se jednom i čuva u data/.secret_key)
# 2) čeka bazu  3) alembic upgrade head  4) seed na praznoj bazi (--minimal ili puni demo uz
#    DEMO_SEED=true); na postojećoj bazi samo novi ključevi postavki
# 5) pokreće naredbu (uvicorn iz CMD-a).
set -eu

cd /app

if [ -z "${SECRET_KEY:-}" ]; then
    key_file="${DATA_DIR:-/app/data}/.secret_key"
    if [ ! -s "$key_file" ]; then
        umask 077
        python -c "import secrets; print(secrets.token_urlsafe(48))" > "$key_file"
        echo "[entrypoint] SECRET_KEY nije postavljen — generiran je i spremljen u data/.secret_key"
    fi
    SECRET_KEY="$(cat "$key_file")"
    export SECRET_KEY
fi

echo "[entrypoint] Čekam bazu..."
python -m app.cli wait-db --timeout "${DB_WAIT_TIMEOUT:-60}"

echo "[entrypoint] Migracije (alembic upgrade head)..."
python -m app.cli migrate

case "$(printf '%s' "${DEMO_SEED:-false}" | tr '[:upper:]' '[:lower:]')" in
    1 | true | yes | on)
        echo "[entrypoint] Seed: puni demo (DEMO_SEED=true)"
        python -m app.seed --if-empty
        ;;
    *)
        echo "[entrypoint] Seed: minimalni (postavke, stranice, katalog, superadmin)"
        python -m app.seed --minimal --if-empty
        ;;
esac

exec "$@"
