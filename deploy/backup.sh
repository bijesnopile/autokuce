#!/usr/bin/env bash
# =============================================================================
# Backup baze (i slika):  deploy/backup.sh <ime|all>
#
#   pg_dump (custom format) → gzip → šifriranje (age, ili gpg) → provjera integriteta
#   (gzip -t + pg_restore --list) → clients/<ime>/data/backups/ → rclone na off-site
#   → retencija (lokalno i na odredištu, BACKUP_RETENTION_DAYS, default 30 dana).
#   Ako je STORAGE_BACKEND=local, slike (data/media) se dodatno kopiraju rclone syncom.
#
# Konfiguracija: deploy/backup.env (zajedničko) ili clients/<ime>/.env (po klijentu):
#   BACKUP_AGE_RECIPIENT  javni age ključ (age1...)  — ILI —  BACKUP_GPG_RECIPIENT (ID/email)
#   BACKUP_RCLONE_REMOTE  npr. storagebox:autokuca (prazno = samo lokalno, upozorenje)
#   BACKUP_RETENTION_DAYS 30
#   BACKUP_AGE_IDENTITY   (opcionalno) privatni ključ → provjera i dešifrirane kopije
#
# Lozinke se ne pojavljuju u listi procesa: pg_dump radi unutar kontejnera baze preko
# lokalnog socketa. Izlazni kod ≠ 0 ako ijedan backup nije uspio (cron → email/log).
# Lokalni test bez Dockera: AK_PG_LOCAL=1 + PGHOST/PGPORT/PGUSER/PGDATABASE (+ .pgpass).
# =============================================================================
SCRIPT_NAME="backup"
. "$(dirname "$0")/lib.sh"

