"""Comprehensive tests for form-to-dict parsing — all key patterns, arrays, edge cases."""

import pytest
from webconfig.server import _parse_key, _form_to_dict, _parse_form_value


class TestParseKey:
    """Test key path parser."""

    def test_simple_key(self):
        assert _parse_key("name") == ["name"]

    def test_dotted_key(self):
        assert _parse_key("server.host") == ["server", "host"]

    def test_deep_nesting(self):
        assert _parse_key("a.b.c.d") == ["a", "b", "c", "d"]

    def test_array_index(self):
        assert _parse_key("items[0]") == ["items", 0]

    def test_array_index_high(self):
        assert _parse_key("items[42]") == ["items", 42]

    def test_array_of_objects(self):
        assert _parse_key("servers[0].name") == ["servers", 0, "name"]

    def test_array_of_objects_deep(self):
        assert _parse_key("config.servers[2].host.port") == ["config", "servers", 2, "host", "port"]

    def test_multiple_array_indices(self):
        assert _parse_key("matrix[0][1]") == ["matrix", 0, 1]

    def test_nested_in_object(self):
        assert _parse_key("features.names[0]") == ["features", "names", 0]


class TestParseFormValue:
    """Test value parsing."""

    def test_empty_string(self):
        assert _parse_form_value("") == ""

    def test_true(self):
        assert _parse_form_value("true") is True

    def test_false(self):
        assert _parse_form_value("false") is False

    def test_integer(self):
        assert _parse_form_value("42") == 42
        assert _parse_form_value("-10") == -10
        assert _parse_form_value("0") == 0

    def test_float(self):
        assert _parse_form_value("3.14") == 3.14
        assert _parse_form_value("-0.5") == -0.5

    def test_string(self):
        assert _parse_form_value("hello") == "hello"
        assert _parse_form_value("192.168.1.1") == "192.168.1.1"


class TestFormToDict:
    """Test form data to nested dict conversion."""

    def test_flat_scalars(self):
        result = _form_to_dict({"name": "test", "port": "8080", "debug": "true"})
        assert result == {"name": "test", "port": 8080, "debug": True}

    def test_nested_one_level(self):
        result = _form_to_dict({"server.host": "0.0.0.0", "server.port": "9090"})
        assert result == {"server": {"host": "0.0.0.0", "port": 9090}}

    def test_nested_multi_level(self):
        result = _form_to_dict({"a.b.c": "deep", "a.b.d": "value"})
        assert result == {"a": {"b": {"c": "deep", "d": "value"}}}

    def test_array_of_strings(self):
        result = _form_to_dict({"tags[0]": "web", "tags[1]": "api", "tags[2]": "db"})
        assert result == {"tags": ["web", "api", "db"]}

    def test_array_of_strings_sparse(self):
        result = _form_to_dict({"tags[0]": "web", "tags[5]": "db"})
        assert len(result["tags"]) == 6
        assert result["tags"][0] == "web"
        assert result["tags"][5] == "db"

    def test_array_of_objects(self):
        result = _form_to_dict({
            "servers[0].name": "primary",
            "servers[0].host": "10.0.0.1",
            "servers[1].name": "backup",
            "servers[1].host": "10.0.0.2",
        })
        assert result == {
            "servers": [
                {"name": "primary", "host": "10.0.0.1"},
                {"name": "backup", "host": "10.0.0.2"},
            ]
        }

    def test_array_inside_object(self):
        result = _form_to_dict({
            "features.names[0]": "auth",
            "features.names[1]": "api",
            "features.enabled": "true",
        })
        assert result == {
            "features": {
                "names": ["auth", "api"],
                "enabled": True,
            }
        }

    def test_mixed_nested_and_arrays(self):
        result = _form_to_dict({
            "server.host": "localhost",
            "server.ports[0]": "80",
            "server.ports[1]": "443",
            "database.url": "postgres://db",
            "database.pool.size": "10",
            "database.pool.timeout": "30",
            "debug": "false",
        })
        assert result["server"]["host"] == "localhost"
        assert result["server"]["ports"] == [80, 443]
        assert result["database"]["pool"]["size"] == 10
        assert result["debug"] is False

    def test_nested_arrays(self):
        result = _form_to_dict({
            "matrix[0][0]": "1",
            "matrix[0][1]": "2",
            "matrix[1][0]": "3",
            "matrix[1][1]": "4",
        })
        assert result == {"matrix": [[1, 2], [3, 4]]}

    def test_empty_form(self):
        result = _form_to_dict({})
        assert result == {}

    def test_single_key(self):
        result = _form_to_dict({"name": "test"})
        assert result == {"name": "test"}

    def test_boolean_in_array(self):
        result = _form_to_dict({"flags[0]": "true", "flags[1]": "false"})
        assert result == {"flags": [True, False]}

    def test_numbers_in_object_array(self):
        result = _form_to_dict({
            "ports[0].name": "http",
            "ports[0].number": "80",
            "ports[1].name": "https",
            "ports[1].number": "443",
        })
        assert result["ports"] == [
            {"name": "http", "number": 80},
            {"name": "https", "number": 443},
        ]

    def test_form_roundtrip_structure(self):
        """Simulate a full form submission and verify structure integrity."""
        form = {
            "server.host": "0.0.0.0",
            "server.port": "8080",
            "server.debug": "true",
            "database.url": "postgres://localhost/db",
            "database.pool_size": "10",
            "database.timeout": "30.0",
            "logging.level": "info",
            "logging.file": "/var/log/app.log",
            "logging.format": "json",
            "features.enabled": "true",
            "features.max_items": "100",
            "features.names[0]": "auth",
            "features.names[1]": "api",
            "features.names[2]": "webhooks",
            "servers[0].name": "primary",
            "servers[0].host": "10.0.0.1",
            "servers[0].port": "443",
            "servers[1].name": "backup",
            "servers[1].host": "10.0.0.2",
            "servers[1].port": "443",
        }
        result = _form_to_dict(form)

        # Check structure
        assert "server" in result
        assert result["server"]["host"] == "0.0.0.0"
        assert result["server"]["port"] == 8080
        assert result["server"]["debug"] is True

        assert "database" in result
        assert result["database"]["url"] == "postgres://localhost/db"
        assert result["database"]["pool_size"] == 10
        assert result["database"]["timeout"] == 30.0

        assert "logging" in result
        assert result["logging"]["level"] == "info"

        assert "features" in result
        assert result["features"]["names"] == ["auth", "api", "webhooks"]
        assert result["features"]["enabled"] is True
        assert result["features"]["max_items"] == 100

        assert "servers" in result
        assert len(result["servers"]) == 2
        assert result["servers"][0] == {"name": "primary", "host": "10.0.0.1", "port": 443}
        assert result["servers"][1] == {"name": "backup", "host": "10.0.0.2", "port": 443}
