.PHONY: install lint typecheck test cov

install:
	pip install -e ".[dev,all]"

lint:
	ruff check src tests
	ruff format --check src tests

typecheck:
	mypy src/echotools

test:
	pytest

cov:
	pytest --cov=echotools --cov-report=term-missing
