#!/usr/bin/env bash
# =============================================================================
# Vraćanje baze iz backupa:  deploy/restore.sh <ime> <datoteka> [--yes]
#
#   <datoteka>: clients/<ime>/data/backups/<ime>-DATUM.dump.gz.age|.gpg (ili samo ime
#               datoteke — tada se traži lokalno pa na BACKUP_RCLONE_REMOTE)
#
# Koraci: dešifriranje (age: BACKUP_AGE_IDENTITY = datoteka s privatnim ključem; gpg: ključ u
# keyringu) → gunzip → pg_restore --list → zaustavi app → vrati u NOVU bazu → zamijeni
# (stara baza ostaje kao <baza>_old_DATUM) → pokreni app → čekaj /zdravlje.
# Slike (STORAGE_BACKEND=local): rclone copy <remote>/<ime>/media clients/<ime>/data/media
# Postupak i test vraćanja: README → "Backup i vraćanje".
# =============================================================================
SCRIPT_NAME="restore"
. "$(dirname "$0")/lib.sh"

[[ $# -ge 2 ]] || {
    echo "Upotreba: $0 <ime> <datoteka> [--yes]" >&2
    exit 2
}
NAME="$1"
FILE="$2"
YES="${3:-}"
valid_client_name "$NAME" || die "neispravno ime klijenta '$NAME'"
DIR="$(client_dir "$NAME")"
[[ -d "$DIR" ]] || die "klijent '$NAME' ne postoji ($DIR)"
require gzip

pg_run() {
    if [[ "${AK_PG_LOCAL:-}" == "1" ]]; then
        "$@"
    else
        dc "$NAME" exec -T db sh -c \
            'PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" exec "$@"' sh "$@"
    fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# 1. Pronađi datoteku (lokalno ili na off-site odredištu).
if [[ ! -f "$FILE" && -f "$DIR/data/backups/$FILE" ]]; then
    FILE="$DIR/data/backups/$FILE"
fi
if [[ ! -f "$FILE" ]]; then
    remote="$(setting "$NAME" BACKUP_RCLONE_REMOTE)"
    [[ -n "$remote" ]] || die "datoteka '$FILE' ne postoji"
    require rclone
    log "Preuzimam $(basename "$FILE") s $remote/$NAME/db/"
    rclone copy "$remote/$NAME/db/$(basename "$FILE")" "$TMP/"
    FILE="$TMP/$(basename "$FILE")"
    [[ -f "$FILE" ]] || die "datoteka nije pronađena ni na $remote"
fi

# 2. Dešifriranje + raspakiravanje.
DUMP="$TMP/restore.dump"
case "$FILE" in
    *.age)
        require age
        identity="$(setting "$NAME" BACKUP_AGE_IDENTITY)"
        [[ -n "$identity" && -f "$identity" ]] ||
            die "za .age treba BACKUP_AGE_IDENTITY=<datoteka s privatnim ključem>"
        age -d -i "$identity" "$FILE" | gzip -dc >"$DUMP"
        ;;
    *.gpg)
        require gpg
        gpg --batch --quiet --decrypt "$FILE" | gzip -dc >"$DUMP"
        ;;
    *.gz) gzip -dc "$FILE" >"$DUMP" ;;
    *) cp "$FILE" "$DUMP" ;;
esac

# 3. Provjera arhive.
if [[ "${AK_PG_LOCAL:-}" == "1" ]]; then
    pg_restore --list "$DUMP" >"$TMP/toc.txt"
else
    pg_run pg_restore --list <"$DUMP" >"$TMP/toc.txt"
fi
grep -q "alembic_version" "$TMP/toc.txt" || die "arhiva ne sadrži shemu aplikacije"
log "Arhiva ispravna: $(grep -c " TABLE DATA " "$TMP/toc.txt" || true) tablica s podacima"

if [[ "$YES" != "--yes" ]]; then
    echo "Baza klijenta '$NAME' bit će zamijenjena sadržajem iz $(basename "$FILE")."
    echo "Aplikacija će biti nedostupna nekoliko minuta. Trenutna baza ostaje kao kopija."
    read -r -p "Za potvrdu upiši ime klijenta: " answer
    [[ "$answer" == "$NAME" ]] || die "prekinuto"
fi

DB="$(env_get "$DIR/.env" POSTGRES_DB)"
DB="${DB:-${PGDATABASE:-autokuca}}"
TS="$(date +%Y%m%d%H%M%S)"
NEW_DB="${DB}_restore_${TS}"
OLD_DB="${DB}_old_${TS}"

if [[ "${AK_PG_LOCAL:-}" != "1" ]]; then
    log "Zaustavljam aplikaciju..."
    dc "$NAME" stop app
fi

log "Vraćam u novu bazu $NEW_DB ..."
pg_run createdb -T template0 -E UTF8 "$NEW_DB"
if [[ "${AK_PG_LOCAL:-}" == "1" ]]; then
    pg_run pg_restore --no-owner --exit-on-error -d "$NEW_DB" "$DUMP"
else
    dc "$NAME" cp "$DUMP" db:/tmp/restore.dump
    pg_run pg_restore --no-owner --exit-on-error -d "$NEW_DB" /tmp/restore.dump
    dc "$NAME" exec -T db rm -f /tmp/restore.dump
fi
version="$(pg_run psql -d "$NEW_DB" -tAc "SELECT version_num FROM alembic_version")"
log "Vraćena shema: $version"

log "Zamjena baza: $DB → $OLD_DB, $NEW_DB → $DB"
pg_run psql -d postgres -v ON_ERROR_STOP=1 -q \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB' AND pid <> pg_backend_pid();" \
    -c "ALTER DATABASE \"$DB\" RENAME TO \"$OLD_DB\";" \
    -c "ALTER DATABASE \"$NEW_DB\" RENAME TO \"$DB\";" >/dev/null

if [[ "${AK_PG_LOCAL:-}" != "1" ]]; then
    log "Pokrećem aplikaciju (migracije se primjenjuju u entrypointu)..."
    dc "$NAME" up -d app
    if ! wait_healthy "$NAME" 240; then
        dc "$NAME" logs --tail 80 app >&2 || true
        die "aplikacija nije zdrava. Povratak: ALTER DATABASE \"$DB\" RENAME TO \"${DB}_neuspjelo\"; ALTER DATABASE \"$OLD_DB\" RENAME TO \"$DB\";"
    fi
fi

log "Vraćanje završeno. Prethodna baza je sačuvana kao $OLD_DB."
log "Kad provjeriš stranicu: deploy/restore.sh ne briše ništa — obriši kopiju ručno:"
log "  docker compose -p ak_${NAME//-/_} exec db dropdb -U autokuca $OLD_DB"
