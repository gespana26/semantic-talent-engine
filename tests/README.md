# Tests

First-slice unit-test harness. Only pure unit tests are in scope:
configuration defaults/overrides and Pydantic schema validation. No
ChromaDB, no AI providers, no CLI, no business flows.

## Layout

```
tests/
├── __init__.py
├── conftest.py
└── unit/
    ├── __init__.py
    ├── test_settings.py
    └── test_schemas.py
```

## Install dev dependencies

From a clean virtual environment at the repo root:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes the production `requirements.txt` plus
`pytest`.

## Run the unit tests

```bash
pytest
```

Pytest discovers tests under `tests/` (configured in `pytest.ini`).

Run a single module:

```bash
pytest tests/unit/test_settings.py
```

Run a single test with verbose output:

```bash
pytest tests/unit/test_schemas.py::test_vacancy_valid_payload_is_accepted -v
```

## Scope rules for new tests in this slice

A test belongs in this slice **only if** it:

- Lives under `tests/unit/`.
- Imports only from `config/` and `models/`.
- Does **not** touch ChromaDB, Ollama, OpenAI, the CLI, the orchestrator,
  the extractor, the search engine, or the query translator.
- Runs in milliseconds with no network and no filesystem writes.

Anything beyond that is out of scope for the first iteration and must
wait for a follow-up SDD change.
