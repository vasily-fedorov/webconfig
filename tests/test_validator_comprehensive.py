"""Comprehensive tests for validator — all JSON Schema types, constraints, coercion, edge cases."""

import pytest
from webconfig.validator import Validator, ValidationError


FULL_SCHEMA = {
    "type": "object",
    "required": ["host", "port"],
    "properties": {
        "host": {
            "type": "string",
            "title": "Server Host",
            "description": "Hostname or IP",
            "default": "127.0.0.1",
        },
        "port": {
            "type": "integer",
            "minimum": 1,
            "maximum": 65535,
            "description": "TCP port",
        },
        "debug": {
            "type": "boolean",
            "default": False,
        },
        "log_level": {
            "type": "string",
            "enum": ["debug", "info", "warn", "error"],
            "default": "info",
        },
        "description": {
            "type": "string",
            "maxLength": 500,
        },
        "timeout": {
            "type": "number",
            "minimum": 0.1,
            "maximum": 300.0,
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "servers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "host": {"type": "string"},
                    "port": {"type": "integer"},
                },
            },
        },
    },
}


class TestValidatorAllTypes:
    """Test validator with all JSON Schema types."""

    def test_string_type_ok(self):
        v = Validator({"type": "object", "properties": {"name": {"type": "string"}}})
        errors = v.validate({"name": "hello"})
        assert len(errors) == 0

    def test_string_type_with_number_rejected(self):
        v = Validator({"type": "object", "properties": {"name": {"type": "string"}}})
        errors = v.validate({"name": 42})
        assert len(errors) >= 1  # jsonschema rejects int for string type

    def test_integer_type_ok(self):
        v = Validator({"type": "object", "properties": {"port": {"type": "integer"}}})
        errors = v.validate({"port": "8080"})
        assert len(errors) == 0
        assert isinstance(errors, list)

    def test_integer_coerced_in_place(self):
        v = Validator({"type": "object", "properties": {"port": {"type": "integer"}}})
        data = {"port": "8080"}
        v.validate(data)
        assert data["port"] == 8080

    def test_integer_invalid(self):
        v = Validator({"type": "object", "properties": {"port": {"type": "integer"}}})
        errors = v.validate({"port": "abc"})
        assert any("expected integer" in e.message for e in errors)

    def test_number_float_ok(self):
        v = Validator({"type": "object", "properties": {"ratio": {"type": "number"}}})
        errors = v.validate({"ratio": "3.14"})
        assert len(errors) == 0
        # Note: number type coercion converts to float

    def test_number_int_coerces(self):
        v = Validator({"type": "object", "properties": {"ratio": {"type": "number"}}})
        data = {"ratio": "3.14"}
        v.validate(data)
        assert data["ratio"] == 3.14

    def test_boolean_true_variants(self):
        v = Validator({"type": "object", "properties": {"enabled": {"type": "boolean"}}})
        for val in ("true", "1", "on", "yes", "True", "TRUE"):
            data = {"enabled": val}
            errors = v.validate(data)
            assert len(errors) == 0, f"'{val}' should coerce to True"
            assert data["enabled"] is True

    def test_boolean_false_variants(self):
        v = Validator({"type": "object", "properties": {"enabled": {"type": "boolean"}}})
        for val in ("false", "0", "off", "no", "False", "FALSE"):
            data = {"enabled": val}
            errors = v.validate(data)
            assert len(errors) == 0, f"'{val}' should coerce to False"
            assert data["enabled"] is False

    def test_boolean_invalid(self):
        v = Validator({"type": "object", "properties": {"enabled": {"type": "boolean"}}})
        errors = v.validate({"enabled": "maybe"})
        assert any("boolean" in e.message.lower() for e in errors)

    def test_enum_valid(self):
        v = Validator({
            "type": "object",
            "properties": {"level": {"type": "string", "enum": ["debug", "info", "error"]}},
        })
        assert len(v.validate({"level": "debug"})) == 0
        assert len(v.validate({"level": "info"})) == 0

    def test_enum_invalid(self):
        v = Validator({
            "type": "object",
            "properties": {"level": {"type": "string", "enum": ["debug", "info"]}},
        })
        errors = v.validate({"level": "trace"})
        assert len(errors) > 0

    def test_null_type(self):
        v = Validator({"type": "object", "properties": {"opt": {"type": "null"}}})
        errors = v.validate({"opt": None})
        assert len(errors) == 0


class TestConstraints:
    """Test constraint validation."""

    def test_minimum_violation(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "minimum": 1}},
        })
        errors = v.validate({"port": 0})
        assert len(errors) > 0

    def test_minimum_ok(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "minimum": 1}},
        })
        assert len(v.validate({"port": 1})) == 0

    def test_maximum_violation(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "maximum": 65535}},
        })
        errors = v.validate({"port": 99999})
        assert len(errors) > 0

    def test_min_length_violation(self):
        v = Validator({
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 3}},
        })
        errors = v.validate({"name": "ab"})
        assert len(errors) > 0

    def test_min_length_ok(self):
        v = Validator({
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 3}},
        })
        assert len(v.validate({"name": "abc"})) == 0

    def test_max_length_violation(self):
        v = Validator({
            "type": "object",
            "properties": {"code": {"type": "string", "maxLength": 5}},
        })
        errors = v.validate({"code": "123456"})
        assert len(errors) > 0

    def test_pattern_violation(self):
        v = Validator({
            "type": "object",
            "properties": {"host": {"type": "string", "pattern": r"^\d+\.\d+\.\d+\.\d+$"}},
        })
        errors = v.validate({"host": "not-an-ip"})
        assert len(errors) > 0

    def test_pattern_ok(self):
        v = Validator({
            "type": "object",
            "properties": {"host": {"type": "string", "pattern": r"^\d+\.\d+\.\d+\.\d+$"}},
        })
        assert len(v.validate({"host": "192.168.1.1"})) == 0

    def test_multiple_constraints(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "minimum": 1, "maximum": 65535}},
        })
        assert len(v.validate({"port": 8080})) == 0
        assert len(v.validate({"port": 0})) > 0
        assert len(v.validate({"port": 99999})) > 0


