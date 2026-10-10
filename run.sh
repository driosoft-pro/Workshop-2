#!/usr/bin/env bash
# =============================================================================
# Workshop-2 - Reliable Batch Data Pipeline (Spotify x Grammy Awards)
# Single entry point for the whole project (Podman first, Docker fallback).
#
#   ./run.sh up          levanta el stack (valida puertos, Airflow + PG + Superset)
#   ./run.sh down        baja todos los servicios del proyecto (volumenes intactos)
#   ./run.sh ports       valida contenedores/puertos activos y libera conflictos
#   ./run.sh test        pytest (unit + integration si la BD esta disponible)
#   ./run.sh trigger     dispara el DAG (Test A: corrida exitosa)
#   ./run.sh status      estado de contenedores + URLs
#   ./run.sh help        todos los comandos
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"

if [ -z "${CONTAINER_HOST:-}" ] && [ -S "/run/user/$(id -u)/podman/podman.sock" ]; then
  export CONTAINER_HOST="unix:///run/user/$(id -u)/podman/podman.sock"
fi

PROJECT=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]//g')

ASSUME_YES="${ASSUME_YES:-0}"
FILTERED_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--yes" ] || [ "$arg" = "-y" ]; then
    ASSUME_YES=1
  else
    FILTERED_ARGS+=("$arg")
  fi
done
if [ "${#FILTERED_ARGS[@]}" -gt 0 ]; then
  set -- "${FILTERED_ARGS[@]}"
else
  set -- "help"
fi

warn() { echo "$@" >&2; }

get_port() {
  local var="$1" default="$2" envf=".env"
  [ -f "$envf" ] || envf=".env.example"
  local val
  val=$(sed -n "s/^${var}=//p" "$envf" 2>/dev/null | head -1)
  echo "${val:-$default}"
}

# --- motor de contenedores (podman primero, docker como respaldo) -----------
detect_engine() {
  if [ -S "/run/user/$(id -u)/podman/podman.sock" ]; then
    export CONTAINER_HOST="unix:///run/user/$(id -u)/podman/podman.sock"
    if command -v systemctl >/dev/null 2>&1; then
      systemctl --user import-environment PATH >/dev/null 2>&1 || true
    fi
  fi
  if [ -n "${ENGINE_BIN:-}" ]; then return 0; fi
  if command -v podman >/dev/null 2>&1; then ENGINE_BIN="podman"
  elif command -v docker >/dev/null 2>&1; then ENGINE_BIN="docker"
  else echo "[run] ERROR: ni 'podman' ni 'docker' disponibles" >&2; return 1
  fi
}

# puertos que este proyecto debe publicar (del .env si existe)
required_ports() {
  local pg af sp
  pg=$(get_port "MUSIC_POSTGRES_PORT" "5432")
  af=$(get_port "AIRFLOW_PORT" "8080")
  sp=$(get_port "SUPERSET_PORT" "8088")
  echo "${pg} ${af} ${sp} ${EXTRA_PORTS:-}"
}

# --- compose provider -------------------------------------------------------
compose() {
  detect_engine || exit 1
  if [ -z "${COMPOSE_CMD:-}" ]; then
    if command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
      COMPOSE_CMD="podman compose"
    elif command -v docker >/dev/null 2>&1; then
      COMPOSE_CMD="docker compose"
    else
      echo "[run] ERROR: ni 'podman compose' ni 'docker compose' disponibles" >&2
      exit 1
    fi
  fi
  # shellcheck disable=SC2086
  $COMPOSE_CMD -f docker-compose.yaml "$@"
}

# --- python (nix develop si existe el flake, si no el .venv) ----------------
run_python() {
  if [ -f flake.nix ] && command -v nix >/dev/null 2>&1; then
    nix develop -c python "$@"
  elif [ -x .venv/bin/python ]; then
    .venv/bin/python "$@"
  else
    python3 "$@"
  fi
}

wait_http() { # url, intentos
  local url="$1" tries="${2:-60}" i=1
  while [ "$i" -le "$tries" ]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "[run] OK  $url"
      return 0
    fi
    sleep 2
    i=$((i + 1))
  done
  echo "[run] TIMEOUT esperando $url" >&2
  return 1
}

