#!/usr/bin/env bash
# ============================================================
# MARÉE — test de bout en bout de la chaîne réelle.
#
#   1. nettoie les conteneurs compose et le journal du run e2e ;
#   2. démarre Redpanda, llama.cpp (E2B réel), python-sim et le
#      client Godot de test ;
#   3. vérifie les assertions Godot (D1/D2/B2/D3) ;
#   4. attend la fin du run et rejoue le journal (E3) ;
#   5. affiche les traces des commandes reçues par l'orchestrateur.
#
# Prérequis : images construites (make build ou docker compose build).
# ============================================================
set -uo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.e2e.yml)
LOG_DIR=/tmp/opencode/maree-logs
RUN_ID=${E2E_RUN_ID:-e2e_godot}
export E2E_CONFIG=${E2E_CONFIG:-e2e-godot.yaml}
mkdir -p "$LOG_DIR"

echo "=== [0/6] config=$E2E_CONFIG run_id=$RUN_ID ==="

echo "=== [1/6] nettoyage ==="
"${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
docker run --rm -v maree-simulation_sim-logs:/logs \
  --entrypoint sh maree-simulation-python-sim \
  -c "rm -f /logs/${RUN_ID}.events.jsonl" >/dev/null 2>&1 || true

echo "=== [2/6] démarrage de la stack ==="
"${COMPOSE[@]}" up -d redpanda llama-cpp python-sim godot-headless 2>&1 | tail -6

echo "=== [3/6] attente du client Godot (max 15 min) ==="
timeout 900 docker wait maree-godot-headless > "$LOG_DIR/e2e-godot.exit" 2>&1
GEXIT=$(tr -dc '0-9' < "$LOG_DIR/e2e-godot.exit")
GEXIT=${GEXIT:-1}
echo "godot exit=$GEXIT"
docker logs maree-godot-headless > "$LOG_DIR/e2e-godot.log" 2>&1
grep -E "OK   -|FAIL -|RESULTAT|\[e2e\]" "$LOG_DIR/e2e-godot.log" | tail -30

echo "=== [4/6] attente de la fin du run python-sim (max 15 min) ==="
timeout 900 docker wait maree-python-sim > /dev/null 2>&1 || true

echo "=== [5/6] rejeu du journal (E3) ==="
"${COMPOSE[@]}" run --rm --no-deps python-sim \
  python -m src.cli replay --run-id "$RUN_ID" --log-dir /logs 2>&1 | tail -3

echo "=== [6/6] traces python-sim (commandes reçues, WS, bilan) ==="
docker logs maree-python-sim > "$LOG_DIR/e2e-python.log" 2>&1
grep -E "contrôle reçu|\[ws\]|terminé|Erreur|Traceback" "$LOG_DIR/e2e-python.log" | tail -20

if [ "$GEXIT" = "0" ]; then
  echo "E2E: SUCCES"
  exit 0
fi
echo "E2E: ECHEC (godot exit=$GEXIT) — logs : $LOG_DIR/e2e-godot.log"
exit 1
