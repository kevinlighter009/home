.PHONY: bootstrap bootstrap-existing ensure-db dev-worker dev-dashboard test lint typecheck format smoke-immich smoke-llm smoke-places smoke-dashboard install-launchd uninstall-launchd logs backup-now

PYTHON := uv run python
PYTEST := uv run pytest

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

bootstrap-existing:
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
	@echo "bootstrap-existing complete — DB is present, deps installed, migrations applied."
