.PHONY: test lint check

test:
	bash plugins/engram/tests/run_tests.sh

lint:
	shellcheck plugins/engram/lib.sh plugins/engram/hooks/*.sh plugins/engram/tests/*.sh

check: lint test