class TestRequiredFields:
    """Test required field validation."""

    def test_required_missing(self):
        v = Validator({
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        })
        errors = v.validate({})
        assert any("required" in e.message.lower() for e in errors)

    def test_required_present(self):
        v = Validator({
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        })
        assert len(v.validate({"host": "0.0.0.0"})) == 0

    def test_required_with_default_coercion(self):
        v = Validator({
            "type": "object",
            "properties": {"host": {"type": "string", "default": "localhost"}},
            "required": ["host"],
        })
        errors = v.validate({})
        # Required missing — no default applied in validation, only in form generator
        assert any("required" in e.message.lower() for e in errors)


class TestNestedValidation:
    """Test validation of nested objects."""

    def test_nested_object_valid(self):
        v = Validator({
            "type": "object",
            "properties": {
                "server": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string"},
                        "port": {"type": "integer"},
                    },
                }
            },
        })
        data = {"server": {"host": "0.0.0.0", "port": "8080"}}
        errors = v.validate(data)
        assert len(errors) == 0
        assert data["server"]["port"] == 8080

    def test_nested_object_invalid(self):
        v = Validator({
            "type": "object",
            "properties": {
                "server": {
                    "type": "object",
                    "properties": {"port": {"type": "integer", "minimum": 1}},
                }
            },
        })
        errors = v.validate({"server": {"port": 0}})
        assert len(errors) > 0

    def test_deeply_nested(self):
        v = Validator({
            "type": "object",
            "properties": {
                "a": {
                    "type": "object",
                    "properties": {
                        "b": {
                            "type": "object",
                            "properties": {"c": {"type": "integer"}},
                        }
                    },
                }
            },
        })
        data = {"a": {"b": {"c": "42"}}}
        errors = v.validate(data)
        assert len(errors) == 0
        assert data["a"]["b"]["c"] == 42


class TestArrayValidation:
    """Test validation of arrays."""

    def test_array_of_strings_valid(self):
        v = Validator({
            "type": "object",
            "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
        })
        assert len(v.validate({"tags": ["a", "b"]})) == 0

    def test_array_min_items_violation(self):
        v = Validator({
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1}
            },
        })
        errors = v.validate({"tags": []})
        assert len(errors) > 0

    def test_array_of_numbers_coercion(self):
        v = Validator({
            "type": "object",
            "properties": {"ports": {"type": "array", "items": {"type": "integer"}}},
        })
        data = {"ports": ["80", "443"]}
        errors = v.validate(data)
        assert len(errors) == 0
        assert data["ports"] == [80, 443]

    def test_array_of_objects_valid(self):
        v = Validator({
            "type": "object",
            "properties": {
                "servers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "port": {"type": "integer"},
                        },
                    },
                }
            },
        })
        data = {"servers": [{"name": "s1", "port": "80"}, {"name": "s2", "port": "443"}]}
        errors = v.validate(data)
        assert len(errors) == 0
        assert data["servers"][0]["port"] == 80
        assert data["servers"][1]["port"] == 443


class TestSingleFieldValidation:
    """Test validate_field() method."""

    def test_valid_field(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "minimum": 1}},
        })
        assert len(v.validate_field("port", "8080")) == 0

    def test_invalid_field(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "minimum": 1}},
        })
        errors = v.validate_field("port", "abc")
        assert len(errors) == 1
        assert "expected integer" in errors[0].message

    def test_constraint_field(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "minimum": 1, "maximum": 65535}},
        })
        assert len(v.validate_field("port", "0")) > 0
        assert len(v.validate_field("port", "99999")) > 0

    def test_field_no_schema(self):
        v = Validator()
        assert len(v.validate_field("any", "value")) == 0

    def test_field_unknown_path(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer"}},
        })
        assert len(v.validate_field("nonexistent", "value")) == 0


class TestFullSchema:
    """Test with the full fixture schema."""

    def test_full_valid_data(self):
        v = Validator(FULL_SCHEMA)
        data = {
            "host": "0.0.0.0",
            "port": "8080",
            "debug": "true",
            "log_level": "info",
            "tags": ["web", "api"],
        }
        errors = v.validate(data)
        assert len(errors) == 0

    def test_full_missing_required(self):
        v = Validator(FULL_SCHEMA)
        errors = v.validate({"port": "8080"})
        assert any("required" in e.message.lower() for e in errors)

    def test_full_port_out_of_range(self):
        v = Validator(FULL_SCHEMA)
        errors = v.validate({"host": "0.0.0.0", "port": "99999"})
        assert len(errors) > 0

    def test_full_enum_invalid(self):
        v = Validator(FULL_SCHEMA)
        data = {"host": "0.0.0.0", "port": "8080", "log_level": "trace"}
        errors = v.validate(data)
        assert len(errors) > 0

    def test_full_array_of_objects(self):
        v = Validator(FULL_SCHEMA)
        data = {
            "host": "0.0.0.0",
            "port": "8080",
            "servers": [
                {"name": "primary", "host": "10.0.0.1", "port": "443"},
                {"name": "backup", "host": "10.0.0.2", "port": "443"},
            ],
        }
        errors = v.validate(data)
        assert len(errors) == 0

    def test_no_schema_no_errors(self):
        v = Validator()
        errors = v.validate({"anything": "goes", "nested": {"deep": True}})
        assert len(errors) == 0
