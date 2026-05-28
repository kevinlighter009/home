.PHONY: bootstrap dev-worker test lint typecheck format

PYTHON := uv run python
PYTEST := uv run pytest

bootstrap:
	uv venv
	uv sync --all-extras
	@test -f .env || (cp .env.example .env && chmod 600 .env && echo "Created .env from template — fill in keys then re-run bootstrap")
	@test -f .env && chmod 600 .env
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/logs
	$(PYTHON) -m home_photo_repo.db migrate
	@echo "Bootstrap complete."

dev-worker:
	$(PYTHON) -m home_photo_repo.worker.main

test:
	$(PYTEST)

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy

format:
	uv run ruff format src tests
