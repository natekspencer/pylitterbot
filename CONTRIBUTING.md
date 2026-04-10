# Contributing

Follow these steps to set up your environment and ensure your changes meet the project's standards.

## Setup

1. Install `uv` by Astral - https://docs.astral.sh/uv/getting-started/installation/
2. Clone this repository:
   ```bash
   git clone https://github.com/natekspencer/pylitterbot.git
   cd pylitterbot
   ```
3. Install dependencies and pre-commit hooks:
   ```bash
   uv sync
   uv run pre-commit install
   ```

## Guidelines

- **Code Formatting:** Ensure your code is properly formatted. This project uses `ruff` for linting and formatting.
- **Typing:** All code must be fully typed. Use `mypy` to check for type issues:
  ```bash
  uv run mypy pylitterbot tests
  ```
- **Testing:** Add tests for any new features or changes. Run the test suite with:
  ```bash
  uv run pytest
  ```
- **Commit Messages:** Follow conventional commit messages, e.g., feat: add new feature or fix: resolve issue with X

## Testing Your Branch

You can run the full suite through all the supported Python versions:

```bash
uv run tox
```

Or just focus on individual checks:

```bash
uv run mypy pylitterbot tests
uv run ruff check .
uv run ruff format .
uv run pytest
```

## Submitting Changes

1. Create a new branch for your feature or fix:
   ```bash
   git checkout -b feature/your-feature
   ```
2. Make your changes and commit them.
3. Make sure all tests pass and that test coverage for your changes is present.
4. Push to your fork and open a pull request.

I appreciate your contributions! 🚀