[[ $# -eq 1 ]] || {
    echo "Upotreba: $0 <ime|all>" >&2
    exit 2
}
require gzip find

# Pokreni PostgreSQL alat u kontejneru baze klijenta (PGUSER/PGDATABASE iz njegovog okruženja).
pg_run() {
    local name="$1"
    shift
    if [[ "${AK_PG_LOCAL:-}" == "1" ]]; then
        "$@"
    else
        dc "$name" exec -T db sh -c \
            'PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" exec "$@"' sh "$@"
    fi
}

# Sadržaj (TOC) arhive: u kontejneru se datoteka šalje kroz stdin, lokalno se čita izravno.
dump_list() {
    local name="$1" file="$2"
    if [[ "${AK_PG_LOCAL:-}" == "1" ]]; then
        pg_restore --list "$file"
    else
        pg_run "$name" pg_restore --list <"$file"
    fi
}

backup_client() {
    local name="$1" dir out_dir retention age_r gpg_r remote storage ts base tmp enc tables
    valid_client_name "$name" || die "neispravno ime klijenta '$name'"
    dir="$(client_dir "$name")"
    [[ -d "$dir" ]] || die "klijent '$name' ne postoji ($dir)"
    out_dir="$dir/data/backups"
    mkdir -p "$out_dir"
    retention="$(setting "$name" BACKUP_RETENTION_DAYS 30)"
    age_r="$(setting "$name" BACKUP_AGE_RECIPIENT)"
    gpg_r="$(setting "$name" BACKUP_GPG_RECIPIENT)"
    remote="$(setting "$name" BACKUP_RCLONE_REMOTE)"
    storage="$(setting "$name" STORAGE_BACKEND local)"
    ts="$(date +%Y%m%d-%H%M%S)"
    base="${name}-${ts}.dump.gz"

    # Nešifrirani dump postoji samo u privremenoj mapi (0700) i briše se i kod greške.
    tmp="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap "rm -rf '$tmp'" EXIT

    log "[$name] pg_dump..."
    pg_run "$name" pg_dump -Fc -Z0 --no-owner | gzip -6 >"$tmp/$base"

    log "[$name] provjera integriteta..."
    gzip -t "$tmp/$base"
    gzip -dc "$tmp/$base" >"$tmp/check.dump"
    dump_list "$name" "$tmp/check.dump" >"$tmp/toc.txt"
    rm -f "$tmp/check.dump"
    tables="$(grep -c " TABLE DATA " "$tmp/toc.txt" || true)"
    grep -q "alembic_version" "$tmp/toc.txt" || die "[$name] dump ne sadrži shemu aplikacije"
    log "[$name] dump ispravan: $tables tablica s podacima, $(du -h "$tmp/$base" | cut -f1)"

    if [[ -n "$age_r" ]]; then
        require age
        enc="$out_dir/$base.age"
        age -r "$age_r" -o "$enc" "$tmp/$base"
    elif [[ -n "$gpg_r" ]]; then
        require gpg
        enc="$out_dir/$base.gpg"
        gpg --batch --yes --quiet --trust-model always -r "$gpg_r" -o "$enc" --encrypt "$tmp/$base"
    else
        die "[$name] nije postavljen BACKUP_AGE_RECIPIENT ni BACKUP_GPG_RECIPIENT — backup se ne sprema nešifriran"
    fi
    chmod 600 "$enc"

    # Provjera dešifrirane kopije kad je privatni ključ dostupan (npr. periodični test vraćanja).
    local identity
    identity="$(setting "$name" BACKUP_AGE_IDENTITY)"
    local verified=false
    if [[ "$enc" == *.age && -n "$identity" && -f "$identity" ]]; then
        age -d -i "$identity" "$enc" | gzip -dc >"$tmp/check.dump"
        verified=true
    elif [[ "$enc" == *.gpg ]] && gpg --batch --list-secret-keys "$gpg_r" >/dev/null 2>&1; then
        gpg --batch --quiet --decrypt "$enc" | gzip -dc >"$tmp/check.dump"
        verified=true
    fi
    if $verified; then
        dump_list "$name" "$tmp/check.dump" | cmp -s - "$tmp/toc.txt" ||
            die "[$name] dešifrirana kopija se ne podudara s dumpom"
        rm -f "$tmp/check.dump"
        log "[$name] dešifrirana kopija provjerena"
    fi
    log "[$name] spremljeno: $enc"

    if [[ -n "$remote" ]]; then
        require rclone
        rclone copy "$enc" "$remote/$name/db/"
        rclone delete --min-age "${retention}d" "$remote/$name/db/"
        if [[ "$storage" == "local" && -d "$dir/data/media" ]]; then
            # Obrisane slike ostaju u media-deleted/<datum> do isteka retencije.
            rclone sync "$dir/data/media" "$remote/$name/media" \
                --backup-dir "$remote/$name/media-deleted/$ts"
            rclone delete --min-age "${retention}d" "$remote/$name/media-deleted/" || true
            rclone rmdirs --leave-root "$remote/$name/media-deleted/" || true
        fi
        log "[$name] kopirano na $remote/$name/"
    else
        warn "[$name] BACKUP_RCLONE_REMOTE nije postavljen — backup postoji samo na ovom serveru"
    fi

    find "$out_dir" -maxdepth 1 -type f -name "${name}-*.dump.gz.*" -mtime "+$retention" -print -delete |
        sed "s/^/[$name] obrisan stari backup: /" || true
    date '+%Y-%m-%d %H:%M:%S' >"$out_dir/last-success.txt"
}

if [[ "$1" == "all" ]]; then
    mapfile -t names < <(list_clients)
    [[ ${#names[@]} -gt 0 ]] || die "nema klijenata u $CLIENTS_DIR"
    failed=()
    for name in "${names[@]}"; do
        (backup_client "$name") || failed+=("$name")
    done
    if [[ ${#failed[@]} -gt 0 ]]; then
        die "backup NIJE uspio za: ${failed[*]}"
    fi
    log "Svi backupi uspješni (${#names[@]})."
else
    backup_client "$1"
fi
