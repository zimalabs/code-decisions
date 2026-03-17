.PHONY: test lint check

test:
	python3 plugins/engram/tests/test_engram.py
	python3 plugins/engram/tests/test_policy.py

lint:
	shellcheck plugins/engram/hooks/*.sh plugins/engram/tests/run_tests.sh
	python3 -c "import compileall; compileall.compile_dir('plugins/engram/engram', quiet=1)"
	python3 -m py_compile plugins/engram/tests/test_engram.py
	python3 -m py_compile plugins/engram/tests/test_policy.py

check: lint test
