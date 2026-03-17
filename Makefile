MARKETPLACE := $(CURDIR)/.claude-plugin/marketplace.json
PLUGIN_VERSION := $(shell python3 -c "import json; print(json.load(open('$(MARKETPLACE)'))['plugins'][0]['version'])")
CACHE_DIR := $(HOME)/.claude/plugins/cache/zimalabs/engram/$(PLUGIN_VERSION)

.PHONY: test lint check dev

test:
	uv run pytest tests/ -q

lint:
	shellcheck plugin/hooks/*.sh
	uv run ruff check plugin/src/engram/
	uv run mypy plugin/src/engram/

check: lint test

dev:
	@rm -rf "$(CACHE_DIR)"
	@ln -sfn "$(CURDIR)/plugin" "$(CACHE_DIR)"
	@echo "Linked $(CACHE_DIR) → $(CURDIR)/plugin"
