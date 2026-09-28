#!/usr/bin/env bash
# =============================================================================
# Ažuriranje svih klijenata:  deploy/update-all.sh [--pull] [--no-backup] [klijent...]
#
#   (zadano)   git pull + docker build -t $AUTOKUCA_IMAGE .   (slika iz ovog repozitorija)
#   --pull     docker pull $AUTOKUCA_IMAGE                     (slika iz registryja)
#
# Zatim redom za svakog klijenta: backup baze → `up -d` (entrypoint pokreće migracije) →
# čeka /zdravlje (Docker healthcheck). Kod prve greške staje i ispisuje log; klijenti koji
# još nisu ažurirani ostaju na staroj verziji.
# =============================================================================
SCRIPT_NAME="update-all"
. "$(dirname "$0")/lib.sh"

PULL=false
BACKUP=true
TARGETS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pull) PULL=true ;;
        --no-backup) BACKUP=false ;;
        -*)
            echo "Upotreba: $0 [--pull] [--no-backup] [klijent...]" >&2
            exit 2
            ;;
        *) TARGETS+=("$1") ;;
    esac
    shift
done
require docker git

# Prethodna slika ostaje kao :previous (brzi povratak: AUTOKUCA_IMAGE=...:previous u .env).
if docker image inspect "$AUTOKUCA_IMAGE" >/dev/null 2>&1; then
    docker tag "$AUTOKUCA_IMAGE" "${AUTOKUCA_IMAGE%:*}:previous"
fi

if $PULL; then
    log "docker pull $AUTOKUCA_IMAGE"
    docker pull "$AUTOKUCA_IMAGE"
else
    log "git pull + docker build ($AUTOKUCA_IMAGE)"
    git -C "$ROOT_DIR" pull --ff-only
    docker build -t "$AUTOKUCA_IMAGE" "$ROOT_DIR"
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
    mapfile -t TARGETS < <(list_clients)
fi
[[ ${#TARGETS[@]} -gt 0 ]] || die "nema klijenata u $CLIENTS_DIR"

done_list=()
for name in "${TARGETS[@]}"; do
    valid_client_name "$name" || die "neispravno ime klijenta '$name'"
    [[ -d "$(client_dir "$name")" ]] || die "klijent '$name' ne postoji"
    log "=== $name ==="
    if $BACKUP; then
        "$DEPLOY_DIR/backup.sh" "$name" || die "backup za '$name' nije uspio — ažuriranje prekinuto"
    fi
    dc "$name" up -d --remove-orphans
    if ! wait_healthy "$name" 240; then
        dc "$name" logs --tail 100 app >&2 || true
        die "'$name' nije zdrav nakon ažuriranja. Ažurirani: ${done_list[*]:-nitko}. " \
            "Vraćanje: deploy/restore.sh $name <zadnji backup> (i prethodna slika)."
    fi
    done_list+=("$name")
    log "$name: OK"
done
docker image prune -f >/dev/null || true
log "Ažurirano: ${done_list[*]}"
