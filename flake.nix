###############################################################
# flake.nix — Workshop-2 ETL Environment (rootless Podman)
# Python 3.12 + uv (requirements.txt) + apache-airflow (Dockerfile) + PostgreSQL + Podman
###############################################################
{
  description = "Workshop-2 — reliable batch ETL (Airflow 3.1.8 + Great Expectations)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };

      pythonEnv = pkgs.python312;

      extraLibs = [
        pkgs.stdenv.cc.cc.lib
        pkgs.zlib
      ];
      libPath = pkgs.lib.makeLibraryPath extraLibs;

      # Debe coincidir con `FROM apache/airflow:<version>` del Dockerfile
      airflowVersion = "3.1.8";
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          pythonEnv
          pkgs.uv
          pkgs.postgresql_16
          pkgs.podman
          pkgs.podman-compose
        ];

        shellHook = ''
          export LD_LIBRARY_PATH="${libPath}:$LD_LIBRARY_PATH"

          if [ ! -d .venv ]; then
            uv venv --python "$(command -v python3)"
          fi

          stamp_file=.venv/.deps.stamp
          deps_id="$(cat requirements.txt requirements-dev.txt | sha256sum | cut -d' ' -f 1)-${airflowVersion}"
          if [ ! -f "$stamp_file" ] || [ "$(cat "$stamp_file")" != "$deps_id" ]; then
            echo "[flake] Instalando requirements.txt + requirements-dev.txt + apache-airflow==${airflowVersion} ..."
            uv pip install --python .venv/bin/python \
              --no-progress \
              -r requirements.txt \
              -r requirements-dev.txt \
              "apache-airflow==${airflowVersion}"
            printf '%s' "$deps_id" > "$stamp_file"
          fi

          unset _OLD_VIRTUAL_PATH _OLD_VIRTUAL_PYTHONHOME
          source .venv/bin/activate

          echo ""
          echo "╔══════════════════════════════════════════════════════════╗"
          echo "║                        Airflow-ETL                       ║"
          echo "╚══════════════════════════════════════════════════════════╝"
          echo ""
          echo "Python:  $(python --version)"
          echo "uv:      $(uv --version)"
          echo "Airflow: $(python -c 'import airflow; print(airflow.__version__)' 2>/dev/null)"
          echo "psql:    $(psql --version | head -1)"
          echo ""
          echo "Comandos (Podman, sin docker):"
          echo "  podman compose up -d --build         Levantar infraestructura"
          echo "  podman compose --profile debug run --rm airflow-cli <cmd>"
          echo "  podman compose logs -f               Ver logs"
          echo "  podman compose down                  Parar (volumes intactos)"
          echo "  airflow dags list                    DAGs (local)"
          echo "  uv pip install -r requirements.txt   Añadir dependencia"
          echo ""
          echo "Stack: apache-airflow ${airflowVersion}, pandas, great_expectations"
          echo ""
          echo "Puertos expuestos en 0.0.0.0 (VM Windows 11):"
          echo "  5432  PostgreSQL music_dw  (Power BI: servidor 192.168.1.14, base music_dw)"
          echo "  8080  Airflow UI / API     (http://192.168.1.14:8080)"
          echo "  8088  Apache Superset      (http://192.168.1.14:8088, admin/admin)"
          echo "  firewall: services.network.firewall.allowedTCPPorts en env.nix"
          echo ""
          echo "Tests:  ./run.sh test        (pytest: unit + integration)"
          echo ""
        '';
      };
    };
}
