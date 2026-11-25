#!/usr/bin/env bash
# Capture headless de scenes/main.tscn et contrôle du PNG produit.
#
#   tools/capture.sh                       # -> captures/main_<horodatage>.png
#   MAREE_CAPTURE_W=1280 MAREE_CAPTURE_H=800 tools/capture.sh
#   MAREE_CAPTURE_PATH=captures/essai.png tools/capture.sh
#   MAREE_WS_URL=ws://127.0.0.1:8765 tools/capture.sh   # scène peuplée
#
# `--headless` est volontairement absent : son pilote de rendu factice
# renvoie une texture nulle. La capture utilise `--rendering-driver opengl3`
# et aucun DISPLAY n'est transmis au processus Godot.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
godot_bin="${GODOT_BIN:-godot}"

command -v "$godot_bin" >/dev/null 2>&1 || {
	echo "capture : binaire Godot introuvable ($godot_bin)" >&2
	exit 1
}

mkdir -p "$root/captures"
out="${MAREE_CAPTURE_PATH:-captures/main_$(date -u +%Y%m%d_%H%M%S)_$$.png}"
# Le script GDScript résout les chemins relatifs depuis la racine du dépôt ;
# le shell fait pareil avant de se placer dans godot/project.
if [[ "$out" != /* ]]; then out="$root/$out"; fi
export MAREE_CAPTURE_PATH="$out"
export MAREE_CAPTURE_W="${MAREE_CAPTURE_W:-1000}"
export MAREE_CAPTURE_H="${MAREE_CAPTURE_H:-640}"
export MAREE_CAPTURE_FRAMES="${MAREE_CAPTURE_FRAMES:-30}"
export MAREE_CAPTURE_WAIT_S="${MAREE_CAPTURE_WAIT_S:-0}"

cd "$root/godot/project"
env -u DISPLAY "$godot_bin" \
	--path "$root/godot/project" \
	--rendering-driver opengl3 \
	--no-header \
	--script "$root/tools/capture_scene.gd"

if [[ ! -f "$out" || ! -s "$out" ]]; then
	echo "capture : PNG absent ou vide : $out" >&2
	exit 1
fi
size="$(stat -c %s "$out")"
if (( size <= 5120 )); then
	echo "capture : PNG trop petit ($size octets <= 5120) : $out" >&2
	exit 1
fi
echo "capture : OK $out ($size octets)"
