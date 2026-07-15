"""Tests for config parser."""

import pytest
from webconfig.parser import ConfigParseError, ConfigParser


class TestParse:
    def test_parse_toml_simple(self):
        cfg = ConfigParser.parse('name = "test"\nport = 8080', "config.toml")
        assert cfg.format == "toml"
        assert cfg.data == {"name": "test", "port": 8080}

    def test_parse_toml_nested(self):
        text = '[server]\nhost = "0.0.0.0"\nport = 8080\n'
        cfg = ConfigParser.parse(text, "config.toml")
        assert cfg.data == {"server": {"host": "0.0.0.0", "port": 8080}}

    def test_parse_json(self):
        cfg = ConfigParser.parse('{"key": "val", "num": 42}', "cfg.json")
        assert cfg.format == "json"
        assert cfg.data == {"key": "val", "num": 42}

    def test_parse_env(self):
        cfg = ConfigParser.parse("KEY=val\nPORT=3000\n# comment\n", "config.env")
        assert cfg.format == "env"
        assert cfg.data == {"KEY": "val", "PORT": "3000"}

    def test_parse_env_dotfile(self):
        cfg = ConfigParser.parse("FOO=bar", ".env")
        assert cfg.format == "env"
        assert cfg.data == {"FOO": "bar"}

    def test_parse_invalid_toml(self):
        with pytest.raises(ConfigParseError, match="Failed to parse toml"):
            ConfigParser.parse("[server\nhost = bad", "config.toml")

    def test_parse_invalid_json(self):
        with pytest.raises(ConfigParseError, match="Failed to parse json"):
            ConfigParser.parse("{bad json}", "cfg.json")

    def test_parse_unsupported_extension(self):
        with pytest.raises(ConfigParseError, match="Unsupported file extension"):
            ConfigParser.parse("foo", "config.yml")


class TestSerialize:
    def test_serialize_toml_simple(self):
        data = {"name": "test", "port": 8080}
        s = ConfigParser.serialize(data, "config.toml")
        assert 'name = "test"' in s
        assert "port = 8080" in s

    def test_serialize_toml_nested(self):
        data = {"server": {"host": "0.0.0.0", "port": 8080}}
        s = ConfigParser.serialize(data, "config.toml")
        assert "[server]" in s
        assert 'host = "0.0.0.0"' in s

    def test_serialize_json(self):
        data = {"key": "val"}
        s = ConfigParser.serialize(data, "cfg.json")
        assert '"key": "val"' in s

    def test_serialize_env(self):
        data = {"KEY": "val", "PORT": "3000"}
        s = ConfigParser.serialize(data, ".env")
        assert "KEY=val" in s
        assert "PORT=3000" in s

    def test_roundtrip_toml(self):
        original = {"server": {"host": "0.0.0.0", "port": 8080}, "debug": True}
        s = ConfigParser.serialize(original, "config.toml")
        cfg = ConfigParser.parse(s, "config.toml")
        assert cfg.data["server"]["host"] == "0.0.0.0"
        assert cfg.data["server"]["port"] == 8080
        assert cfg.data["debug"] is True

    def test_serialize_none_skipped(self):
        data = {"key": "val", "skipped": None}
        s = ConfigParser.serialize(data, "config.toml")
        assert "skipped" not in s
        assert "key" in s
