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
#   ./run.sh prune       poda basura y deja solo 2 copias por carpeta
#   ./run.sh help        todos los comandos
#
# Cada comando de trabajo arranca con una poda automatica (KEEP_COPIES=2);
# help, prune y los comandos de limpieza/bajada la saltan.
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

# --- poda automatica (basura + rotacion de copias) ---------------------------
# KEEP_COPIES = copias que se conservan por carpeta (por defecto 2).
# Nunca toca: data/raw (fuente), data/work, data/output, .env, .venv,
# docs/evidence/runs ni kpis, y preserva los JSON de Test A/B/C citados en
# docs/evidence_register.md (data/work y data/output se borran solo a mano,
# con clean-data / clean-all).
KEEP_COPIES="${KEEP_COPIES:-2}"
[[ "$KEEP_COPIES" =~ ^[1-9][0-9]*$ ]] || KEEP_COPIES=2

_prune_logs() {
  local dag i runs=()
  [ -d logs ] || return 0
  for dag in logs/*/; do
    [ -d "$dag" ] || continue
    mapfile -t runs < <(find "$dag" -mindepth 1 -maxdepth 1 -type d -name 'run_id=*' \
                         -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2-)
    for (( i = KEEP_COPIES; i < ${#runs[@]}; i++ )); do
      rm -rf -- "${runs[$i]}" 2>/dev/null || true
    done
  done
  return 0
}

_prune_evidence() {
  local stage i newest=()
  [ -d docs/evidence/gx ] || return 0
  for stage in docs/evidence/gx/*/; do
    [ -d "$stage" ] || continue
    mapfile -t newest < <(find "$stage" -maxdepth 1 -type f -name '*.json' \
        ! -name '*_test_a_success.json' \
        ! -name '*_test_b_critical_failure.json' \
        ! -name '*_test_c_safe_rerun.json' \
        -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2-)
    for (( i = KEEP_COPIES; i < ${#newest[@]}; i++ )); do
      rm -f -- "${newest[$i]}" 2>/dev/null || true
    done
  done
  return 0
}

_prune_junk() {
  find . -path ./.venv -prune -o -path ./.git -prune -o \
       -type d \( -name '__pycache__' -o -name '.pytest_cache' \
                  -o -name '.ruff_cache' -o -name '.mypy_cache' \) \
       -prune -exec rm -rf {} + 2>/dev/null || true
  find . -path ./.venv -prune -o -path ./.git -prune -o \
       -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.tmp' \
                  -o -name '*.swp' -o -name '*~' \) \
       -exec rm -f {} + 2>/dev/null || true
  rm -rf gx/uncommitted/* data/bad/* 2>/dev/null || true
  return 0
}

cmd_prune() {
  echo "[run] poda: conservando $KEEP_COPIES copias por carpeta y eliminando basura ..."
  _prune_logs
  _prune_evidence
  _prune_junk
  echo "[run] poda completada"
}

get_env() {
  local var="$1" default="$2" envf=".env"
  [ -f "$envf" ] || envf=".env.example"
  local val
  val=$(sed -n "s/^${var}=//p" "$envf" 2>/dev/null | head -1)
  echo "${val:-$default}"
}

get_port() { get_env "$1" "$2"; }

# --- motor de contenedores (podman primero, docker como respaldo) -----------
detect_engine() {
  if [ ! -f "$HOME/.config/containers/registries.conf" ] && [ ! -f "/etc/containers/registries.conf" ]; then
    mkdir -p "$HOME/.config/containers"
    printf 'unqualified-search-registries = ["docker.io"]\n' > "$HOME/.config/containers/registries.conf" 2>/dev/null || true
  fi
  if [ ! -f "$HOME/.config/containers/policy.json" ] && [ ! -f "/etc/containers/policy.json" ]; then
    mkdir -p "$HOME/.config/containers"
    printf '{\n  "default": [\n    {\n      "type": "insecureAcceptAnything"\n    }\n  ]\n}\n' > "$HOME/.config/containers/policy.json" 2>/dev/null || true
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
_compose_cmd() {
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
}

compose() {
  _compose_cmd
  # el wrapper `podman compose` avisa a stderr en cada invocacion; no aporta nada.
  # shellcheck disable=SC2086
  $COMPOSE_CMD -f docker-compose.yaml "$@" \
    2> >(grep -v 'Executing external compose provider' >&2 || true)
}

# Igual que compose, pero filtra el ruido benigno de la desmantelacion
# ("no container with name or ID ...", "no container with ID or name ...",
# "unable to find pod ...") que podman-compose imprime cuando el recurso ya
# no existe. Todo lo demas de stderr se muestra tal cual y el codigo de salida
# real se conserva. No usar para `exec`: ahi ese mensaje si es un fallo real.
compose_teardown() {
  _compose_cmd
  local err rc=0
  err=$(mktemp)
  # shellcheck disable=SC2086
  $COMPOSE_CMD -f docker-compose.yaml "$@" 2>"$err" || rc=$?
  grep -vE 'no container with (name or ID|ID or name)|unable to find pod' \
    "$err" >&2 || true
  rm -f "$err"
  return "$rc"
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

# El DW lo llena el ETL (src/load.py aplica sql/dw_schema.sql en la primera
# corrida del DAG). En un clone/volumen nuevo music_dw existe pero esta vacio,
# y en ese estado el bootstrap de Superset revienta con 500
# (relation "fact_grammy_award" does not exist).
dw_ready() {
  local pg_user
  pg_user=$(get_env "POSTGRES_USER" "music")
  compose exec -T music-postgres \
    psql -U "$pg_user" -d music_dw -Atc "select to_regclass('public.fact_grammy_award')" \
    2>/dev/null | grep -q 'fact_grammy_award'
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
  if dw_ready; then
    cmd_superset
  else
    warn "[run] AVISO: music_dw aun no tiene tablas (fact_grammy_award ausente)."
    warn "[run]          El data warehouse se llena en la primera corrida del DAG;"
    warn "[run]          el bootstrap de Superset se omite en este arranque."
    warn "[run]          Completa la configuracion con:"
    warn "[run]            ./run.sh trigger     # Test A -> carga music_dw"
    warn "[run]            ./run.sh superset    # datasets + charts + dashboard"
  fi
  cmd_status
}

cmd_down() {
  compose_teardown stop || true
  compose_teardown down
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
  compose_teardown down -v --remove-orphans
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
  compose_teardown down -v --remove-orphans
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

  up                  .env + valida/libera puertos + compose up -d --build + fuente
                      (+ superset si music_dw ya tiene tablas; si no avisa y sigue)
  down | stop         baja TODOS los servicios del proyecto (volumenes intactos)
  fresh [--yes]       limpieza TOTAL y arranque desde cero (clean-all + up)
  clean-all [--yes]   limpieza TOTAL (contenedores, BDs, logs de Airflow y datos temporales)
  clean-airflow       limpia solo los logs de Airflow (logs/)
  clean-db [--yes]    baja contenedores y borra volumenes de bases de datos
  clean-data          limpia datos de trabajo y salida (data/work, output, bad, gx)
  prune               poda basura y deja solo 2 copias por carpeta (KEEP_COPIES)
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

# --- poda automatica al inicio de cada comando -------------------------------
# Se salta en: help, prune (es la poda) y los comandos de limpieza/bajada,
# que ya limpian ellos mismos y no deben podar antes de la confirmacion y/N.
case "${1:-help}" in
  help|-h|--help|prune|down|stop|clean|clean-all|clean-airflow|clean-db|clean-data|reset|fresh) ;;
  *) cmd_prune || true ;;
esac

case "${1:-help}" in
  up)           cmd_up ;;
  down|stop)    cmd_down ;;
  fresh)        cmd_fresh ;;
  clean-all)    shift; cmd_clean_all "$@" ;;
  clean-airflow) cmd_clean_airflow ;;
  clean-db)     shift; cmd_clean_db "$@" ;;
  clean-data)   cmd_clean_data ;;
  prune)        cmd_prune ;;
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
