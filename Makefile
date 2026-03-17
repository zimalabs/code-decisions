.PHONY: test lint check

test:
	python3 plugins/engram/tests/test_engram.py

lint:
	shellcheck plugins/engram/hooks/*.sh plugins/engram/tests/run_tests.sh
	python3 -m py_compile plugins/engram/engram.py
	python3 -m py_compile plugins/engram/tests/test_engram.py

check: lint test
