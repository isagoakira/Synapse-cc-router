# Release Checklist

Use this checklist when preparing a new release of CC Router.

## Pre-Release

- [ ] All tests pass: `python -m pytest tests/ -v`
- [ ] Test coverage >= 80%: `python -m pytest --cov=cc_router tests/`
- [ ] Lint passes: `ruff check .`
- [ ] Format check passes: `black --check .`
- [ ] Type check passes: `mypy cc_router/`
- [ ] Version updated in `cc_router/__init__.py`
- [ ] CHANGELOG.md updated with all changes
- [ ] README.md dependencies/requirements up to date
- [ ] API docs reflect any new components
- [ ] `cc_router_config.template.json` matches actual config schema
- [ ] Git status clean (no uncommitted changes)
- [ ] Pre-commit hooks pass: `pre-commit run --all-files`

## Release Process

### 1. Tag and Push

```bash
git tag -a v0.2.0 -m "CC Router v0.2.0"
git push origin v0.2.0
```

### 2. CI/CD Actions

- GitHub Actions will automatically:
  - Run lint + test + docker build
  - Build distribution packages
  - Create GitHub Release (from `release.yml`)
  - Publish to PyPI (if `PYPI_API_TOKEN` secret is configured)

### 3. Post-Release Verification

- [ ] PyPI package published: `pip install cc-router==0.2.0`
- [ ] Docker image builds: `docker build -t cc-router:0.2.0 .`
- [ ] CLI works: `cc-router --help`
- [ ] GitHub Release page created with changelog
- [ ] Release tagged in repository

## Version History

| Version | Date | Notes |
|---------|------|-------|
| 0.1.0 | 2025-05-06 | Initial alpha release |
| 0.2.0 | 2026-05-07 | Public release prep: docs, CI, tests, community files |
