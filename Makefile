# LexiGuard Makefile

PYTHON ?= python
PYTEST ?= pytest
UVICORN ?= uvicorn

.PHONY: help setup dev test lint clean

help:
	@echo "LexiGuard — available targets:"
	@echo "  make setup    Install Python dependencies"
	@echo "  make dev      Run the development server (127.0.0.1:8000)"
	@echo "  make test     Run the test suite"
	@echo "  make lint     Run ruff linter"
	@echo "  make clean    Remove generated files"

setup:
	$(PYTHON) -m pip install -e ".[dev]"
	@echo "Setup complete. Verify Ollama is installed and running before starting."

dev:
	$(UVICORN) backend.app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	$(PYTEST) tests/ -v

lint:
	ruff check backend/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache/ .coverage htmlcov/
