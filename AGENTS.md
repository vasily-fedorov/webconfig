# AGENTS.md — Webconfig

## Project Overview

Webconfig is a Python CLI utility that starts a local web server with a Web UI
for editing configuration files (TOML/JSON/ENV) with optional JSON Schema support.

## Tech Stack

- **Python 3.11+** — `tomllib` in stdlib
- **Flask 3.x** + Jinja2 — server-side HTML rendering
- **HTMX 2.x** — interactivity without custom JS
- **S4 (Система 4) v0.3** — CSS system (vendored in `webconfig/static/s4/`)
- **jsonschema** — JSON Schema validation
- **pytest** — testing

## Architecture

Server-side rendering with HTMX for partial updates. No SPA, no custom JS framework.

```
CLI (argparse) → Flask app → Jinja2 templates → HTML + HTMX → Browser
                    ↓
              parser.py      form_generator.py      validator.py
              (TOML/JSON/ENV) (dict → Field tree)   (type + jsonschema)
```

## Key Design Decisions

1. **Server-side rendering** — S4 is CSS-only, designed for semantic HTML.
   Templates generate HTML with S4 utility classes on the server.
2. **HTMX for interactivity** — No custom JS. Save, validate, array add/remove
   all go through HTMX attributes (`hx-post`, `hx-swap`, `hx-target`).
3. **Field tree model** — `form_generator.py` converts parsed dict into a
   `Field` tree. Templates recursively render this tree. Schema enriches the
   tree with types, enums, defaults, constraints.
4. **No file I/O in parser** — `ConfigParser.parse(text, path)` takes
   already-read text. Callers handle file reads/writes.
5. **Single file per session** — One config file per server instance.

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Argparse, validate args, create app, open browser, run |
| `server.py` | Flask routes: `/`, `/save`, `/api/validate/<path>`, `/api/array/add/<path>`, `/api/array/remove/<path>/<idx>`, `/reload` |
| `parser.py` | `ConfigParser.parse(text, path)` and `ConfigParser.serialize(data, path)` |
| `form_generator.py` | `FormGenerator.generate(data, schema=None)` → `Field` tree |
| `validator.py` | `Validator(schema).validate(data)` and `validate_field(path, value)` |

## Templates

- `base.html` — `<html>` wrapper: S4 init (`S4()`), HTMX, preset attribute, shared styles
- `editor.html` — extends `base.html`. Contains Jinja2 macros for recursive field rendering:
  `render_children`, `render_object`, `render_array`, `render_scalar`, `render_boolean`, `render_select`

## Testing

```bash
.venv/bin/pytest tests/ -v
```

127 tests, all in `tests/`:

| File | Tests | Covers |
|------|-------|--------|
| `test_parser.py` | 14 | parse/serialize roundtrip for TOML, JSON, ENV |
| `test_form_generator.py` | 12 | dict → `Field` tree, schema enrichment |
| `test_form_parsing.py` | 29 | form key → nested dict (`_parse_key`, `_form_to_dict`) |
| `test_validator.py` | 12 | type coercion, schema validation, `validate_field` |
| `test_validator_comprehensive.py` | 43 | every type, constraint, nesting and array case |
| `test_server_array.py` | 17 | `/api/array/add` and `/api/array/remove` endpoints |

Unit tests import from `webconfig.*` directly; endpoint tests use
`Flask.test_client` against a `tmp_path` copy of the fixtures in `tests/fixtures/`.
Any change to the array endpoints or their path helpers needs a
`test_server_array.py` case, since those routes are not reachable from the
parser/validator unit tests.

## Code Style

- Python 3.11+ type hints throughout
- `from __future__ import annotations` for forward references
- Dataclasses for data models
- Stdlib-first: no unnecessary dependencies
- Comments only for non-obvious behavior

## Design Document

Full design spec: `docs/superpowers/specs/2026-07-15-webconfig-design.md`
