SHELL := /bin/bash
.SHELLFLAGS := -o errexit -o pipefail -o nounset -c
MAKEFLAGS += --no-builtin-rules
MAKEFLAGS += --no-builtin-variables
.ONESHELL: # Don't execute shell statements in parallel
.SUFFIXES: # Remove suffix patterns
.DELETE_ON_ERROR: # Delete outputs on error
.DEFAULT_GOAL := help # Set default goal to help

PYTEST_ADDOPTS ?=

ifdef VERBOSE
PYTEST_ADDOPTS += -$(VERBOSE)
endif 

.PHONY: help
help:  ## Prints this usage
	@printf '== RECIPES ==\n' && sed -nE 's/^\s*#\s*(==.*)/\n\1/p; s/^([^.:[:space:]][^:[:space:]]+):[^#]*###*\s*(.*$$)/\1 -- \2/p' $(MAKEFILE_LIST)

# Set up AWS and cloudknot configuration file locations:
AWS_CONFIG_FILE ?= $(HOME)/.aws/config

# == Testing ==
$(AWS_CONFIG_FILE):
	test -f "$@" || { mkdir -p $(dir $@); cloudknot configure; }

.PHONY: test
test: $(AWS_CONFIG_FILE) ## Run unit tests with pytest
	set +o errexit && pytest --pyargs cloudknot --cov-report term-missing --cov-config .coveragerc --cov=cloudknot

.PHONY: devtest
devtest: $(AWS_CONFIG_FILE) ## Run unit tests with pytest -x, exiting after first failure
    # Useful for development when tests are long
	pytest -x --pyargs cloudknot --cov-report term-missing --cov-config .coveragerc --cov=cloudknot

# == Cleanup ==
.PHONY: clean
clean: clean-build clean-pyc clean-test ## Remove all build, test, coverage and Python artifacts

.PHONY: clean-all
clean-all: clean clean-aws-config ## Remove AWS configuration and all build, test, coverage and Python artifacts

.PHONY: clean-build
clean-build: ## Remove build artifacts
	rm -rf build/ dist/ .eggs/
	find . -name '*.egg-info' -or -name '*.egg' -exec rm -rf {} +

.PHONY: clean-pyc
clean-pyc: ## Remove Python file artifacts
	find . -name '*.py[co]' -or -name '*~' -or -name '__pycache__' -exec rm -rf {} +

.PHONY: clean-test
clean-test: ## Remove test artifacts
	rm -rfv .pytest_cache cloudknot_*func_* tmp*

.PHONY: clean-aws-config
clean-aws-config: ## Remove AWS configuration
	rm -rfv $(AWS_CONFIG_DIR)

.PHONY: generate-aws-test-config
generate-aws-test-config:  ## Generate a clean AWS configuration for testing
	mkdir -p $(AWS_CONFIG_DIR) && \
		touch $(AWS_CONFIG_DIR)/credentials && \
		printf "[aws]\nconfigured = True\n" > $(AWS_CONFIG_DIR)/cloudknot

# == Linting and formatting ==

.PHONY: flake ## Run flake8
flake:
	flake8

.PHONY: lint
lint: ## Run all linters (flake, pydocstyle, black)
	flake8
	black --check .
	pydocstyle

# == Build and release ==

dist: clean ## Build source and wheel package
	python setup.py sdist
	python setup.py bdist_wheel --universal
	ls -l $@

.PHONY: release
release: dist ## Package and upload a release
	twine upload $</*

