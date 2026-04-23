# management-server/Makefile
#
# Developer-facing entry points. All targets operate from this directory.
# The CI pipeline builds the image via management-server/Dockerfile;
# this Makefile is for local iteration only.

PYTHON ?= python3
VENV   ?= .venv
PIP    := $(VENV)/bin/pip
PY     := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

.PHONY: help venv install dev-install test lint migrate up down clean

help:
	@echo "Targets:"
	@echo "  make venv         create $(VENV) if missing"
	@echo "  make install      install runtime deps into $(VENV)"
	@echo "  make dev-install  install runtime + dev deps (pytest, ruff, mypy)"
	@echo "  make test         run pytest"
	@echo "  make lint         run ruff"
	@echo "  make up / down    docker compose up/down (needs docker)"
	@echo "  make migrate      alembic upgrade head (needs postgres reachable)"
	@echo "  make clean        rm venv + caches"

venv:
	@if [ ! -d "$(VENV)" ]; then \
	    $(PYTHON) -m venv $(VENV) ; \
	    $(PIP) install --disable-pip-version-check --quiet --upgrade pip setuptools wheel ; \
	fi

install: venv
	$(PIP) install --disable-pip-version-check --quiet -e .

dev-install: venv
	$(PIP) install --disable-pip-version-check --quiet -e '.[dev]' aiosqlite

test: dev-install
	$(PYTEST) -ra

lint: dev-install
	$(VENV)/bin/ruff check app tests

migrate:
	$(VENV)/bin/alembic upgrade head

up:
	docker compose up --build -d

down:
	docker compose down

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache **/__pycache__
