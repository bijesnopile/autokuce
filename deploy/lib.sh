# shellcheck shell=bash
# Zajedničke funkcije za deploy/*.sh (učitava se s `. "$(dirname "$0")/lib.sh"`).
# Pretpostavljeni raspored na VPS-u (npr. /opt/autokuca = klon ovog repozitorija):
#   deploy/caddy/                 zajednički Caddy (portovi 80/443, mreža `web`)
#   deploy/caddy/sites/<ime>.caddy
#   clients/<ime>/                docker-compose.yml, .env, data/, overrides/

set -Eeuo pipefail
umask 027

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
CLIENTS_DIR="${CLIENTS_DIR:-$ROOT_DIR/clients}"
CADDY_DIR="$DEPLOY_DIR/caddy"
AUTOKUCA_IMAGE="${AUTOKUCA_IMAGE:-autokuca:latest}"

log() { printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${SCRIPT_NAME:-deploy}" "$*"; }
warn() { log "UPOZORENJE: $*" >&2; }
die() {
    log "GREŠKA: $*" >&2
    exit 1
}

require() {
    local cmd
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 || die "nedostaje naredba '$cmd'"
    done
}

# Ime klijenta: mala slova, brojke i crtica (koristi se u imenima kontejnera i mapa).
valid_client_name() {
    [[ "$1" =~ ^[a-z0-9][a-z0-9-]{1,30}$ ]]
}

client_dir() { printf '%s/%s' "$CLIENTS_DIR" "$1"; }

# Čita jednu vrijednost iz .env datoteke (KEY=VALUE, bez izvršavanja datoteke).
env_get() {
    local file="$1" key="$2" line
    [[ -f "$file" ]] || return 0
    line="$(grep -E "^${key}=" "$file" | tail -n 1 || true)"
    line="${line#*=}"
    line="${line%\"}"
    line="${line#\"}"
    printf '%s' "$line"
}

# Vrijednost iz klijentovog .env, zatim iz deploy/backup.env (BACKUP_ENV_FILE), zatim zadana.
setting() {
    local name="$1" key="$2" default="${3:-}" value=""
    value="$(env_get "$(client_dir "$name")/.env" "$key")"
    [[ -n "$value" ]] || value="$(env_get "${BACKUP_ENV_FILE:-$DEPLOY_DIR/backup.env}" "$key")"
    [[ -n "$value" ]] || value="${!key:-}"
    printf '%s' "${value:-$default}"
}

random_hex() { head -c "${1:-32}" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

# docker compose za klijenta (projekt ak_<ime>).
dc() {
    local name="$1" dir
    shift
    dir="$(client_dir "$name")"
    docker compose -f "$dir/docker-compose.yml" --project-directory "$dir" \
        -p "ak_${name//-/_}" "$@"
}

dc_caddy() {
    docker compose -f "$CADDY_DIR/docker-compose.yml" --project-directory "$CADDY_DIR" \
        -p autokuca_caddy "$@"
}

caddy_reload() {
    if [[ -n "$(dc_caddy ps --status running -q caddy 2>/dev/null)" ]]; then
        dc_caddy exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
    else
        warn "zajednički Caddy ne radi — pokrećem ga (deploy/caddy)"
        dc_caddy up -d
    fi
}

# Čeka da kontejner <ime>_app bude "healthy" (Docker HEALTHCHECK na /zdravlje).
wait_healthy() {
    local name="$1" timeout="${2:-180}" waited=0 status
    while ((waited < timeout)); do
        status="$(docker inspect --format '{{.State.Health.Status}}' "${name}_app" 2>/dev/null || echo "none")"
        [[ "$status" == "healthy" ]] && return 0
        sleep 3
        waited=$((waited + 3))
    done
    return 1
}

list_clients() {
    local dir
    for dir in "$CLIENTS_DIR"/*/; do
        [[ -f "$dir/docker-compose.yml" ]] && basename "$dir"
    done
    return 0
}
