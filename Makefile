PYTHON ?= python3
EVAL_OUTPUT ?= eval-results

.PHONY: test lint check doctor eval

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check src tests

check: test lint

doctor:
	$(PYTHON) -m research_engine.cli doctor

eval:
	PYTHONPATH=src $(PYTHON) -m research_engine.eval --output $(EVAL_OUTPUT)
