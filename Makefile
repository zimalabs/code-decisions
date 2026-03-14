.PHONY: test lint check

test:
	bash tests/run_tests.sh

lint:
	shellcheck lib.sh hooks/*.sh tests/*.sh

check: lint test
