#!/usr/bin/env bash
# =============================================================================
# Uklanjanje klijenta:  deploy/remove-client.sh <ime> [--yes]
#
# 1. zadnji backup baze (deploy/backup.sh <ime>)  2. zaustavi i ukloni kontejnere i volumen
# baze  3. arhivira clients/<ime>/ (baza-dump, slike, .env) u archive/<ime>-<datum>.tar.gz
# 4. uklanja deploy/caddy/sites/<ime>.caddy i reloada Caddy.
# Arhiva sadrži osobne podatke — čuvaj je šifriranu i obriši kad istekne rok iz ugovora.
# =============================================================================
SCRIPT_NAME="remove-client"
. "$(dirname "$0")/lib.sh"

[[ $# -ge 1 ]] || {
    echo "Upotreba: $0 <ime> [--yes]" >&2
    exit 2
}
NAME="$1"
YES="${2:-}"
valid_client_name "$NAME" || die "neispravno ime klijenta '$NAME'"
DIR="$(client_dir "$NAME")"
[[ -d "$DIR" ]] || die "$DIR ne postoji"
require docker tar

if [[ "$YES" != "--yes" ]]; then
    echo "Klijent '$NAME' bit će zaustavljen, a njegova baza i datoteke arhivirani i uklonjeni."
    read -r -p "Za potvrdu upiši ime klijenta: " answer
    [[ "$answer" == "$NAME" ]] || die "prekinuto"
fi

log "Zadnji backup baze..."
if ! "$DEPLOY_DIR/backup.sh" "$NAME"; then
    warn "backup nije uspio — radim nešifrirani dump u arhivu"
    dc "$NAME" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
        >"$DIR/data/backups/${NAME}-final.dump" || die "ni dump nije uspio — ništa nije obrisano"
fi

log "Zaustavljam i uklanjam kontejnere i volumen baze..."
dc "$NAME" down -v --remove-orphans

ARCHIVE_DIR="$ROOT_DIR/archive"
mkdir -p "$ARCHIVE_DIR"
chmod 700 "$ARCHIVE_DIR"
ARCHIVE="$ARCHIVE_DIR/${NAME}-$(date +%Y%m%d-%H%M%S).tar.gz"
log "Arhiviram $DIR → $ARCHIVE"
tar -czf "$ARCHIVE" -C "$CLIENTS_DIR" "$NAME"
chmod 600 "$ARCHIVE"
rm -rf "$DIR"

rm -f "$CADDY_DIR/sites/$NAME.caddy"
caddy_reload || warn "reload Caddyja nije uspio — provjeri deploy/caddy"

log "Klijent '$NAME' uklonjen. Arhiva: $ARCHIVE"
log "Ne zaboravi: DNS zapise, Brevo domenu i kopije na off-site odredištu (rclone)."
