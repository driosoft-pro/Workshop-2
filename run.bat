@echo off
rem ============================================================================
rem Workshop-2 - Reliable Batch Data Pipeline (Spotify x Grammy Awards)
rem Windows entry point (Docker Desktop or Podman machine).
rem
rem   run.bat up        levanta el stack (Airflow + PostgreSQL + Superset)
rem   run.bat test      pytest (unit + integracion si la BD esta disponible)
rem   run.bat trigger   dispara el DAG (Test A)
rem   run.bat prune     poda basura y deja solo 2 copias por carpeta
rem   run.bat help      todos los comandos
rem
rem Cada comando de trabajo arranca con una poda automatica (KEEP_COPIES=2);
rem help, prune y los comandos de limpieza/bajada la saltan.
rem ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not defined KEEP_COPIES set "KEEP_COPIES=2"

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

rem --- poda automatica al inicio de cada comando -----------------------------
rem Se salta en help, prune (es la poda) y los comandos de limpieza/bajada,
rem que ya limpian ellos mismos y no deben podar antes de su confirmacion.
set "SKIP_PRUNE="
for %%c in (prune down stop clean clean-all clean-airflow clean-db clean-data reset fresh) do (
  if /i "%1"=="%%c" set "SKIP_PRUNE=1"
)
if not defined SKIP_PRUNE call :prune

if "%1"=="up" goto :up
if "%1"=="down" goto :down
if "%1"=="stop" goto :down
if "%1"=="fresh" goto :fresh
if "%1"=="clean" goto :cleanall
if "%1"=="clean-all" goto :cleanall
if "%1"=="clean-airflow" goto :cleanairflow
if "%1"=="clean-db" goto :cleandb
if "%1"=="clean-data" goto :cleandata
if "%1"=="prune" goto :prunecmd
if "%1"=="reset" goto :reset
if "%1"=="ports" goto :ports
if "%1"=="check-ports" goto :ports
if "%1"=="status" goto :status
if "%1"=="source" goto :source
if "%1"=="trigger" goto :trigger
if "%1"=="trigger-bad" goto :triggerbad
if "%1"=="trigger-fuzzy" goto :triggerfuzzy
if "%1"=="validate" goto :validate
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
rem Si music_dw esta vacio (nuevo entorno), inicializa el pipeline y espera
call :dwready
if errorlevel 1 (
  echo [run] inicializando Data Warehouse mediante el pipeline ETL ^(Test A^)...
  call :trigger
  echo [run] esperando a que el pipeline pueble music_dw...
  for /l %%i in (1,1,30) do (
    call :dwready
    if not errorlevel 1 goto :dw_is_ready
    timeout /t 3 /nobreak >nul
  )
)
:dw_is_ready
call :dwready
if not errorlevel 1 (
  call :superset
) else (
  echo [run] AVISO: el pipeline aun esta procesando. Cuando finalice ejecuta: run.bat superset
)
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
call :compose_down_quiet
echo [run] servicios del proyecto detenidos (volumenes conservados)
goto :eof

:dwready
rem 0 = music_dw ya tiene la tabla del DW, 1 = DW vacio (o BD no disponible).
%COMPOSE% -f docker-compose.yaml exec -T music-postgres psql -U music -d music_dw -Atc "select to_regclass('public.fact_grammy_award')" 2>nul | findstr /c:"fact_grammy_award" >nul
if errorlevel 1 exit /b 1
exit /b 0

