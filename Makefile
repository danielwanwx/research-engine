.PHONY: test lint check doctor

test:
	python -m pytest -q

lint:
	python -m ruff check src tests

check: test lint

doctor:
	python -m research_engine.cli doctor
