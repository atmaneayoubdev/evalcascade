## Summary

<!-- What does this change do, and why? Link related issues (e.g. "Fixes #123"). -->

## Type of change

- [ ] Bug fix
- [ ] New feature (metric, evaluator, CLI/API capability, ...)
- [ ] Breaking change
- [ ] Documentation
- [ ] Refactor / tooling / CI

## How was it tested?

<!-- Commands you ran and anything you checked by hand. Tests must not call real providers. -->

## Checklist

- [ ] `uv run pytest` passes.
- [ ] `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy` pass.
- [ ] New behaviour has tests, and the tests make no network calls.
- [ ] Docs (`docs/`, `README.md`, CLI help) reflect the change.
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`.
- [ ] No secrets, `.env` files, local databases or build output are included.
- [ ] Dashboard changes pass `npm run lint`, `npm run typecheck` and `npm run build` in `web/`.