:compose_down_quiet
rem podman-compose imprime ruido benigno al desmantelar ("no container with
rem name or ID ...", "unable to find pod ..."). Se filtra SOLO eso; lo demas
rem de stderr se muestra tal cual y el codigo de salida se conserva.
set "ERRF=%TEMP%\workshop2_compose_%RANDOM%.err"
%COMPOSE% -f docker-compose.yaml %* 2>"%ERRF%"
set "DOWN_RC=%ERRORLEVEL%"
if exist "%ERRF%" (
  findstr /v /c:"no container with name or ID" /c:"no container with ID or name" /c:"unable to find pod" /c:"Executing external compose provider" "%ERRF%" 1>&2
  del /q "%ERRF%" >nul 2>nul
)
if not "%DOWN_RC%"=="0" exit /b %DOWN_RC%
exit /b 0

:cleanairflow
echo [run] limpiando logs de Airflow ...
if exist logs (
  del /f /q /s logs\* >nul 2>nul
  for /d %%p in (logs\*) do rmdir /s /q "%%p" 2>nul
)
if not exist logs mkdir logs
echo [run] logs de Airflow eliminados
goto :eof

:cleandata
echo [run] limpiando datos intermedios y de salida ...
if exist data\work (
  del /f /q /s data\work\* >nul 2>nul
  for /d %%p in (data\work\*) do rmdir /s /q "%%p" 2>nul
)
if exist data\output (
  del /f /q /s data\output\* >nul 2>nul
  for /d %%p in (data\output\*) do rmdir /s /q "%%p" 2>nul
)
if exist data\bad (
  del /f /q /s data\bad\* >nul 2>nul
  for /d %%p in (data\bad\*) do rmdir /s /q "%%p" 2>nul
)
if exist gx\uncommitted (
  del /f /q /s gx\uncommitted\* >nul 2>nul
  for /d %%p in (gx\uncommitted\*) do rmdir /s /q "%%p" 2>nul
)
if not exist data\work mkdir data\work
if not exist data\output mkdir data\output
if not exist data\bad mkdir data\bad
echo [run] datos intermedios y de salida eliminados
goto :eof

:cleandb
call :compose_down_quiet down -v --remove-orphans
echo [run] bases de datos y contenedores eliminados
goto :eof

:cleanall
call :compose_down_quiet down -v --remove-orphans
call :cleanairflow
call :cleandata
echo [run] entorno completamente limpio desde cero
goto :eof

:fresh
call :cleanall
call :up
goto :eof

:reset
goto :cleanall

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
echo [run] activando y disparando reliable_music_pipeline (Test A) ...
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver airflow dags unpause reliable_music_pipeline
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline
goto :eof

:triggerbad
%PY% -m scripts.make_bad_data
echo [run] activando y disparando el Test B (fallo controlado, bad_musical_pipeline) ...
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver airflow dags unpause bad_musical_pipeline
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver airflow dags trigger bad_musical_pipeline
goto :eof

:triggerfuzzy
echo [run] disparando reliable_music_pipeline con enable_fuzzy=true ...
%COMPOSE% -f docker-compose.yaml exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline --conf "{\"enable_fuzzy\":true}"
goto :eof

:validate
%PY% -m scripts.validate_report %2 %3 %4 %5
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

:prune
rem --- basura + rotacion de copias (KEEP_COPIES por carpeta) -----------------
rem Nunca toca data\raw, data\work, data\output, .env, .venv, docs\evidence\runs
rem ni kpis, y preserva los JSON de Test A/B/C citados en
rem docs\evidence_register.md (data\work y data\output se borran solo a mano,
rem con clean-data / clean-all).
where powershell >nul 2>nul
if errorlevel 1 (
  echo [run] aviso: powershell no disponible, poda omitida
  goto :eof
)
echo [run] poda: conservando %KEEP_COPIES% copias por carpeta y eliminando basura ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$k=0; if($env:KEEP_COPIES -match '^[1-9][0-9]*$'){$k=[int]$env:KEEP_COPIES}; if($k -lt 1){$k=1}; $junk=@('__pycache__','.pytest_cache','.ruff_cache','.mypy_cache'); $skip=@('.venv','.git'); $gx='docs\evidence\gx'; if(Test-Path -LiteralPath $gx){Get-ChildItem -LiteralPath $gx -Directory | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -File -Filter '*.json' | Where-Object { $_.Name -notlike '*_test_a_success.json' -and $_.Name -notlike '*_test_b_critical_failure.json' -and $_.Name -notlike '*_test_c_safe_rerun.json' } | Sort-Object LastWriteTime -Descending | Select-Object -Skip $k | Remove-Item -Force }}; if(Test-Path -LiteralPath 'logs'){Get-ChildItem -LiteralPath 'logs' -Directory | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Directory -Filter 'run_id=*' | Sort-Object LastWriteTime -Descending | Select-Object -Skip $k | Remove-Item -Recurse -Force }}; Get-ChildItem -LiteralPath . -Directory -Force | Where-Object { $skip -notcontains $_.Name } | ForEach-Object { if($junk -contains $_.Name){ Remove-Item -LiteralPath $_.FullName -Recurse -Force } else { Get-ChildItem -LiteralPath $_.FullName -Directory -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { $junk -contains $_.Name } | Remove-Item -Recurse -Force; Get-ChildItem -LiteralPath $_.FullName -File -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.pyc','.pyo','.tmp','.swp' -or $_.Name.EndsWith('~') } | Remove-Item -Force } }; foreach($d in @('gx\uncommitted','data\bad')){ if(Test-Path -LiteralPath $d){ Get-ChildItem -LiteralPath $d -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force } }" >nul 2>&1
echo [run] poda completada
goto :eof

:prunecmd
goto :eof

:usage
echo Uso: run.bat ^<comando^>
echo(
echo   up                  .env + libera puertos + compose up -d --build + source prep
echo                         (+ superset si music_dw ya tiene tablas; si no avisa y sigue)
echo   down ^| stop         para TODOS los servicios del proyecto (volumenes intactos)
echo   fresh               limpieza TOTAL y arranque desde cero (clean-all + up)
echo   clean-all           limpieza TOTAL (contenedores, BDs, logs de Airflow y datos temporales)
echo   clean-airflow       limpia solo los logs de Airflow (logs\)
echo   clean-db            para contenedores y borra volumenes de bases de datos
echo   clean-data          limpia datos de trabajo y salida (data\work, output, bad, gx)
echo   prune               poda basura y deja solo 2 copias por carpeta (KEEP_COPIES)
echo   clean               alias de clean-all
echo   reset               alias de clean-all
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
