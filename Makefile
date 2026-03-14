dev:
	uv run python main.py

docs:
	uv run mkdocs serve

lint:
	uv run ruff check --fix . && uv run uncomment . && uv run mypy .
