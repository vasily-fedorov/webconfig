"""Flask application — web UI for config editing."""

import json
import os
from pathlib import Path

from flask import Flask, render_template, request

from webconfig.form_generator import FormGenerator
from webconfig.parser import ConfigParseError, ConfigParser
from webconfig.validator import ValidationError, Validator


def create_app(config_path: str, schema: dict | None = None, preset: str = "auto") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = os.urandom(24)

    # Read and parse initial config (side-effect: validates file at startup)
    try:
        config_text = Path(config_path).read_text()
        config = ConfigParser.parse(config_text, config_path)
    except ConfigParseError as e:
        # Create app anyway — show error page
        app.config["PARSE_ERROR"] = str(e)
        app.config["CONFIG_PATH"] = config_path
        app.config["CONFIG_FORMAT"] = _format_from_path(config_path)
        app.config["SCHEMA"] = schema
        app.config["PRESET"] = preset
        return _register_routes(app)

    app.config["CONFIG_PATH"] = config_path
    app.config["CONFIG_FORMAT"] = config.format
    app.config["CONFIG_DATA"] = config.data
    app.config["SCHEMA"] = schema
    app.config["PRESET"] = preset

    return _register_routes(app)


def _register_routes(app: Flask) -> Flask:
    """Register all routes on the Flask app."""

    generator = FormGenerator()
    validator = Validator(schema=app.config.get("SCHEMA"))

    @app.route("/")
    def editor():
        """GET / — render the editor form."""
        filename = os.path.basename(app.config["CONFIG_PATH"])
        fmt = app.config.get("CONFIG_FORMAT", "")
        # Allow theme override via ?preset= query param
        query_preset = request.args.get("preset")
        if query_preset in ("light", "dark"):
            app.config["PRESET"] = query_preset
        preset = app.config["PRESET"]
        data = app.config.get("CONFIG_DATA", {})
        schema = app.config.get("SCHEMA")
        parse_error = app.config.get("PARSE_ERROR")

        if parse_error:
            return render_template(
                "editor.html",
                filename=filename,
                format=fmt,
                preset=preset,
                field=None,
                error_message=parse_error,
            )

        field_tree = generator.generate(data, schema)
        return render_template(
            "editor.html",
            filename=filename,
            format=fmt,
            preset=preset,
            field=field_tree,
        )

    @app.route("/reload")
    def reload():
        """GET /reload — re-read config file from disk, render form."""
        config_path = app.config["CONFIG_PATH"]

        try:
            config_text = Path(config_path).read_text()
            config = ConfigParser.parse(config_text, config_path)
        except ConfigParseError as e:
            return render_template(
                "editor.html",
                filename=os.path.basename(config_path),
                format=app.config.get("CONFIG_FORMAT", ""),
                preset=app.config["PRESET"],
                field=None,
                error_message=f"Reload failed: {e}",
            )

        app.config["CONFIG_DATA"] = config.data
        app.config["CONFIG_FORMAT"] = config.format

        field_tree = generator.generate(config.data, app.config.get("SCHEMA"))
        return render_template(
            "editor.html",
            filename=os.path.basename(config_path),
            format=config.format,
            preset=app.config["PRESET"],
            field=field_tree,
            saved_message="Reloaded from disk.",
        )

    @app.route("/save", methods=["POST"])
    def save():
        """POST /save — validate form data, save to file, return form HTML."""
        config_path = app.config["CONFIG_PATH"]
        fmt = app.config.get("CONFIG_FORMAT", "")
        preset = app.config["PRESET"]
        schema = app.config.get("SCHEMA")

        # Parse flat form data into nested dict
        form_data = _form_to_dict(request.form)

        # Validate
        errors = validator.validate(form_data)
        if errors:
            field_tree = generator.generate(form_data, schema)
            return render_template(
                "editor.html",
                filename=os.path.basename(config_path),
                format=fmt,
                preset=preset,
                field=field_tree,
                error_message=f"Validation failed: {errors[0].message}",
            )

        try:
            serialized = ConfigParser.serialize(form_data, config_path)
            Path(config_path).write_text(serialized)
            app.config["CONFIG_DATA"] = form_data
        except Exception as e:
            field_tree = generator.generate(form_data, schema)
            return render_template(
                "editor.html",
                filename=os.path.basename(config_path),
                format=fmt,
                preset=preset,
                field=field_tree,
                error_message=f"Save failed: {e}",
            )

        field_tree = generator.generate(form_data, schema)
        return render_template(
            "editor.html",
            filename=os.path.basename(config_path),
            format=fmt,
            preset=preset,
            field=field_tree,
            saved_message="Saved.",
        )

    @app.route("/api/validate/<path:field_path>", methods=["POST"])
    def validate_field(field_path: str):
        """POST /api/validate/<path> — validate a single field, return error HTML or empty."""
        value = request.form.get(field_path, "")
        errors = validator.validate_field(field_path, value)
        if errors:
            return f'<div class="field-error">{errors[0].message}</div>'
        return ""

    @app.route("/api/array/add/<path:array_path>", methods=["POST"])
    def array_add(array_path: str):
        """POST /api/array/add/<path> — add element to array, return array section HTML."""
        config_path = app.config["CONFIG_PATH"]
        schema = app.config.get("SCHEMA")
        fmt = app.config.get("CONFIG_FORMAT", "")

        data = app.config.get("CONFIG_DATA", {})
        _add_array_element(data, array_path)
        app.config["CONFIG_DATA"] = data

        field_tree = generator.generate(data, schema)
        array_field = _find_field(field_tree, array_path)
        if array_field is None:
            return "", 404

        # Render just the array section
        return _render_array_section(array_field, array_path)

    @app.route("/api/array/remove/<path:array_path>/<int:index>", methods=["DELETE"])
    def array_remove(array_path: str, index: int):
        """DELETE /api/array/remove/<path>/<idx> — remove element, return array section HTML."""
        schema = app.config.get("SCHEMA")

        data = app.config.get("CONFIG_DATA", {})
        _remove_array_element(data, array_path, index)
        app.config["CONFIG_DATA"] = data

        field_tree = generator.generate(data, schema)
        array_field = _find_field(field_tree, array_path)
        if array_field is None:
            return "", 404

        return _render_array_section(array_field, array_path)

    return app


