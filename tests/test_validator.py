"""Tests for validator."""

from webconfig.validator import Validator, ValidationError


class TestValidator:
    def test_no_schema_no_errors(self):
        v = Validator()
        errors = v.validate({"key": "val"})
        assert len(errors) == 0

    def test_type_coercion_integer(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer"}},
        })
        data = {"port": "8080"}
        errors = v.validate(data)
        assert len(errors) == 0
        assert data["port"] == 8080  # coerced in place

    def test_type_coercion_failure(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer"}},
        })
        data = {"port": "abc"}
        errors = v.validate(data)
        # Two errors: one from type coercion, one from jsonschema type check
        assert len(errors) >= 1
        assert any("expected integer" in e.message for e in errors)

    def test_type_coercion_boolean(self):
        v = Validator({
            "type": "object",
            "properties": {"debug": {"type": "boolean"}},
        })
        data = {"debug": "true"}
        errors = v.validate(data)
        assert len(errors) == 0
        assert data["debug"] is True

    def test_schema_validation_minimum(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "minimum": 1, "maximum": 65535}},
        })
        errors = v.validate({"port": 0})
        assert len(errors) >= 1
        assert any("minimum" in e.message.lower() or "≥" in e.message for e in errors)

    def test_schema_validation_required(self):
        v = Validator({
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        })
        errors = v.validate({})
        assert len(errors) >= 1
        assert any("required" in e.message.lower() for e in errors)

    def test_schema_validation_enum(self):
        v = Validator({
            "type": "object",
            "properties": {"level": {"type": "string", "enum": ["debug", "info"]}},
        })
        errors = v.validate({"level": "invalid"})
        assert len(errors) >= 1

    def test_validate_field(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer", "minimum": 1}},
        })
        errors = v.validate_field("port", "abc")
        assert len(errors) == 1
        assert "expected integer" in errors[0].message

    def test_validate_field_ok(self):
        v = Validator({
            "type": "object",
            "properties": {"port": {"type": "integer"}},
        })
        errors = v.validate_field("port", "8080")
        assert len(errors) == 0

    def test_nested_coercion(self):
        v = Validator({
            "type": "object",
            "properties": {
                "server": {
                    "type": "object",
                    "properties": {"port": {"type": "integer"}},
                }
            },
        })
        data = {"server": {"port": "8080"}}
        errors = v.validate(data)
        assert len(errors) == 0
        assert data["server"]["port"] == 8080

    def test_array_coercion(self):
        v = Validator({
            "type": "object",
            "properties": {
                "ports": {
                    "type": "array",
                    "items": {"type": "integer"},
                }
            },
        })
        data = {"ports": ["80", "443"]}
        errors = v.validate(data)
        assert len(errors) == 0
        assert data["ports"] == [80, 443]

    def test_no_schema_passes(self):
        v = Validator()
        errors = v.validate_field("any", "value")
        assert len(errors) == 0
