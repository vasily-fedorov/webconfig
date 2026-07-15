"""Form model and FormGenerator — converts parsed config dict into a Field tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Field:
    key: str
    label: str
    field_type: str  # "text" | "number" | "boolean" | "select" | "textarea" | "object" | "array" | "null"
    value: Any
    depth: int = 0
    path: str = ""
    description: str | None = None
    enum: list[str] | None = None
    default: Any = None
    required: bool = False
    constraints: dict = field(default_factory=dict)
    children: list[Field] = field(default_factory=list)
    item_type: str | None = None  # for arrays: "text" | "number" | "object" | ...


class FormGenerator:
    """Converts a config dict (and optional JSON Schema) into a Field tree."""

    # ── type inference (no schema) ──────────────────────────────────────

    @staticmethod
    def _infer_type(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str):
            return "textarea" if len(value) > 40 else "text"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "text"  # str() coercion fallback

    @staticmethod
    def _infer_item_type(arr: list) -> str:
        if not arr:
            return "text"
        first = arr[0]
        if isinstance(first, bool):
            return "boolean"
        if isinstance(first, (int, float)):
            return "number"
        if isinstance(first, str):
            return "text"
        if isinstance(first, dict):
            return "object"
        if isinstance(first, list):
            return "array"
        return "text"

    # ── schema-driven type mapping ──────────────────────────────────────

    @staticmethod
    def _map_schema_type(schema_node: dict, value: Any) -> str:
        if "enum" in schema_node:
            return "select"

        t = schema_node.get("type", "string")

        if t == "string":
            max_len = schema_node.get("maxLength")
            if max_len is not None and max_len > 80:
                return "textarea"
            if max_len is None and isinstance(value, str) and len(value) > 40:
                return "textarea"
            return "text"

        if t in ("number", "integer"):
            return "number"
        if t == "boolean":
            return "boolean"
        if t == "object":
            return "object"
        if t == "array":
            return "array"
        return "text"  # fallback

    _ITEMS_TYPE_MAP = {
        "string": "text",
        "number": "number",
        "integer": "number",
        "boolean": "boolean",
        "object": "object",
        "array": "array",
    }

    @staticmethod
    def _extract_constraints(schema_node: dict) -> dict:
        constraints: dict = {}
        for k in ("minimum", "maximum", "minLength", "maxLength", "pattern"):
            if k in schema_node:
                constraints[k] = schema_node[k]
        return constraints

    @staticmethod
    def _make_label(key: str, schema_node: dict | None = None) -> str:
        if schema_node and schema_node.get("title"):
            return schema_node["title"]
        return key.replace("_", " ").title()

    @staticmethod
    def _make_path(prefix: str, key: str) -> str:
        if prefix:
            return f"{prefix}.{key}"
        return key

    # ── tree building ───────────────────────────────────────────────────

    def generate(self, data: dict, schema: dict | None = None) -> Field:
        """Build a Field tree from *data* optionally enriched by *schema*."""
        root = Field(
            key="",
            label="",
            field_type="object",
            value=data,
            depth=0,
            path="",
        )
        root.children = self._build_children(data, schema, depth=0, path_prefix="")
        return root

    def _build_children(
        self,
        data: dict,
        schema_node: dict | None,
        depth: int,
        path_prefix: str,
    ) -> list[Field]:
        children: list[Field] = []

        # build required set from schema
        required_set: set[str] = set()
        if schema_node and "required" in schema_node:
            required_set = set(schema_node["required"])

        # union of data keys and schema properties
        all_keys: set[str] = set(data.keys())
        if schema_node and "properties" in schema_node:
            all_keys |= set(schema_node["properties"].keys())

        for key in sorted(all_keys):
            key_in_data = key in data
            value = data.get(key)
            prop_schema: dict | None = None
            if schema_node and "properties" in schema_node:
                prop_schema = schema_node["properties"].get(key)

            # apply schema default when key is missing from data
            if not key_in_data and prop_schema and "default" in prop_schema:
                value = prop_schema["default"]

            field_path = self._make_path(path_prefix, key)

            # drive type from schema or infer from python value
            if prop_schema:
                field_type = self._map_schema_type(prop_schema, value)
                description = prop_schema.get("description")
                enum_vals = prop_schema.get("enum")
                default = prop_schema.get("default")
                required = key in required_set
                constraints = self._extract_constraints(prop_schema)
                label = self._make_label(key, prop_schema)
            else:
                field_type = self._infer_type(value)
                description = None
                enum_vals = None
                default = None
                required = False
                constraints = {}
                label = self._make_label(key)

            field_obj = Field(
                key=key,
                label=label,
                field_type=field_type,
                value=value,
                depth=depth + 1,
                path=field_path,
                description=description,
                enum=enum_vals,
                default=default,
                required=required,
                constraints=constraints,
            )

            # nested object → recurse
            if isinstance(value, dict):
                field_obj.field_type = "object"
                nested_schema = prop_schema if prop_schema else None
                field_obj.children = self._build_children(
                    value, nested_schema, depth + 1, field_path
                )
            elif field_obj.field_type == "object" and value is None:
                nested_schema = prop_schema if prop_schema else None
                field_obj.children = self._build_children(
                    {}, nested_schema, depth + 1, field_path
                )

            # array → build element children
            if isinstance(value, list):
                field_obj.field_type = "array"
                field_obj.item_type = self._resolve_item_type(prop_schema, value)

                items_schema = prop_schema.get("items", {}) if prop_schema else None
                field_obj.children = self._build_array_children(
                    value, items_schema, depth + 1, field_path, field_obj.item_type
                )
            elif field_obj.field_type == "array" and value is None:
                field_obj.item_type = self._resolve_item_type(prop_schema, [])
                items_schema = prop_schema.get("items", {}) if prop_schema else None
                field_obj.children = self._build_array_children(
                    [], items_schema, depth + 1, field_path, field_obj.item_type
                )

            children.append(field_obj)

        return children

    def _resolve_item_type(self, prop_schema: dict | None, arr: list) -> str:
        if prop_schema and "items" in prop_schema:
            items_type = prop_schema["items"].get("type", "string")
            return self._ITEMS_TYPE_MAP.get(items_type, "text")
        return self._infer_item_type(arr)

    def _build_array_children(
        self,
        arr: list,
        items_schema: dict | None,
        depth: int,
        path_prefix: str,
        item_type: str,
    ) -> list[Field]:
        children: list[Field] = []
        for i, element in enumerate(arr):
            element_path = f"{path_prefix}[{i}]"
            element_field = Field(
                key=f"[{i}]",
                label=f"[{i}]",
                field_type=item_type,
                value=element,
                depth=depth,
                path=element_path,
            )
            if item_type == "object" and isinstance(element, dict):
                element_field.children = self._build_children(
                    element, items_schema, depth + 1, element_path
                )
            children.append(element_field)
        return children
