# Contributing

Before submitting a pull request, make sure you have validated all tests pass as well as ensuring there is test coverage for your changes.

Run the full suite through all the supported Python versions:

```bash
uv run tox
```

Or individual pieces:

```bash
uv run mypy pylitterbot tests
uv run ruff check .
uv run ruff format .
uv run pytest
```