# valida puertos activos: contenedores ajenos que publican un puerto
# requerido se detienen automaticamente (podman/docker); procesos que no
# son contenedores solo se reportan.
cmd_ports() {
  for arg in "$@"; do
    case "$arg" in --yes|-y) export ASSUME_YES=1 ;; esac
  done
  detect_engine || return 1
  local ports port id name pfmt owned=" " stopped=0
  ports=$(required_ports)
  echo "[run] validando puertos requeridos: $ports (motor: $ENGINE_BIN, proyecto: $PROJECT)"
  for port in $ports; do
    while IFS='|' read -r id name pfmt; do
      [ -n "${id:-}" ] || continue
      case "${pfmt:-}" in *":${port}->"*) ;; *) continue ;; esac
      if printf '%s\n' "$name" | grep -qE "^${PROJECT}[-_]"; then
        owned="$owned$port "
        continue
      fi
      echo "[run] conflicto en :$port -> $name (contenedor ajeno)"
      if [ "${ASSUME_YES:-0}" != "1" ]; then
        read -r -p "[run] ¿Detener contenedor ajeno $name en :$port? [y/N] " resp
        case "$resp" in
          [yY][eE][sS]|[yY]) ;;
          *) echo "[run] cancelado por el usuario" >&2; return 1 ;;
        esac
      fi
      echo "[run] deteniendo contenedor ajeno $name ..."
      if "$ENGINE_BIN" stop "$id" >/dev/null 2>&1; then
        echo "[run]   detenido: $name"
        stopped=1
      else
        echo "[run] ERROR: no se pudo detener $name (puerto $port)" >&2
        return 1
      fi
    done < <("$ENGINE_BIN" ps --format '{{.ID}}|{{.Names}}|{{.Ports}}' 2>/dev/null)
  done
  [ "$stopped" -eq 1 ] && sleep 2
  for port in $ports; do
    case "$owned" in *" $port "*) echo "[run]   :$port -> de este proyecto" ;;
      *) if ss -ltn 2>/dev/null | grep -qE "[.:]${port}[[:space:]]"; then
           warn "[run] :$port sigue en escucha por un proceso que no es contenedor:"
           ss -ltnp 2>/dev/null | grep -E "[.:]${port}[[:space:]]" | sed 's/^/         /' || true
         fi ;;
    esac
  done
  echo "[run] puertos listos: $ports"
}

cmd_up() {
  [ -f .env ] || { cp .env.example .env; echo "[run] creado .env desde .env.example"; }
  cmd_ports
  compose up -d --build
  echo "[run] esperando servicios ..."
  local af_port sp_port
  af_port=$(get_port "AIRFLOW_PORT" "8080")
  sp_port=$(get_port "SUPERSET_PORT" "8088")
  wait_http "http://localhost:${af_port}/api/v2/monitor/health" 90 || true
  wait_http "http://localhost:${sp_port}/health" 90 || true
  cmd_source
  cmd_superset
  cmd_status
}

cmd_down() {
  compose stop 2>/dev/null || true
  compose down
  echo "[run] servicios del proyecto detenidos (volumenes conservados)"
}

