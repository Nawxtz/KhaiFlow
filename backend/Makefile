.PHONY: ci lint typecheck test

ci: lint typecheck test

lint:
	ruff check app

typecheck:
	mypy app

test:
	pytest
