@echo off
rem ============================================================================
rem Workshop-2 - Reliable Batch Data Pipeline (Spotify x Grammy Awards)
rem Windows entry point (Docker Desktop or Podman machine).
rem
rem   run.bat up        levanta el stack (Airflow + PostgreSQL + Superset)
rem   run.bat test      pytest (unit + integracion si la BD esta disponible)
rem   run.bat trigger   dispara el DAG (Test A)
rem   run.bat help      todos los comandos
rem ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem --- proveedor compose (podman si existe, si no docker) -------------------
set "COMPOSE="
where podman >nul 2>nul && podman compose version >nul 2>nul && set "COMPOSE=podman compose"
if not defined COMPOSE (
  where docker >nul 2>nul && set "COMPOSE=docker compose"
)
if not defined COMPOSE (
  echo [run] ERROR: ni "podman compose" ni "docker compose" disponibles
  exit /b 1
)

rem --- python ----------------------------------------------------------------
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if "%1"=="" goto :usage
if "%1"=="help" goto :usage

if "%1"=="up" goto :up
if "%1"=="down" goto :down
if "%1"=="stop" goto :down
if "%1"=="reset" goto :reset
if "%1"=="ports" goto :ports
if "%1"=="check-ports" goto :ports
if "%1"=="status" goto :status
if "%1"=="source" goto :source
if "%1"=="trigger" goto :trigger
if "%1"=="trigger-bad" goto :triggerbad
if "%1"=="test" goto :test
if "%1"=="unit" goto :unit
if "%1"=="smoke" goto :smoke
if "%1"=="bad" goto :bad
if "%1"=="superset" goto :superset
if "%1"=="dags" goto :dags
if "%1"=="logs" goto :logs

echo [run] comando desconocido: %1
goto :usage

:up
if not exist .env (
  copy .env.example .env >nul
  echo [run] creado .env desde .env.example
)
call :ports
%COMPOSE% -f docker-compose.yaml up -d --build
if errorlevel 1 exit /b 1
echo [run] esperando servicios ...
timeout /t 30 /nobreak >nul
call :source
call :superset
call :status
goto :eof

:ports
set "ENGINE=podman"
where podman >nul 2>nul || set "ENGINE=docker"
for %%I in ("%CD%") do set "PROJECT=%%~nxI"
echo [run] validando puertos requeridos: 5432 8080 8088 (motor: %ENGINE%, proyecto: %PROJECT%)
for %%P in (5432 8080 8088) do (
  for /f "tokens=1,2,3 delims=|" %%a in ('%ENGINE% ps --format "{{.ID}}^|{{.Names}}^|{{.Ports}}" 2^>nul') do (
    echo %%c| findstr /c":%%P->" >nul
    if not errorlevel 1 (
      echo %%b| findstr /r /i /c:"^%PROJECT%[-_]" >nul
      if errorlevel 1 (
        echo [run] conflicto en :%%P -^> %%b (contenedor ajeno) - deteniendo ...
        %ENGINE% stop %%a >nul
        if errorlevel 1 (echo [run] ERROR: no se pudo detener %%b >&2) else echo [run]   detenido: %%b
      ) else (
        echo [run]   :%%P -^> %%b (de este proyecto)
      )
    )
  )
)
echo [run] puertos listos: 5432 8080 8088
goto :eof

:down
%COMPOSE% -f docker-compose.yaml down
echo [run] servicios del proyecto detenidos (volumenes conservados)
goto :eof

:reset
%COMPOSE% -f docker-compose.yaml down -v
echo [run] volumenes eliminados (estado del DW borrado)
goto :eof

:status
%COMPOSE% -f docker-compose.yaml ps
echo(
echo   Airflow UI : http://localhost:8080   (airflow / airflow)
echo   Superset UI : http://localhost:8088   (admin / admin)
echo   PostgreSQL  : localhost:5432          (music / music -^> music_dw)
goto :eof

:source
echo [run] preparacion de la fuente Grammy (CSV -^> music_source) ...
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver python -m scripts.prepare_source_db
goto :eof

:trigger
echo [run] disparando reliable_music_pipeline (Test A) ...
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline
goto :eof

:triggerbad
%PY% -m scripts.make_bad_data
echo [run] disparando el Test B (fallo controlado, spotify_bad.csv) ...
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline --conf "{\"spotify_source_file\":\"spotify_bad.csv\"}"
goto :eof

:test
%PY% -m pytest %2 %3 %4 %5
goto :eof

:unit
%PY% -m pytest -m "not integration" %2 %3 %4 %5
goto :eof

:smoke
%PY% -m scripts.smoke_test %2 %3 %4 %5
goto :eof

:bad
%PY% -m scripts.make_bad_data
goto :eof

:superset
echo [run] bootstrap de Superset (datasets + charts + dashboard) ...
%COMPOSE% -f docker-compose.yaml exec -T superset python /app/scripts/superset_bootstrap.py
goto :eof

:dags
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver airflow dags list
goto :eof

:logs
set "SVC=%2"
if "%SVC%"=="" set "SVC=airflow-scheduler"
%COMPOSE% -f docker-compose.yaml logs -f %SVC%
goto :eof

:usage
echo Uso: run.bat ^<comando^>
echo(
echo   up                  .env + libera puertos + compose up -d --build + source prep + superset bootstrap
echo   down ^| stop         para TODOS los servicios del proyecto (volumenes intactos)
echo   reset               para el stack y borra los volumenes
echo   ports               valida contenedores/puertos activos y detiene los ajenos
echo   status              estado de contenedores y URLs
echo   source              re-importa el CSV de Grammy a music_source
echo   trigger             DAG Test A (corrida exitosa)
echo   trigger-bad         genera spotify_bad.csv y dispara el Test B
echo   test [pytest args]  pruebas unitarias + de integracion
echo   unit  [pytest args] solo pruebas offline
echo   smoke [args]        pipeline local sin Airflow
echo   bad                 crea data\bad\spotify_bad.csv
echo   superset            re-ejecuta el bootstrap de Superset
echo   dags                lista los DAGs de Airflow
echo   logs [servicio]     logs en vivo
exit /b 0