cmd_clean_airflow() {
  echo "[run] limpiando logs de Airflow ..."
  rm -rf logs/* 2>/dev/null || true
  mkdir -p logs
  echo "[run] logs de Airflow eliminados"
}

cmd_clean_data() {
  echo "[run] limpiando datos intermedios y de salida (work, output, bad, gx) ..."
  rm -rf data/work/* data/output/* data/bad/* gx/uncommitted/* 2>/dev/null || true
  mkdir -p data/work data/output data/bad
  echo "[run] datos intermedios y de salida eliminados"
}

cmd_clean_db() {
  for arg in "$@"; do
    case "$arg" in --yes|-y) export ASSUME_YES=1 ;; esac
  done
  if [ "${ASSUME_YES:-0}" != "1" ]; then
    read -r -p "[run] ¿Eliminar todos los contenedores y volumenes de base de datos? [y/N] " resp
    case "$resp" in
      [yY][eE][sS]|[yY]) ;;
      *) echo "[run] cancelado por el usuario" >&2; return 1 ;;
    esac
  fi
  echo "[run] deteniendo contenedores y eliminando volumenes de base de datos ..."
  compose down -v --remove-orphans
  echo "[run] bases de datos y contenedores eliminados"
}

cmd_clean_all() {
  for arg in "$@"; do
    case "$arg" in --yes|-y) export ASSUME_YES=1 ;; esac
  done
  if [ "${ASSUME_YES:-0}" != "1" ]; then
    read -r -p "[run] ¿Limpieza TOTAL (contenedores, bases de datos, logs de Airflow y datos temporales)? [y/N] " resp
    case "$resp" in
      [yY][eE][sS]|[yY]) ;;
      *) echo "[run] cancelado por el usuario" >&2; return 1 ;;
    esac
  fi
  echo "[run] deteniendo contenedores y eliminando volumenes ..."
  compose down -v --remove-orphans
  echo "[run] limpiando logs de Airflow y datos intermedios ..."
  rm -rf logs/* data/work/* data/output/* data/bad/* gx/uncommitted/* 2>/dev/null || true
  mkdir -p logs data/work data/output data/bad
  echo "[run] entorno completamente limpio desde cero"
}

cmd_fresh() {
  echo "[run] reiniciando todo el entorno desde cero ..."
  cmd_clean_all --yes
  cmd_up
}

cmd_reset() {
  cmd_clean_all "$@"
}
cmd_logs()     { compose logs -f "${1:-airflow-scheduler}"; }
cmd_status()   { compose ps; echo; cmd_urls; }
cmd_urls()     {
  local pg_port af_port sp_port
  pg_port=$(get_port "MUSIC_POSTGRES_PORT" "5432")
  af_port=$(get_port "AIRFLOW_PORT" "8080")
  sp_port=$(get_port "SUPERSET_PORT" "8088")
  echo "  Airflow UI : http://localhost:${af_port}   (airflow / airflow)"
  echo "  Superset UI : http://localhost:${sp_port}   (admin / admin)"
  echo "  PostgreSQL  : localhost:${pg_port}          (music / music -> music_dw, music_source, superset)"
}

cmd_source() {
  echo "[run] preparacion de la fuente Grammy (CSV -> music_source) ..."
  compose exec -T airflow-apiserver python -m scripts.prepare_source_db
}

cmd_trigger() {
  echo "[run] disparando reliable_music_pipeline (Test A) ..."
  compose exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline
}

cmd_trigger_bad() {
  run_python -m scripts.make_bad_data
  echo "[run] disparando el Test B (fallo controlado, spotify_bad.csv) ..."
  compose exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline \
    --conf '{"spotify_source_file":"spotify_bad.csv"}'
}

cmd_trigger_fuzzy() {
  echo "[run] disparando reliable_music_pipeline con enable_fuzzy=true ..."
  compose exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline \
    --conf '{"enable_fuzzy": true}'
}

cmd_test()     { run_python -m pytest "$@"; }
cmd_unit()     { run_python -m pytest -m "not integration" "$@"; }
cmd_smoke()    { run_python -m scripts.smoke_test "$@"; }
cmd_bad()      { run_python -m scripts.make_bad_data; }

cmd_superset() {
  echo "[run] bootstrap de Superset (datasets + charts + dashboard) ..."
  compose exec -T superset python /app/scripts/superset_bootstrap.py
}

cmd_dags()     { compose exec -T airflow-apiserver airflow dags list; }

cmd_validate() {
  run_python -m scripts.validate_report "$@"
}

usage() {
  cat <<'EOF'
Uso: ./run.sh <comando>

  up                  .env + valida/libera puertos + compose up -d --build + fuente + superset
  down | stop         baja TODOS los servicios del proyecto (volumenes intactos)
  fresh [--yes]       limpieza TOTAL y arranque desde cero (clean-all + up)
  clean-all [--yes]   limpieza TOTAL (contenedores, BDs, logs de Airflow y datos temporales)
  clean-airflow       limpia solo los logs de Airflow (logs/)
  clean-db [--yes]    baja contenedores y borra volumenes de bases de datos
  clean-data          limpia datos de trabajo y salida (data/work, output, bad, gx)
  clean [--yes]       alias de clean-all
  reset [--yes]       alias de clean-all
  ports [--yes]       valida contenedores/puertos activos y detiene los ajenos (conflictos)
  status              estado de contenedores y URLs
  urls                URLs de acceso
  source              re-importa el CSV de Grammy a music_source
  trigger             DAG Test A (corrida exitosa)
  trigger-bad         genera spotify_bad.csv y dispara el Test B (fallo controlado)
  trigger-fuzzy       dispara reliable_music_pipeline con enable_fuzzy=true
  validate [args]     corre reporte de validacion automatizado (V1-V16, --superset, --json)
  test [pytest args]  pruebas unitarias + de integracion (auto-skip sin BD)
  unit  [pytest args] solo pruebas offline
  smoke [args]        pipeline local sin Airflow (scripts/smoke_test.py)
  bad                 crea data/bad/spotify_bad.csv
  superset            re-ejecuta el bootstrap de Superset (idempotente)
  dags                lista los DAGs de Airflow
  logs [servicio]     logs en vivo (por defecto airflow-scheduler)
  help                esta ayuda
EOF
}

case "${1:-help}" in
  up)           cmd_up ;;
  down|stop)    cmd_down ;;
  fresh)        cmd_fresh ;;
  clean-all)    shift; cmd_clean_all "$@" ;;
  clean-airflow) cmd_clean_airflow ;;
  clean-db)     shift; cmd_clean_db "$@" ;;
  clean-data)   cmd_clean_data ;;
  clean)        shift; cmd_clean_all "$@" ;;
  reset)        shift; cmd_reset "$@" ;;
  ports|check-ports) shift; cmd_ports "$@" ;;
  status)       cmd_status ;;
  urls)         cmd_urls ;;
  source)       cmd_source ;;
  trigger)      cmd_trigger ;;
  trigger-bad)  cmd_trigger_bad ;;
  trigger-fuzzy) cmd_trigger_fuzzy ;;
  validate)     shift; cmd_validate "$@" ;;
  test)         shift; cmd_test "$@" ;;
  unit)         shift; cmd_unit "$@" ;;
  smoke)        shift; cmd_smoke "$@" ;;
  bad)          cmd_bad ;;
  superset)     cmd_superset ;;
  dags)         cmd_dags ;;
  logs)         shift; cmd_logs "$@" ;;
  help|-h|--help) usage ;;
  *) echo "comando desconocido: $1" >&2; usage; exit 1 ;;
esac
