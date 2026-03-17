SOURCE_DIR := $(CURDIR)/plugins/engram
MARKETPLACE := $(CURDIR)/.claude-plugin/marketplace.json
PLUGIN_VERSION := $(shell python3 -c "import json; print(json.load(open('$(MARKETPLACE)'))['plugins'][0]['version'])")
CACHE_DIR := $(HOME)/.claude/plugins/cache/zimalabs/engram/$(PLUGIN_VERSION)

.PHONY: test lint check dev

test:
	python3 plugins/engram/tests/test_engram.py
	python3 plugins/engram/tests/test_policy.py

lint:
	shellcheck plugins/engram/hooks/*.sh plugins/engram/tests/run_tests.sh
	python3 -c "import compileall; compileall.compile_dir('plugins/engram/engram', quiet=1)"
	python3 -m py_compile plugins/engram/tests/test_engram.py
	python3 -m py_compile plugins/engram/tests/test_policy.py

check: lint test

dev:
	@rm -rf "$(CACHE_DIR)"
	@ln -sfn "$(SOURCE_DIR)" "$(CACHE_DIR)"
	@echo "Linked $(CACHE_DIR) → $(SOURCE_DIR)"