# ===== Helper functions =====


def _format_from_path(path: str) -> str:
    """Determine format from file extension."""
    suffix = Path(path).suffix.lower()
    return suffix.lstrip(".")


def _form_to_dict(form_data) -> dict:
    """Convert flat form data (key=value) to nested dict.

    Keys like "server.host" become nested. Array keys like "items[0]" become lists.
    """
    import re

    result: dict = {}
    for key in form_data:
        raw = form_data[key]
        # Handle MultiDict — checkbox sends list, take last value
        if isinstance(raw, list):
            raw = raw[-1] if raw else ""
        _set_nested(result, key, _parse_form_value(raw))
    return result


def _parse_key(key: str) -> list:
    """Parse 'servers[0].name' → ['servers', 0, 'name'] or 'matrix[0][1]' → ['matrix', 0, 1]."""
    import re

    result = []
    # Split on dots, then split each segment on brackets
    for segment in key.split("."):
        # Match patterns like 'name', 'name[0]', 'name[0][1]'
        parts = re.split(r"(\[\d+\])", segment)
        for part in parts:
            if not part:
                continue
            m = re.match(r"^\[(\d+)\]$", part)
            if m:
                result.append(int(m.group(1)))
            else:
                result.append(part)
    return result


def _parse_form_value(value: str):
    """Parse a form string value into appropriate Python type."""
    if value == "":
        return ""
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass
    return value


def _set_nested(d: dict, key: str, value):
    """Set a value in nested dict using dotted path and array indices."""
    parts = _parse_key(key)
    node = d
    for i, part in enumerate(parts):
        if isinstance(part, int):
            while len(node) <= part:
                if i + 1 < len(parts):
                    node.append([] if isinstance(parts[i + 1], int) else {})
                else:
                    node.append(None)
            if i == len(parts) - 1:
                node[part] = value
            else:
                node = node[part]
        else:
            if i == len(parts) - 1:
                node[part] = value
            else:
                next_is_index = i + 1 < len(parts) and isinstance(parts[i + 1], int)
                node = node.setdefault(part, [] if next_is_index else {})


def _add_array_element(data: dict, path: str):
    """Add a default element to an array at the given path."""
    parts = _parse_key_path(path)
    current = data
    for i, part in enumerate(parts):
        if part.startswith("[") and part.endswith("]"):
            continue
        if part not in current:
            current[part] = []
        if i == len(parts) - 1:
            arr = current[part]
            if not isinstance(arr, list):
                arr = []
                current[part] = arr
            # Determine default value based on existing items
            if arr and isinstance(arr[0], dict):
                # Array of objects — add empty dict
                arr.append({})
            elif arr:
                # Array of scalars — add same type
                arr.append("")
            else:
                arr.append("")
        else:
            current = current[part]


def _remove_array_element(data: dict, path: str, index: int):
    """Remove an element from an array at the given path."""
    parts = _parse_key_path(path)
    current = data
    for part in parts:
        if part.startswith("[") and part.endswith("]"):
            continue
        if part in current:
            current = current[part]
    if isinstance(current, list) and 0 <= index < len(current):
        current.pop(index)


def _find_field(field_tree, path: str):
    """Find a Field node by its path in the tree."""
    if field_tree.path == path:
        return field_tree

    import re

    parts = _parse_key_path(path)
    current = field_tree
    for part in parts:
        if part.startswith("[") and part.endswith("]"):
            continue
        found = False
        for child in current.children:
            if child.key == part:
                current = child
                found = True
                break
        if not found:
            return None
    return current


