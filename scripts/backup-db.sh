#!/bin/bash
# =============================================================================
# Backup PostgreSQL — ECC Recensement
# =============================================================================
#
# Effectue un pg_dump de la base de données depuis le conteneur PostgreSQL,
# sauvegarde le fichier dans ~/backups/ecc2026/ avec un horodatage,
# et supprime les backups de plus de 7 jours.
#
# Usage :
#   ./scripts/backup-db.sh                   # depuis ~/apps/ecc2026
#   ./scripts/backup-db.sh /chemin/custom    # dossier de backup personnalisé
#
# Appelé automatiquement par le workflow CD avant chaque déploiement.
# Peut aussi être appelé manuellement ou via cron.
#
# Prérequis :
#   - docker compose fonctionnel
#   - Le conteneur PostgreSQL (ecc-personal) doit être running
#   - Le fichier .env.prod doit contenir POSTGRES_DB, POSTGRES_USER
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${1:-$HOME/backups/ecc2026}"
RETENTION_DAYS=7
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
COMPOSE_FILE="compose.prod.yml"
ENV_FILE=".env.prod"
CONTAINER_NAME="ecc-personal"

# ---------------------------------------------------------------------------
# Fonctions
# ---------------------------------------------------------------------------
log() {
    echo "[backup] $(date '+%Y-%m-%d %H:%M:%S') — $1"
}

die() {
    echo "[backup] ❌ ERREUR : $1" >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Vérifications préalables
# ---------------------------------------------------------------------------
cd "$PROJECT_DIR" || die "Impossible d'accéder à $PROJECT_DIR"

# Vérifier que le fichier .env.prod existe
[ -f "$ENV_FILE" ] || die "Fichier $ENV_FILE introuvable dans $PROJECT_DIR"

# Charger les variables nécessaires depuis .env.prod
# (on extrait uniquement POSTGRES_DB et POSTGRES_USER, sans exécuter le fichier)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")

[ -n "$POSTGRES_DB" ]   || die "POSTGRES_DB non trouvé dans $ENV_FILE"
[ -n "$POSTGRES_USER" ] || die "POSTGRES_USER non trouvé dans $ENV_FILE"

# Vérifier que le conteneur PostgreSQL tourne
docker inspect "$CONTAINER_NAME" --format='{{.State.Status}}' 2>/dev/null | grep -q "running" \
    || die "Le conteneur $CONTAINER_NAME n'est pas en cours d'exécution"

# ---------------------------------------------------------------------------
# Création du backup
# ---------------------------------------------------------------------------
mkdir -p "$BACKUP_DIR"

BACKUP_FILE="$BACKUP_DIR/ecc_${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

log "Début du backup de la base '$POSTGRES_DB'…"
log "Destination : $BACKUP_FILE"

docker exec "$CONTAINER_NAME" \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --no-owner \
        --no-privileges \
        --format=plain \
    | gzip > "$BACKUP_FILE"

# Vérifier que le fichier n'est pas vide
BACKUP_SIZE=$(stat --format=%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
if [ "$BACKUP_SIZE" -lt 100 ]; then
    die "Le fichier de backup est trop petit ($BACKUP_SIZE octets) — le dump a probablement échoué"
fi

log "✅ Backup terminé — $(du -h "$BACKUP_FILE" | cut -f1)"

# ---------------------------------------------------------------------------
# Nettoyage : suppression des backups de plus de N jours
# ---------------------------------------------------------------------------
DELETED_COUNT=$(find "$BACKUP_DIR" -name "ecc_*.sql.gz" -type f -mtime +$RETENTION_DAYS -print -delete | wc -l)

if [ "$DELETED_COUNT" -gt 0 ]; then
    log "🗑  $DELETED_COUNT ancien(s) backup(s) supprimé(s) (rétention : ${RETENTION_DAYS} jours)"
fi

# Afficher les backups restants
log "Backups disponibles :"
ls -lht "$BACKUP_DIR"/ecc_*.sql.gz 2>/dev/null | head -10 || log "(aucun)"

log "Terminé."
