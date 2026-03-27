.PHONY: fmt lint test validate code-coverage check ci clean dev

fmt:
	uv run ruff format src/decision/

lint:
	shellcheck src/hooks/*.sh
	uv run ruff format --check src/decision/
	uv run ruff check src/decision/
	uv run mypy src/decision/

test:
	uv run pytest tests/ -n auto

validate:
	uv run python3 -m decision validate

code-coverage:
	uv run pytest tests/ --cov=decision --cov-report=term-missing --cov-report=xml

check: lint test validate

ci: check code-coverage

clean:
	bash scripts/clean.sh

dev:
	@bash scripts/dev.sh
