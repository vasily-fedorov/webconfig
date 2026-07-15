"""Validator — type validation and JSON Schema validation for config data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jsonschema


@dataclass
class ValidationError:
    """A single validation error with the field path and a human-readable message."""

    field_path: str
    message: str


class Validator:
    """Validates config data against type expectations and an optional JSON Schema."""

    def __init__(self, schema: dict | None = None) -> None:
        self.schema = schema

    # ------------------------------------------------------------------ public

    def validate(self, data: dict) -> list[ValidationError]:
        """Run type validation, then schema validation if a schema is available.

        Type validation walks the nested dict and coerces leaf values **in place**
        to the types declared in the schema.  Schema validation runs ``jsonschema``
        on the already-coerced instance.

        Returns a (possibly empty) list of ``ValidationError``.
        """
        errors: list[ValidationError] = []

        # Phase 1 – type coercion.  Values that can be converted are replaced
        # in *data* so that Phase 2 sees native Python types.
        errors.extend(self._coerce_types(data, schema_node=self.schema, prefix=""))

        # Phase 2 – jsonschema validation (only when a schema was provided).
        if self.schema is not None:
            errors.extend(self._validate_schema(data))

        return errors

    def validate_field(
        self,
        field_path: str,
        value: Any,
        expected_type: str | None = None,
    ) -> list[ValidationError]:
        """Validate a single field identified by its dotted path.

        *Type checking*:  resolves the expected type from one of:
         1. the explicit *expected_type* parameter,
         2. the schema (when ``self.schema`` is set),
         3. skipped – no type info available.

        *Schema checking* (when ``self.schema`` is set): resolves the
        schema node for *field_path* and validates the **coerced** value
        against it.
        """
        errors: list[ValidationError] = []

        # --- resolve expected type ---
        resolved_type = expected_type
        if resolved_type is None and self.schema is not None:
            node = self._resolve_schema_path(field_path)
            if node is not None:
                resolved_type = node.get("type")

        # --- type coercion ---
        coerced = value
        if resolved_type is not None:
            try:
                coerced = self._coerce_value(value, resolved_type)
            except (ValueError, TypeError):
                errors.append(
                    ValidationError(
                        field_path,
                        f"expected {resolved_type}, got '{value}'",
                    )
                )
                # If type coercion failed, skip schema validation – the
                # value can't satisfy schema constraints anyway.
                return errors

        # --- jsonschema validation (against the coerced value) ---
        if self.schema is not None:
            errors.extend(self._validate_single_field(field_path, coerced))

        return errors

    # ------------------------------------------------------------- internals

    @staticmethod
    def _coerce_value(value: Any, expected_type: str) -> Any:
        """Try to convert *value* to *expected_type*.

        Returns the coerced value on success.  Raises ``ValueError`` or
        ``TypeError`` when coercion is impossible.
        """
        if not isinstance(value, str):
            return value  # already a native Python type

        stripped = value.strip()

        if expected_type == "integer":
            if not stripped:
                raise ValueError("empty integer value")
            return int(stripped)

        if expected_type == "number":
            if not stripped:
                raise ValueError("empty number value")
            return float(stripped)

        if expected_type == "boolean":
            low = stripped.lower()
            if low in ("true", "1", "on", "yes"):
                return True
            if low in ("false", "0", "off", "no"):
                return False
            raise ValueError(f"unexpected boolean value '{value}'")

        # "string", "array", "object" – keep as-is.
        return value

    def _coerce_types(
        self,
        data: dict,
        schema_node: dict | None,
        prefix: str,
    ) -> list[ValidationError]:
        """Walk *data* recursively and coerce leaf values **in place**."""
        errors: list[ValidationError] = []

        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key

            child_schema: dict | None = None
            if schema_node is not None:
                props = schema_node.get("properties")
                if isinstance(props, dict):
                    child_schema = props.get(key)

            if isinstance(value, dict):
                errors.extend(self._coerce_types(value, child_schema, path))
            elif isinstance(value, list):
                errors.extend(self._coerce_list_types(value, child_schema, path))
            else:
                if child_schema is not None:
                    expected = child_schema.get("type")
                    if expected is not None and expected not in ("object", "array"):
                        try:
                            data[key] = self._coerce_value(value, expected)
                        except (ValueError, TypeError):
                            errors.append(
                                ValidationError(
                                    path,
                                    f"expected {expected}, got '{value}'",
                                )
                            )

        return errors

    def _coerce_list_types(
        self,
        items: list,
        schema_node: dict | None,
        prefix: str,
    ) -> list[ValidationError]:
        """Coerce array elements **in place** using the ``items`` sub-schema."""
        errors: list[ValidationError] = []

        item_schema: dict | None = None
        if schema_node is not None:
            item_schema = schema_node.get("items")

        for i, item in enumerate(items):
            item_path = f"{prefix}[{i}]"
            if isinstance(item, dict):
                errors.extend(self._coerce_types(item, item_schema, item_path))
            elif isinstance(item, list):
                errors.extend(self._coerce_list_types(item, item_schema, item_path))
            else:
                if item_schema is not None:
                    expected = item_schema.get("type")
                    if expected is not None and expected not in ("object", "array"):
                        try:
                            items[i] = self._coerce_value(item, expected)
                        except (ValueError, TypeError):
                            errors.append(
                                ValidationError(
                                    item_path,
                                    f"expected {expected}, got '{item}'",
                                )
                            )

        return errors

    def _validate_schema(self, data: dict) -> list[ValidationError]:
        """Run ``jsonschema`` validation on (already-coerced) *data*."""
        errors: list[ValidationError] = []
        try:
            v = jsonschema.Draft202012Validator(self.schema)  # type: ignore[arg-type]
            for err in v.iter_errors(data):
                field_path = (
                    ".".join(str(p) for p in err.absolute_path)
                    if err.absolute_path
                    else "(root)"
                )
                errors.append(
                    ValidationError(field_path, self._format_jsonschema_error(err))
                )
        except jsonschema.SchemaError:
            # Schema itself is invalid – skip schema-level validation.
            pass
        return errors

    def _validate_single_field(
        self,
        field_path: str,
        value: Any,
    ) -> list[ValidationError]:
        """Validate a single (already-coerced) value against its schema node."""
        errors: list[ValidationError] = []
        node = self._resolve_schema_path(field_path)
        if node is None:
            return errors

        try:
            v = jsonschema.Draft202012Validator(node)  # type: ignore[arg-type]
            for err in v.iter_errors(value):
                errors.append(
                    ValidationError(field_path, self._format_jsonschema_error(err))
                )
        except jsonschema.SchemaError:
            pass

        return errors

    def _resolve_schema_path(self, field_path: str) -> dict | None:
        """Walk the JSON Schema tree for a dotted *field_path*.

        ``field_path`` may include array-index notation (``items[0]``) which
        is resolved through the ``items`` sub-schema.
        """
        if self.schema is None:
            return None

        parts = field_path.split(".")
        node: dict = self.schema

        for part in parts:
            # Strip array index suffix, e.g. "features[2]" → "features".
            key = part
            has_index = False
            idx = part.find("[")
            if idx != -1:
                key = part[:idx]
                has_index = True

            props = node.get("properties")
            if not isinstance(props, dict) or key not in props:
                return None

            node = props[key]

            if has_index:
                items = node.get("items")
                if not isinstance(items, dict):
                    return None
                node = items

        return node

    @staticmethod
    def _format_jsonschema_error(error: jsonschema.ValidationError) -> str:
        """Map a ``jsonschema.ValidationError`` to a human-readable string."""
        validator = error.validator
        value = error.validator_value

        if validator == "required":
            return "field is required"
        if validator == "type":
            return f"expected {value}, got {error.instance}"
        if validator == "minimum":
            return f"must be ≥ {value}"
        if validator == "maximum":
            return f"must be ≤ {value}"
        if validator == "exclusiveMinimum":
            return f"must be > {value}"
        if validator == "exclusiveMaximum":
            return f"must be < {value}"
        if validator == "minLength":
            return f"must be at least {value} characters"
        if validator == "maxLength":
            return f"must be at most {value} characters"
        if validator == "minItems":
            return f"must have at least {value} items"
        if validator == "maxItems":
            return f"must have at most {value} items"
        if validator == "pattern":
            return f"must match pattern {value}"
        if validator == "enum":
            return f"must be one of: {', '.join(str(v) for v in value)}"

        return error.message
