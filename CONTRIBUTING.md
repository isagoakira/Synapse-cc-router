# Contributing to CC Router

Thank you for your interest in CC Router! We welcome contributions from the community.

## Development Setup

1. **Clone the repository**:

   ```bash
   git clone https://github.com/anthropics/cc-router
   cd cc-router
   ```

2. **Install with development dependencies**:

   ```bash
   pip install -e ".[dev]"
   ```

3. **Install pre-commit hooks**:

   ```bash
   pip install pre-commit
   pre-commit install
   ```

4. **Verify the setup**:

   ```bash
   python -m pytest tests/ -v
   ruff check .
   black --check .
   mypy cc_router/
   ```

## Code Style

- **Formatter**: [Black](https://github.com/psf/black) with line length 100
- **Linter**: [Ruff](https://github.com/astral-sh/ruff) (replace Flake8/isort)
- **Type Checker**: [mypy](https://mypy-lang.org/) (strict mode for core modules)

Format your code before committing:

```bash
black cc_router/ tests/
ruff check --fix cc_router/ tests/
```

## Testing

- All new features must include tests.
- Run the full suite before submitting:

  ```bash
  python -m pytest tests/ -v --cov=cc_router
  ```

- Target coverage: at least 80%.

## Pull Request Process

1. Create a feature branch from `main`.
2. Make your changes with clear commit messages.
3. Ensure all tests pass and lint checks are clean.
4. Open a pull request using the [PR template](.github/PULL_REQUEST_TEMPLATE.md).
5. Maintainers will review your PR within 3-5 business days.

## Issue Reporting

- Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) for defects.
- Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md) for enhancements.
- Check existing issues before opening a new one.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
