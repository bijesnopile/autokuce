#!/bin/sh
# Autokuća — entrypoint kontejnera `app`.
# 1) SECRET_KEY (ako nije zadan: generira se jednom i trajno čuva u data/.secret_key)
# 2) čeka bazu  3) alembic upgrade head  4) seed na praznoj bazi (--minimal ili puni demo uz
#    DEMO_SEED=true); na postojećoj bazi samo novi ključevi postavki
# 5) provjera da je SECRET_KEY isti kao prije (otisak u bazi)  6) naredba iz CMD-a (uvicorn).
set -eu

cd /app

# Ključ se generira samo jednom (data/.secret_key, 0600) i nikad ponovno; aplikacija i
# `docker compose exec` naredbe čitaju isti ključ. Bez trajnog data/ volumena start se odbija.
python -m app.cli ensure-secret-key

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

# Ključ mora biti isti kao pri prošlim startovima (otisak u bazi) — inače bi 2FA tajne,
# sesije i poveznice za odjavu tiho prestale vrijediti. Promjena ključa: --accept (SIGURNOST.md).
python -m app.cli check-secret-key

exec "$@"
