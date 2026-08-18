<![CDATA[# Tests — `tests/`

## Structure
- `unit/` — Isolated unit tests (models, utils, validators)
- `integration/` — Backend API integration tests
- `e2e/` — End-to-end browser tests
- `scientific/` — Scientific model validation tests
- `performance/` — Load and performance benchmarks
- `fixtures/` — Shared test data and fixtures

## Running Tests
```bash
# All Python tests
pytest

# Frontend tests
cd apps/web && npm test

# Scientific validation
pytest tests/scientific/

# Specific module
pytest simulation/tests/
pytest tests/unit/
```

## Test Naming Convention
```
test_<module>_<function>_<scenario>.py
```
]]>
