.PHONY: clean-pyc clean-build docs generate-versions

clean: clean-build clean-pyc

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info
	rm -fr __pycache__/ .eggs/ .cache/ .tox/

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

lint:
	uv run ruff check --fix
	uv run ruff check --select I --fix

format:
	uv run ruff format 

git:
	git push --all
	git push --tags

check:
	uv pip check

dev-setup:
	uv sync --dev
