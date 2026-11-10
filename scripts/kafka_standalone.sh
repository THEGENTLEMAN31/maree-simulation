#!/usr/bin/env bash
# Démarre Apache Kafka (KRaft, nœud unique) **sans Docker**, sur l'hôte.
#
# Prérequis : java (vérifié), réseau pour le téléchargement initial.
# Le journal JSONL reste la source de vérité ; ce broker sert la preuve C1
# (les événements transitent par Kafka) et le flux live Godot.
#
# Usage :
#   scripts/kafka_standalone.sh up     # télécharge (si absent) + lance
#   scripts/kafka_standalone.sh down   # arrête
#   scripts/kafka_standalone.sh status
set -euo pipefail

KAFKA_DIR="${KAFKA_DIR:-/mnt/data/kafka}"
KAFKA_VERSION="${KAFKA_VERSION:-3.9.1}"
PORT="${KAFKA_PORT:-9092}"
CLEANUP="${KAFKA_CLEANUP:-no}"   # "yes" pour repartir d'un dossier vide

resolve_url() {
  local v="$1"
  # downloads.apache.org ne sert parfois pas de HEAD ; archive.apache.org répond.
  for path in \
    "3.9.1/kafka_2.13-3.9.1.tgz" \
    "4.0.0/kafka_2.13-4.0.0.tgz" \
    "3.8.1/kafka_2.13-3.8.1.tgz" \
    ; do
    local url="https://archive.apache.org/dist/kafka/${path}"
    if curl -fsS --max-time 15 -r 0-0 "$url" -o /dev/null; then
      echo "$url"
      return 0
    fi
  done
  echo "[kafka] aucune archive trouvée (ajuster KAFKA_VERSION)" >&2
  return 1
}

ensure_kafka() {
  if [ -d "$KAFKA_DIR/kafka/bin" ]; then
    echo "[kafka] déjà présent dans $KAFKA_DIR/kafka"
    return
  fi
  mkdir -p "$KAFKA_DIR"
  local url
  url="$(resolve_url "$KAFKA_VERSION")"
  echo "[kafka] téléchargement de $url ..."
  curl -fsSL "$url" -o "$KAFKA_DIR/kafka.tgz"
  tar -xzf "$KAFKA_DIR/kafka.tgz" -C "$KAFKA_DIR"
  rm -f "$KAFKA_DIR/kafka.tgz"
  # normaliser le répertoire (kafka_2.13-3.9.1 -> kafka)
  local extracted
  extracted="$(dirname "$(echo "$KAFKA_DIR"/kafka_*/bin | awk '{print $1}')")"
  if [ -d "$KAFKA_DIR/kafka" ]; then rm -rf "$KAFKA_DIR/kafka"; fi
  mv "$extracted" "$KAFKA_DIR/kafka"
  echo "[kafka] installé dans $KAFKA_DIR/kafka"
}

gen_config() {
  local conf="$KAFKA_DIR/kafka/config/kraft-single.properties"
  cat > "$conf" <<EOF
# KRaft single-node (sans Zookeeper), pour hôte unique.
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@127.0.0.1:9093
listeners=PLAINTEXT://127.0.0.1:${PORT},CONTROLLER://127.0.0.1:9093
inter.broker.listener.name=PLAINTEXT
advertised.listeners=PLAINTEXT://127.0.0.1:${PORT}
controller.listener.names=CONTROLLER
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
log.dirs=${KAFKA_DIR}/log
num.partitions=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
log.retention.hours=1
auto.create.topics.enable=true
EOF
  echo "[kafka] config : $conf (port ${PORT})"
}

gen_id() {
  if [ -f "$KAFKA_DIR/cluster.id" ]; then
    cat "$KAFKA_DIR/cluster.id"
  else
    "$KAFKA_DIR/kafka/bin/kafka-storage.sh" random-uuid | tee "$KAFKA_DIR/cluster.id"
  fi
}

do_up() {
  ensure_kafka
  gen_config
  if [ -f "$KAFKA_DIR/run.pid" ] && kill -0 "$(cat "$KAFKA_DIR/run.pid")" 2>/dev/null; then
    echo "[kafka] déjà lancé (pid $(cat "$KAFKA_DIR/run.pid"))"
    return
  fi
  local cluster_id
  cluster_id="$(gen_id)"
  echo "[kafka] formatage du stockage (id=$cluster_id) ..."
  "$KAFKA_DIR/kafka/bin/kafka-storage.sh" format \
    -t "$cluster_id" -c "$KAFKA_DIR/kafka/config/kraft-single.properties" >/dev/null
  echo "[kafka] lancement du nœud ..."
  nohup "$KAFKA_DIR/kafka/bin/kafka-server-start.sh" \
    "$KAFKA_DIR/kafka/config/kraft-single.properties" \
    >"$KAFKA_DIR/kafka.log" 2>&1 &
  echo $! > "$KAFKA_DIR/run.pid"
  echo "[kafka] pid $(cat "$KAFKA_DIR/run.pid"). Attente de 127.0.0.1:${PORT} ..."
  for i in $(seq 1 30); do
    if (echo > /dev/tcp/127.0.0.1/$PORT) 2>/dev/null; then
      echo "[kafka] prêt sur 127.0.0.1:${PORT}."
      return
    fi
    sleep 1
  done
  echo "[kafka] délai dépassé — regarder $KAFKA_DIR/kafka.log" >&2
  return 1
}

do_down() {
  if [ -f "$KAFKA_DIR/run.pid" ]; then
    kill "$(cat "$KAFKA_DIR/run.pid")" 2>/dev/null || true
    rm -f "$KAFKA_DIR/run.pid"
    echo "[kafka] arrêté."
  else
    echo "[kafka] pas de pid — rien à arrêter."
  fi
}

case "${1:-status}" in
  up) do_up ;;
  down) do_down ;;
  status)
    if [ -f "$KAFKA_DIR/run.pid" ] && kill -0 "$(cat "$KAFKA_DIR/run.pid")" 2>/dev/null; then
      echo "[kafka] actif (pid $(cat "$KAFKA_DIR/run.pid"))"
    else
      echo "[kafka] inactif"
    fi
    ;;
  *) echo "usage: $0 up|down|status" >&2; exit 2 ;;
esac