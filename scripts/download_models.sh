#!/usr/bin/env bash
# ============================================================
# Télécharge les modèles GGUF (hôte, une seule fois).
# Les modèles sont montés en lecture seule dans llama-cpp.
# ============================================================
set -euo pipefail

MODELS_DIR="$(cd "$(dirname "$0")/.." && pwd)/models"
mkdir -p "$MODELS_DIR"

# Gemma 4 E2B (rapide) + E4B (raisonnement) — quantifications Q4_K_M
# Sources : bartowski (GGUF structurés, chat templating inclus)
# NB : la branche do-it-yourself (Transformers -> GGUF) est documentée
#      dans docs/architecture.md (export d'un checkpoint quantifié soi-même).
E2B_URL="${E2B_URL:-https://huggingface.co/bartowski/gemma-4-2b-it-GGUF/resolve/main/gemma-4-2b-it-Q4_K_M.gguf}"
E4B_URL="${E4B_URL:-https://huggingface.co/bartowski/gemma-4-4b-it-GGUF/resolve/main/gemma-4-4b-it-Q4_K_M.gguf}"
EMB_URL="${EMB_URL:-https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-GGUF/resolve/main/bge-small-en-v1.5-f16.gguf}"

echo "==> Modèles → $MODELS_DIR"
echo "    E2B : $E2B_URL"

if [ ! -f "$MODELS_DIR/gemma-4-2b-it-Q4_K_M.gguf" ]; then
  echo "    téléchargement E2B…"
  curl -L --fail --retry 3 -o "$MODELS_DIR/gemma-4-2b-it-Q4_K_M.gguf" "$E2B_URL"
else
  echo "    E2B présent, skip"
fi

if [ ! -f "$MODELS_DIR/gemma-4-4b-it-Q4_K_M.gguf" ]; then
  echo "==> E4B : $E4B_URL"
  echo "    téléchargement E4B (4,6 Go)…"
  curl -L --fail --retry 3 -o "$MODELS_DIR/gemma-4-4b-it-Q4_K_M.gguf" "$E4B_URL"
else
  echo "    E4B présent, skip"
fi

if [ ! -f "$MODELS_DIR/bge-small-en-v1.5-f16.gguf" ]; then
  echo "==> Embeddings : $EMB_URL"
  echo "    téléchargement BGE-small…"
  curl -L --fail --retry 3 -o "$MODELS_DIR/bge-small-en-v1.5-f16.gguf" "$EMB_URL"
else
  echo "    BGE-small présent, skip"
fi

echo "==> Terminé. Vérifiez :"
ls -lh "$MODELS_DIR"