#!/usr/bin/env bash
# =============================================================================
# Novi klijent na VPS-u:  deploy/new-client.sh <ime> <domena> [--demo] [--admin-email X]
#
#   deploy/new-client.sh autokuca-horvat auto-horvat.hr
#
# 1. clients/<ime>/: docker-compose.yml (iz predloška), .env s generiranim tajnama,
#    data/media, data/backups, overrides/
# 2. deploy/caddy/sites/<ime>.caddy + reload zajedničkog Caddyja
# 3. pokreće app + db (migracije i seed postavki rade se u entrypointu; --demo = demo podaci)
# 4. ispisuje podatke za prvu prijavu i checklistu (docs/ONBOARDING-KLIJENTA.md)
# =============================================================================
SCRIPT_NAME="new-client"
. "$(dirname "$0")/lib.sh"

usage() {
    echo "Upotreba: $0 <ime> <domena> [--demo] [--admin-email adresa]" >&2
    echo "  ime:    mala slova, brojke i crtica (npr. autokuca-horvat)" >&2
    echo "  domena: npr. auto-horvat.hr (bez https://)" >&2
    exit 2
}

[[ $# -ge 2 ]] || usage
NAME="$1"
DOMAIN="$2"
shift 2
DEMO=false
ADMIN_EMAIL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --demo) DEMO=true ;;
        --admin-email)
            ADMIN_EMAIL="${2:-}"
            shift
            ;;
        *) usage ;;
    esac
    shift
done

valid_client_name "$NAME" || die "neispravno ime klijenta '$NAME'"
[[ "$DOMAIN" =~ ^([a-z0-9-]+\.)+[a-z]{2,}$ ]] || die "neispravna domena '$DOMAIN'"
require docker head od tr sed

DIR="$(client_dir "$NAME")"
[[ ! -e "$DIR" ]] || die "$DIR već postoji"
SITE_FILE="$CADDY_DIR/sites/$NAME.caddy"
[[ ! -e "$SITE_FILE" ]] || die "$SITE_FILE već postoji"
grep -rqsE "^${DOMAIN//./\\.}([ ,]|$)" "$CADDY_DIR/sites/" && die "domena $DOMAIN je već dodijeljena"

# Slika aplikacije: izgradi iz repozitorija ako je nema.
if ! docker image inspect "$AUTOKUCA_IMAGE" >/dev/null 2>&1; then
    log "Gradim sliku $AUTOKUCA_IMAGE ..."
    docker build -t "$AUTOKUCA_IMAGE" "$ROOT_DIR"
fi

log "Kreiram $DIR"
mkdir -p "$DIR/data/media" "$DIR/data/backups" "$DIR/overrides/templates" "$DIR/overrides/static"
cp "$DEPLOY_DIR/client-template/docker-compose.yml" "$DIR/docker-compose.yml"

SECRET_KEY="$(random_hex 32)"
POSTGRES_PASSWORD="$(random_hex 24)"
SEED_PASSWORD="$(random_hex 10)-Ak"

