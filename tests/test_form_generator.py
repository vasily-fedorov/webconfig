"""Tests for form generator."""

from webconfig.form_generator import Field, FormGenerator


class TestFormGenerator:
    def test_simple_fields(self):
        g = FormGenerator()
        root = g.generate({"name": "test", "port": 8080, "debug": True})
        children = {c.key: c for c in root.children}
        assert children["name"].field_type == "text"
        assert children["port"].field_type == "number"
        assert children["debug"].field_type == "boolean"

    def test_nested_objects(self):
        g = FormGenerator()
        root = g.generate({"server": {"host": "0.0.0.0", "port": 8080}})
        server = root.children[0]
        assert server.field_type == "object"
        assert server.key == "server"
        host = [c for c in server.children if c.key == "host"][0]
        assert host.path == "server.host"
        assert host.depth == 2

    def test_array_of_strings(self):
        g = FormGenerator()
        root = g.generate({"names": ["a", "b", "c"]})
        arr = root.children[0]
        assert arr.field_type == "array"
        assert arr.item_type == "text"
        assert len(arr.children) == 3
        assert arr.children[1].key == "[1]"
        assert arr.children[1].value == "b"

    def test_array_of_objects(self):
        g = FormGenerator()
        root = g.generate({"items": [{"name": "a"}, {"name": "b"}]})
        arr = root.children[0]
        assert arr.field_type == "array"
        assert arr.item_type == "object"
        assert len(arr.children) == 2
        first_item = arr.children[0]
        assert first_item.field_type == "object"
        assert len(first_item.children) == 1
        assert first_item.children[0].key == "name"

    def test_schema_enum_to_select(self):
        g = FormGenerator()
        schema = {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["debug", "info", "error"]}
            },
        }
        root = g.generate({"level": "info"}, schema)
        field = root.children[0]
        assert field.field_type == "select"
        assert field.enum == ["debug", "info", "error"]

    def test_schema_default(self):
        g = FormGenerator()
        schema = {
            "type": "object",
            "properties": {
                "timeout": {"type": "integer", "default": 30}
            },
        }
        root = g.generate({}, schema)
        field = root.children[0]
        assert field.value == 30
        assert field.default == 30

    def test_schema_required(self):
        g = FormGenerator()
        schema = {
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        }
        root = g.generate({"host": "0.0.0.0"}, schema)
        assert root.children[0].required is True

    def test_schema_constraints(self):
        g = FormGenerator()
        schema = {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "minimum": 1, "maximum": 65535}
            },
        }
        root = g.generate({"port": 8080}, schema)
        field = root.children[0]
        assert field.constraints == {"minimum": 1, "maximum": 65535}

    def test_textarea_for_long_strings(self):
        g = FormGenerator()
        root = g.generate({"desc": "x" * 100})
        assert root.children[0].field_type == "textarea"

    def test_schema_title_as_label(self):
        g = FormGenerator()
        schema = {
            "type": "object",
            "properties": {"server_port": {"type": "integer", "title": "Server Port"}},
        }
        root = g.generate({"server_port": 8080}, schema)
        assert root.children[0].label == "Server Port"

    def test_null_value(self):
        g = FormGenerator()
        root = g.generate({"opt": None})
        assert root.children[0].field_type == "null"

    def test_empty_dict(self):
        g = FormGenerator()
        root = g.generate({})
        assert root.field_type == "object"
        assert len(root.children) == 0
