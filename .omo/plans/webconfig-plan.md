# Webconfig — Implementation Plan

Based on design doc: `docs/superpowers/specs/2026-07-15-webconfig-design.md`

## Phase 1: Foundation (sequential dependencies)

### 1.1 Project scaffolding
- Create `pyproject.toml` with dependencies
- Create directory structure: `webconfig/`, `webconfig/templates/`, `webconfig/static/`, `tests/fixtures/`
- `webconfig/__init__.py`, `webconfig/__main__.py`

### 1.2 Parser (`parser.py`)
- `ConfigParser.parse()` — TOML (via `tomllib`), JSON (via `json`), ENV (custom)
- `ConfigParser.serialize()` — dict → TOML/JSON/ENV string
- Custom ENV parser: key=value, `#` comments, no nesting
- Custom TOML writer: dict → valid TOML string (no `tomli-w` dependency)

### 1.3 Form Generator (`form_generator.py`)
- `Field` dataclass with all attributes from design
- `FormGenerator.generate(data, schema=None)` → Field tree
- Type inference without schema: int/float→number, bool→boolean, str→text/textarea, list→array, dict→object
- Schema-aware generation: parallel traversal of data + schema trees
- Enum → select, default values, required flag, constraints

### 1.4 Validator (`validator.py`)
- Type validation: number fields must be numeric, boolean must be true/false
- Schema validation via `jsonschema.validate()`
- Single-field validation for `/api/validate/<path>`

## Phase 2: Server & UI (parallel where possible)

### 2.1 CLI (`cli.py`)
- Argparse: `config`, `--port`, `--host`, `--schema`, `--preset`, `--no-browser`
- `main()`: validate args, parse config, create Flask app, open browser, run

### 2.2 Templates
- `base.html` — S4 + HTMX setup, preset attribute
- `editor.html` — recursive field rendering, HTMX attributes
- S4 utility classes for layout
- Error display, flash messages via `<e-badge>`

### 2.3 Static Assets
- Vendor S4 v0.3 CSS/JS into `webconfig/static/s4/`
- Vendor HTMX 2.x into `webconfig/static/htmx.min.js`

### 2.4 Server (`server.py`)
- Flask app factory: `create_app(config_path, schema, preset)`
- `GET /` — render editor
- `POST /save` — validate, serialize, write, return HTML partial
- `POST /api/validate/<path>` — validate single field, return error HTML or empty
- `POST /api/array/add/<path>` — add array element, return array section HTML
- `DELETE /api/array/remove/<path>/<idx>` — remove element, return array section HTML
- `GET /reload` — re-read file, return editor HTML

## Phase 3: Tests

### 3.1 Test fixtures
- `config.toml` — nested tables, arrays
- `config.json` — equivalent JSON
- `config.env` — flat ENV
- `schema.json` — types, enum, constraints

### 3.2 Unit tests
- `test_parser.py` — parse/serialize round-trip for all formats
- `test_form_generator.py` — Field tree generation with/without schema
- `test_validator.py` — type + schema validation

### 3.3 Integration tests
- `test_server.py` — Flask test_client: GET, POST save, validation errors, array ops
