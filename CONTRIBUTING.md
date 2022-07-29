# Contributing

Before submitting a pull request, make sure you have validated all tests pass as well as ensuring 100% code coverage.

To run tests, you must have `pytest`, `pytest-asyncio` and `pytest-cov` installed, then run the following command:

```bash
mypy pylitterbot tests
pylint pylitterbot tests
pytest --cov --cov-report term-missing -vv
```