def _render_array_section(array_field, array_path: str) -> str:
    """Render the HTML for an array section, used by HTMX responses."""
    # Import render_template_string for partial rendering
    from flask import render_template_string

    safe_id = array_path.replace(".", "-")

    items_html = ""
    for idx, item in enumerate(array_field.children):
        item_path = f"{array_path}[{idx}]"
        if item.field_type == "object":
            items_html += f"""
            <div class="array-item">
                <div style="flex: 1;">
                    {_render_object_inline_html(item, item_path)}
                </div>
                <button class="remove-btn" type="button"
                        hx-delete="/api/array/remove/{array_path}/{idx}"
                        hx-target="#array-{safe_id}"
                        hx-swap="outerHTML"
                        title="Remove item">&times;</button>
            </div>
            """
        else:
            items_html += f"""
            <div class="array-item">
                <div class="form-row" style="flex: 1;">
                    {_render_scalar_html(item, item_path)}
                </div>
                <button class="remove-btn" type="button"
                        hx-delete="/api/array/remove/{array_path}/{idx}"
                        hx-target="#array-{safe_id}"
                        hx-swap="outerHTML"
                        title="Remove item">&times;</button>
            </div>
            """

    return f"""
    <div class="field-wrapper" id="array-{safe_id}">
        {items_html}
        <button type="button"
                hx-post="/api/array/add/{array_path}"
                hx-target="#array-{safe_id}"
                hx-swap="outerHTML"
                style="margin-top: 0.5em;">
            + Add item
        </button>
    </div>
    """


def _render_scalar_html(field, path: str) -> str:
    """Render HTML for a scalar field (used in array items)."""
    safe_id = path.replace(".", "-").replace("[", "-").replace("]", "")
    value = field.value if field.value is not None else ""

    if field.field_type == "textarea":
        return f"""
        <textarea id="{safe_id}" name="{path}" rows="3"
                  hx-post="/api/validate/{path}"
                  hx-trigger="change"
                  hx-target="#err-{safe_id}"
                  hx-swap="innerHTML">{value}</textarea>
        <div id="err-{safe_id}" class="field-error"></div>
        """
    elif field.field_type == "number":
        min_attr = f'min="{field.constraints["min"]}"' if field.constraints.get("min") is not None else ""
        max_attr = f'max="{field.constraints["max"]}"' if field.constraints.get("max") is not None else ""
        return f"""
        <input type="number" id="{safe_id}" name="{path}" value="{value}"
               {min_attr} {max_attr}
               hx-post="/api/validate/{path}"
               hx-trigger="change"
               hx-target="#err-{safe_id}"
               hx-swap="innerHTML" />
        <div id="err-{safe_id}" class="field-error"></div>
        """
    else:
        pattern_attr = f'pattern="{field.constraints["pattern"]}"' if field.constraints.get("pattern") else ""
        minlen_attr = f'minlength="{field.constraints["minLength"]}"' if field.constraints.get("minLength") is not None else ""
        maxlen_attr = f'maxlength="{field.constraints["maxLength"]}"' if field.constraints.get("maxLength") is not None else ""
        return f"""
        <input type="text" id="{safe_id}" name="{path}" value="{value}"
               {pattern_attr} {minlen_attr} {maxlen_attr}
               hx-post="/api/validate/{path}"
               hx-trigger="change"
               hx-target="#err-{safe_id}"
               hx-swap="innerHTML" />
        <div id="err-{safe_id}" class="field-error"></div>
        """


def _render_object_inline_html(field, path: str) -> str:
    """Render HTML for an object field inline (used in array items)."""
    children_html = ""
    for child in field.children:
        child_path = f"{path}.{child.key}" if path else child.key

        if child.field_type == "object":
            children_html += f"""
            <details open>
                <summary class="section-header">
                    <strong>{child.label}</strong>
                    <span class="type-badge">object</span>
                </summary>
                <div class="field-wrapper">
                    {_render_object_inline_html(child, child_path)}
                </div>
            </details>
            """
        elif child.field_type == "array":
            children_html += _render_array_section(child, child_path)
        elif child.field_type == "boolean":
            safe_id = child_path.replace(".", "-").replace("[", "-").replace("]", "")
            checked = "checked" if child.value else ""
            children_html += f"""
            <div class="form-row-inline" style="margin-bottom: 1em;">
                <input type="checkbox" id="{safe_id}" name="{child_path}"
                       value="true" {checked}
                       hx-post="/api/validate/{child_path}"
                       hx-trigger="change"
                       hx-target="#err-{safe_id}"
                       hx-swap="innerHTML" />
                <label for="{safe_id}">{child.label}</label>
                <input type="hidden" name="{child_path}" value="false" />
                <div id="err-{safe_id}" class="field-error" style="margin-left: 0.5em;"></div>
            </div>
            """
        elif child.field_type == "select":
            safe_id = child_path.replace(".", "-").replace("[", "-").replace("]", "")
            options = "".join(
                f'<option value="{opt}" {"selected" if child.value == opt else ""}>{opt}</option>'
                for opt in (child.enum or [])
            )
            children_html += f"""
            <div class="form-row">
                <label for="{safe_id}">{child.label}</label>
                <select id="{safe_id}" name="{child_path}"
                        hx-post="/api/validate/{child_path}"
                        hx-trigger="change"
                        hx-target="#err-{safe_id}"
                        hx-swap="innerHTML">
                    {options}
                </select>
                <div id="err-{safe_id}" class="field-error"></div>
            </div>
            """
        else:
            children_html += _render_scalar_html(child, child_path)

    return children_html
