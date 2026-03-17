MARKETPLACE := $(CURDIR)/.claude-plugin/marketplace.json
PLUGIN_VERSION := $(shell python3 -c "import json; print(json.load(open('$(MARKETPLACE)'))['plugins'][0]['version'])")
CACHE_DIR := $(HOME)/.claude/plugins/cache/zimalabs/engram/$(PLUGIN_VERSION)

.PHONY: test lint fmt check ci clean dev

fmt:
	uv run ruff format plugin/engram/

lint:
	shellcheck plugin/hooks/*.sh
	uv run ruff format --check plugin/engram/
	uv run ruff check plugin/engram/
	uv run mypy plugin/engram/

test:
	uv run pytest tests/ -q

check: lint test

ci: check

clean:
	rm -f .engram/index.db .engram/brief.md
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage coverage.xml
	rm -rf htmlcov/

dev:
	@rm -rf "$(CACHE_DIR)"
	@ln -sfn "$(CURDIR)/plugin" "$(CACHE_DIR)"
	@echo "Linked $(CACHE_DIR) → $(CURDIR)/plugin"
