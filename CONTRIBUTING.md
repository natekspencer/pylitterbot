# Contributing

Before submitting a pull request, make sure you have validated all tests pass as well as ensuring 100% code coverage.

To run tests, you must have `pytest`, `pytest-asyncio` and `pytest-cov` installed, then run the following command:

```bash
mypy pylitterbot tests
ruff check
ruff format
pytest --cov --cov-report term-missing -vv
```
