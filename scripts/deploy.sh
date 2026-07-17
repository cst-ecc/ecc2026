#!/bin/bash
# =============================================================================
# Déploiement — ECC Recensement
# =============================================================================
#
# Séquence de déploiement exécutée sur le VPS par le workflow CD de GitHub
# Actions. Peut aussi être lancé manuellement.
#
# Étapes :
#   1. Backup de la base de données (pg_dump)
#   2. Pull des dernières modifications depuis origin/main
#   3. Build des images Docker (portal + shield)
#   4. Redémarrage des services (down/up)
#   5. Vérification de santé (health check)
#   6. Nettoyage des images Docker inutilisées
#
# Usage :
#   ./scripts/deploy.sh          # déploiement normal
#
# Prérequis :
#   - Git configuré avec accès au dépôt
#   - Docker et docker compose installés
#   - Fichier .env.prod présent
#   - scripts/backup-db.sh présent et exécutable
#
# En cas d'échec :
#   Le script s'arrête à la première erreur (set -e).
#   Les images Docker précédentes restent disponibles pour un rollback manuel.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="compose.prod.yml"
ENV_FILE=".env.prod"
BRANCH="main"
HEALTH_CHECK_RETRIES=30
HEALTH_CHECK_INTERVAL=5

# ---------------------------------------------------------------------------
# Fonctions
# ---------------------------------------------------------------------------
log() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[deploy] $(date '+%Y-%m-%d %H:%M:%S') — $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

die() {
    echo ""
    echo "❌❌❌ ÉCHEC DU DÉPLOIEMENT ❌❌❌"
    echo "[deploy] ERREUR : $1" >&2
    exit 1
}

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

# ---------------------------------------------------------------------------
# Démarrage
# ---------------------------------------------------------------------------
cd "$PROJECT_DIR" || die "Impossible d'accéder à $PROJECT_DIR"

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║         ECC RECENSEMENT — DÉPLOIEMENT EN PRODUCTION            ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Projet  : $PROJECT_DIR"
echo "  Branche : $BRANCH"
echo "  Date    : $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""

# ---------------------------------------------------------------------------
# Étape 1 : Backup de la base de données
# ---------------------------------------------------------------------------
log "ÉTAPE 1/6 — Backup de la base de données"

if [ -x "$SCRIPT_DIR/backup-db.sh" ]; then
    "$SCRIPT_DIR/backup-db.sh" || die "Le backup de la base a échoué. Déploiement annulé."
else
    die "scripts/backup-db.sh non trouvé ou non exécutable"
fi

# ---------------------------------------------------------------------------
# Étape 2 : Pull du code depuis GitHub
# ---------------------------------------------------------------------------
log "ÉTAPE 2/6 — Pull des modifications (origin/$BRANCH)"

# S'assurer qu'on est sur la bonne branche
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    die "La branche active est '$CURRENT_BRANCH', attendue : '$BRANCH'"
fi

# Vérifier qu'il n'y a pas de modifications locales non commitées
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    echo "[deploy] ⚠  Modifications locales détectées — stash automatique"
    git stash push -m "deploy-auto-stash-$(date +%Y%m%d_%H%M%S)"
fi

git pull --ff-only origin "$BRANCH" || die "git pull a échoué (possible divergence)"

echo "[deploy] Commit courant : $(git log --oneline -1)"

# ---------------------------------------------------------------------------
# Étape 3 : Build des images Docker
# ---------------------------------------------------------------------------
log "ÉTAPE 3/6 — Build des images Docker"

compose build --pull || die "docker compose build a échoué"

# ---------------------------------------------------------------------------
# Étape 4 : Redémarrage des services
# ---------------------------------------------------------------------------
log "ÉTAPE 4/6 — Redémarrage des services"

# Arrêter proprement (sans supprimer les volumes !)
compose down --timeout 30

# Relancer tout
compose up -d

echo "[deploy] Services démarrés."

# ---------------------------------------------------------------------------
# Étape 5 : Health check
# ---------------------------------------------------------------------------
log "ÉTAPE 5/6 — Vérification de santé"

echo "[deploy] Attente que le portail Django soit opérationnel…"

for i in $(seq 1 $HEALTH_CHECK_RETRIES); do
    # Vérifier que le conteneur portal est "running" (pas "restarting")
    PORTAL_STATUS=$(docker inspect ecc-portal --format='{{.State.Status}}' 2>/dev/null || echo "absent")

    if [ "$PORTAL_STATUS" = "running" ]; then
        # Vérifier que Gunicorn répond réellement
        if docker exec ecc-portal python -c "
import django
django.setup()
from django.db import connection
connection.ensure_connection()
print('OK')
" 2>/dev/null | grep -q "OK"; then
            echo "[deploy] ✅ Django est opérationnel (tentative $i/$HEALTH_CHECK_RETRIES)"
            break
        fi
    fi

    if [ "$i" -eq "$HEALTH_CHECK_RETRIES" ]; then
        echo "[deploy] Derniers logs du portail :"
        docker logs ecc-portal --tail 50 2>&1 || true
        die "Le portail n'a pas démarré après $((HEALTH_CHECK_RETRIES * HEALTH_CHECK_INTERVAL))s"
    fi

    echo "[deploy] Tentative $i/$HEALTH_CHECK_RETRIES — statut: $PORTAL_STATUS — attente ${HEALTH_CHECK_INTERVAL}s…"
    sleep $HEALTH_CHECK_INTERVAL
done

# Vérifier aussi que nginx (shield) tourne
SHIELD_STATUS=$(docker inspect ecc-shield --format='{{.State.Status}}' 2>/dev/null || echo "absent")
if [ "$SHIELD_STATUS" != "running" ]; then
    echo "[deploy] ⚠  Le conteneur ecc-shield n'est pas running (status: $SHIELD_STATUS)"
    echo "[deploy] Derniers logs :"
    docker logs ecc-shield --tail 20 2>&1 || true
    die "Nginx (shield) ne tourne pas"
fi

echo "[deploy] ✅ Nginx (shield) est opérationnel"

# ---------------------------------------------------------------------------
# Étape 6 : Nettoyage
# ---------------------------------------------------------------------------
log "ÉTAPE 6/6 — Nettoyage"

# Supprimer les images Docker non utilisées (dangling)
CLEANED=$(docker image prune -f 2>/dev/null | tail -1)
echo "[deploy] Images nettoyées : $CLEANED"

# Afficher l'état final
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║              ✅ DÉPLOIEMENT TERMINÉ AVEC SUCCÈS                ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
compose ps
echo ""
echo "  Commit  : $(git log --oneline -1)"
echo "  Date    : $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""