umask 077
cat >"$DIR/.env" <<EOF
# Klijent: $NAME — generirano $(date '+%Y-%m-%d %H:%M') (deploy/new-client.sh)
# Tajne su generirane nasumično. Ne commitaj ovu datoteku. Opis varijabli: .env.example
CLIENT=$NAME
COMPOSE_PROJECT_NAME=ak_${NAME//-/_}
AUTOKUCA_IMAGE=$AUTOKUCA_IMAGE

APP_ENV=production
SECRET_KEY=$SECRET_KEY
BASE_URL=https://$DOMAIN
HTTPS=true
TRUST_PROXY=true
DEMO_SEED=$DEMO
SEED_PASSWORD=$SEED_PASSWORD

POSTGRES_USER=autokuca
POSTGRES_DB=autokuca
POSTGRES_PASSWORD=$POSTGRES_PASSWORD

# Email: Brevo (verificiraj domenu: SPF/DKIM/DMARC — docs/ONBOARDING-KLIJENTA.md).
# Dok BREVO_API_KEY nije upisan, emailovi se ne šalju (vidljivi su u logu kao greška).
EMAIL_BACKEND=brevo
EMAIL_FROM=noreply@$DOMAIN
BREVO_API_KEY=

# Slike: local (data/media, ide u backup) ili s3 (R2 / Hetzner Object Storage).
STORAGE_BACKEND=local

# Anti-spam i analitika (opcionalno)
TURNSTILE_SITE_KEY=
TURNSTILE_SECRET_KEY=
UMAMI_SCRIPT_URL=
UMAMI_WEBSITE_ID=

# Dnevno održavanje (retencija) u aplikaciji u 04:00.
MAINTENANCE_IN_APP=true
ADMIN_IP_ALLOWLIST=

# Backup (prazno = vrijednosti iz deploy/backup.env)
BACKUP_AGE_RECIPIENT=
BACKUP_GPG_RECIPIENT=
BACKUP_RCLONE_REMOTE=
EOF
umask 027

# TLS: Cloudflare Origin certifikat ako postoji, inače automatski Let's Encrypt.
CERT_DIR="$CADDY_DIR/certs/$DOMAIN"
TLS_LINE="	# TLS: automatski Let's Encrypt. Iza Cloudflare proxyja → Origin certifikat u
	# deploy/caddy/certs/$DOMAIN/{cert.pem,key.pem} i ponovno generiraj ovu datoteku."
if [[ -f "$CERT_DIR/cert.pem" && -f "$CERT_DIR/key.pem" ]]; then
    TLS_LINE="	tls /etc/caddy/certs/$DOMAIN/cert.pem /etc/caddy/certs/$DOMAIN/key.pem"
    log "Koristim Cloudflare Origin certifikat iz $CERT_DIR"
else
    warn "nema Origin certifikata u $CERT_DIR — Caddy će tražiti Let's Encrypt certifikat"
fi

mkdir -p "$CADDY_DIR/sites"
cat >"$SITE_FILE" <<EOF
# Klijent: $NAME (generirano $(date '+%Y-%m-%d'))
$DOMAIN {
	import autokuca
$TLS_LINE
	reverse_proxy ${NAME}_app:8000
}

www.$DOMAIN {
$TLS_LINE
	redir https://$DOMAIN{uri} permanent
}
EOF

log "Pokrećem kontejnere..."
dc "$NAME" up -d
if ! wait_healthy "$NAME" 240; then
    dc "$NAME" logs --tail 80 app >&2 || true
    die "aplikacija nije postala zdrava — provjeri log iznad (clients/$NAME)"
fi
caddy_reload

if [[ -n "$ADMIN_EMAIL" ]]; then
    ADMIN_PASSWORD="$(random_hex 10)-Ak"
    dc "$NAME" exec -T app python -m app.cli create-superadmin \
        --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD" >/dev/null
fi

cat <<EOF

==============================================================================
 Klijent '$NAME' je pokrenut:  https://$DOMAIN   (admin: https://$DOMAIN/admin)
==============================================================================
 Prva prijava (lozinka je samo u clients/$NAME/.env — promijeni je nakon prijave):
   admin@domena.com / $SEED_PASSWORD
EOF
if [[ -n "$ADMIN_EMAIL" ]]; then
    echo "   $ADMIN_EMAIL / $ADMIN_PASSWORD   (superadmin)"
fi
cat <<EOF
 Prva prijava traži postavljanje 2FA (aplikacija za autentikaciju + kodovi za oporavak).

 Checklista (docs/ONBOARDING-KLIJENTA.md):
  [ ] DNS: A zapis $DOMAIN (+ www) → IP ovog servera, Cloudflare proxy + SSL "Full (strict)"
  [ ] Brevo: domena $DOMAIN verificirana (SPF, DKIM, DMARC), BREVO_API_KEY u .env
  [ ] Postavke: podaci tvrtke (impressum), logo, boje, email za upite
  [ ] Pravni tekstovi pregledani od pravnika + verzija politike privatnosti
  [ ] Potpisan ugovor o obradi podataka (docs/pravno/UGOVOR-O-OBRADI-PODATAKA.md)
  [ ] Vozila unesena, testni upit i newsletter prijava prošli
  [ ] Backup: deploy/backup.sh $NAME prošao, vraćanje testirano
  [ ] Pristupni podaci predani, 2FA postavljena, admin@domena.com deaktiviran ako nije potreban
==============================================================================
EOF
