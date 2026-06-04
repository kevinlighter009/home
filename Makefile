.PHONY: bootstrap bootstrap-existing setup-new-mac ensure-db dev-worker dev-dashboard test lint typecheck format smoke-immich smoke-llm smoke-places smoke-dashboard install-launchd uninstall-launchd logs backup-now install-mlx smoke-mlx monitor start-mlx digest digest-dry configure-tailscale install-nginx uninstall-nginx

PYTHON := uv run python
PYTEST := uv run pytest

# Model weights live on the SSD so they travel with the data.
# All make targets (worker, dashboard, smoke tests) inherit this.
export HF_HOME := /Volumes/PhotoSSD/mlx_models

bootstrap:
	@if [ -f .env ]; then \
		if grep -qE '^(IMMICH_API_KEY|ANTHROPIC_API_KEY)=replace_me' .env; then \
			echo ""; \
			echo "ERROR: .env contains 'replace_me' placeholder secrets. Fill them in and re-run."; \
			exit 1; \
		fi; \
		chmod 600 .env; \
	else \
		cp .env.example .env; \
		chmod 600 .env; \
		echo ""; \
		echo "ERROR: Created .env from template. Edit it (IMMICH_API_KEY etc.) and re-run 'make bootstrap'."; \
		exit 1; \
	fi
	uv venv
	uv sync --all-extras
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/logs
	$(PYTHON) -m home_photo_repo.db migrate
	@echo ""
	@echo "--- Configuring Tailscale for dashboard access ---"
	$(PYTHON) scripts/configure_tailscale.py || true
	@echo ""
	@echo "Bootstrap complete."

ensure-db:
	@if [ ! -f .env ]; then echo "ERROR: .env missing. Run 'make bootstrap' first."; exit 1; fi
	$(PYTHON) -m home_photo_repo.db migrate

dev-worker: ensure-db
	$(PYTHON) -m home_photo_repo.worker.main

test:
	$(PYTEST)

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy

format:
	uv run ruff format src tests

smoke-immich: ensure-db
	$(PYTHON) scripts/smoke_immich.py

smoke-llm:
	$(PYTHON) scripts/smoke_llm.py

smoke-places:
	$(PYTHON) scripts/smoke_places.py $(ARGS)

dev-dashboard: ensure-db
	$(PYTHON) -m home_photo_repo.dashboard.main

smoke-dashboard:
	$(PYTHON) scripts/smoke_dashboard.py

install-launchd:
	$(PYTHON) -m launchd.install_launchd

uninstall-launchd:
	$(PYTHON) -m launchd.uninstall_launchd

logs:
	@LOG_DIR=$$HOME/Library/Logs/home_photo_repo; \
	test -d "$$LOG_DIR" || (echo "log dir $$LOG_DIR does not exist yet — has install-launchd run?" && exit 1); \
	tail -f $$LOG_DIR/*.log

backup-now:
	scripts/backup_postgres.sh

setup-new-mac:
	python3 scripts/setup_new_mac.py

bootstrap-existing:
	@echo "--- Installing system dependencies (Homebrew, uv, Docker, nginx, Tailscale) ---"
	python3 scripts/setup_new_mac.py || true
	@echo ""
	uv venv
	uv sync --all-extras
	@if [ ! -f .env ]; then \
		echo "ERROR: .env missing. Create it from .env.example first."; \
		exit 1; \
	fi
	@chmod 600 .env
	@if grep -qE '^(IMMICH_API_KEY|ANTHROPIC_API_KEY)=replace_me' .env; then \
		echo "ERROR: .env still contains 'replace_me' placeholder secrets."; \
		exit 1; \
	fi
	@if [ ! -f "$${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db/app.sqlite" ]; then \
		echo "ERROR: app.sqlite not found at $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db/app.sqlite"; \
		echo "       Use 'make bootstrap' on a fresh setup; 'bootstrap-existing' is for migrating to a new Mac with an already-populated SSD."; \
		exit 1; \
	fi
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/logs
	$(PYTHON) -m home_photo_repo.db migrate
	@echo ""
	@echo "--- Configuring Tailscale for dashboard access ---"
	$(PYTHON) scripts/configure_tailscale.py || true
	@echo ""
	@echo "bootstrap-existing complete — DB is present, deps installed, migrations applied."

configure-tailscale:
	$(PYTHON) scripts/configure_tailscale.py

install-nginx:
	$(PYTHON) scripts/install_nginx.py

uninstall-nginx:
	$(PYTHON) scripts/install_nginx.py --uninstall

install-mlx:
	@echo "Installing mlx-vlm (Apple Silicon required)..."
	uv sync --extra mlx
	@echo ""
	@echo "Installing the MLX launchd service..."
	$(PYTHON) -m launchd.install_launchd mlx
	@echo ""
	@echo "MLX installed. Model will download on first run (~5 GB)."
	@echo "Switch a stage to MLX by setting in .env:"
	@echo "    LLM_STAGE_A_PROVIDER=mlx"
	@echo "    LLM_STAGE_B_PROVIDER=mlx"
	@echo "Then: make smoke-mlx  (verifies end-to-end)"

smoke-mlx:
	$(PYTHON) scripts/smoke_mlx.py

start-mlx:
	@echo "HF_HOME=$(HF_HOME)"
	uv run mlx_vlm.server \
		--model mlx-community/Qwen2.5-VL-7B-Instruct-4bit \
		--port 8081

monitor: ensure-db
	$(PYTHON) scripts/monitor_processing.py

digest: ensure-db
	$(PYTHON) scripts/send_digest.py

digest-dry: ensure-db
	$(PYTHON) scripts/send_digest.py --dry-run
