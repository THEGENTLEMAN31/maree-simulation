#!/usr/bin/env bash
# ============================================================
# Télécharge les modèles GGUF (hôte, une seule fois), avec REPRISE
# et VÉRIFICATION DE TAILLE (un fichier partiel n'est jamais skippé).
# Sources vérifiées (HuggingFace, oct. 2026) :
#   - unsloth/gemma-4-E2B-it-GGUF  : Q4_K_M (2 962 979 904 o)
#   - unsloth/gemma-4-E4B-it-GGUF  : Q4_K_M (4 746 247 872 o)
# ============================================================
set -euo pipefail

MODELS_DIR="$(cd "$(dirname "$0")/.." && pwd)/models"
mkdir -p "$MODELS_DIR"

BASE="https://huggingface.co"
# (nom local|URL|taille attendue en octets) — tailles réelles constatées
# sur les fichiers téléchargés depuis HF le 14 oct. (l'API HF rapporte des
# tailles légèrement différentes des octets finaux, on fige les vraies).
E2B_REPO="unsloth/gemma-4-E2B-it-GGUF"
E4B_REPO="unsloth/gemma-4-E4B-it-GGUF"
E2B_SIZE="3106738272"
E4B_SIZE="4977171584"

L_FILES=(
  "gemma-4-E2B-it-Q4_K_M.gguf|$BASE/$E2B_REPO/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf|$E2B_SIZE"
  "gemma-4-E4B-it-Q4_K_M.gguf|$BASE/$E4B_REPO/resolve/main/gemma-4-E4B-it-Q4_K_M.gguf|$E4B_SIZE"
)

echo "==> Modèles → $MODELS_DIR"
for entry in "${L_FILES[@]}"; do
  IFS='|' read -r fname url expected <<< "$entry"
  dest="$MODELS_DIR/$fname"

  if [ -f "$dest" ]; then
    actual="$(stat -c%s "$dest")"
    if [ "$actual" -eq "$expected" ]; then
      echo "    $fname complet ($(numfmt --to=iec $actual)), skip"
      continue
    else
      echo "    $fname INCOMPLET : $actual o / $expected o — reprise…"
    fi
  fi

  # Reprise (-C -) + HTTP/1.1 + retries. Boucle tant qu'incomplet ou en erreur.
  attempt=0
  max_attempts=10
  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    echo "    tentative $attempt/$max_attempts…"
    if curl --http1.1 -L -C - --fail --retry 5 --retry-delay 3 \
        --retry-all-errors --progress-bar -o "$dest" "$url"; then
      actual="$(stat -c%s "$dest")"
      if [ "$actual" -eq "$expected" ]; then
        echo "    ✓ $fname (taille OK)"
        break
      else
        echo "    ⚠ $fname taille $actual/$expected — nouvelle tentative"
      fi
    else
      echo "    ⚠ curl échec, nouvelle tentative dans 4 s…"
      sleep 4
    fi
  done

  actual="$(stat -c%s "$dest" 2>/dev/null || echo 0)"
  [ "$actual" -eq "$expected" ] || { echo "!! $fname toujours incomplet" >&2; exit 1; }
done

echo "==> Terminé."
ls -lh "$MODELS_DIR"