SHELL := bash
.ONESHELL:

VENV := ./.venv

.PHONY: ruff
ruff:
	ruff check .
	ruff format --check .

.PHONY: flake
flake: ruff

.PHONY: lint
lint: ruff

.PHONY: test
test: ## Unit testing using pytest
	pytest --pyargs cloudknot --cov-report term-missing --cov-config .coveragerc --cov=cloudknot

.PHONY: devtest
devtest: ## Unit testing with the -x option, aborts testing after first failure
    # Useful for development when tests are long
	pytest -x --pyargs cloudknot --cov-report term-missing --cov-config .coveragerc --cov=cloudknot

.PHONY: clean
clean: clean-build clean-pyc clean-test clean-lint ## remove all build, test, coverage and Python artifacts

.PHONY: clean-build
clean-build: ## remove build artifacts
	rm -rf build/ dist/ .eggs/
	find . -name '*.egg-info' -or -name '*.egg' -exec rm -rf {} +

.PHONY: clean-test
clean-test:
	find . -name '.pytest_cache' -exec rm -rf {} +

.PHONY: clean-pyc
clean-pyc: ## remove Python file artifacts
	find . \
		-name '*.pyc' -or \
		-name '*.pyo' -or \
		-name '*~' \
		-exec rm -rf {} +

.PHONY: clean-lint
clean-lint:
	find . \
		-name '.mypy_cache' -or \
		-name '.ruff_cache' \
		-exec rm -rf {} +

.PHONY: release
release: dist ## Package and upload a release
	twine upload dist/*

.PHONY: dist
dist: clean ## Build source and wheel package
	python setup.py sdist
	python setup.py bdist_wheel --universal
	ls -l dist

.PHONY: clean-venv
clean-venv:
	command -v deactivate >/dev/null 2>&1 && deactivate
	rm -rf $(VENV)

.PHONY: venv
venv: clean-venv
	python -m venv $(VENV)
	$(VENV)/bin/pip install -U pip setuptools setuptools_scm
	$(VENV)/bin/pip install -e '.[dev]'

