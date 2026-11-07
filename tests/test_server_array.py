"""Tests for the array add/remove endpoints and their path helpers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from webconfig.form_generator import FormGenerator
from webconfig.server import (
    _add_array_element,
    _find_field,
    _remove_array_element,
    create_app,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def app(tmp_path):
    """App backed by a writable copy of the TOML fixture and its schema."""
    config = tmp_path / "config.toml"
    shutil.copy(FIXTURES / "config.toml", config)
    schema = json.loads((FIXTURES / "schema.json").read_text())
    application = create_app(str(config), schema)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


class TestArrayAddEndpoint:
    def test_add_scalar_appends_element(self, client, app):
        before = list(app.config["CONFIG_DATA"]["features"]["names"])

        response = client.post("/api/array/add/features.names")

        assert response.status_code == 200
        after = app.config["CONFIG_DATA"]["features"]["names"]
        assert len(after) == len(before) + 1
        assert after[: len(before)] == before

    def test_add_scalar_renders_input_for_new_index(self, client, app):
        count = len(app.config["CONFIG_DATA"]["features"]["names"])

        html = client.post("/api/array/add/features.names").get_data(as_text=True)

        assert f'name="features.names[{count}]"' in html
        assert 'id="array-features-names"' in html

    def test_add_object_appends_element_matching_sibling_shape(self, client, app):
        before = list(app.config["CONFIG_DATA"]["servers"])

        response = client.post("/api/array/add/servers")

        assert response.status_code == 200
        servers = app.config["CONFIG_DATA"]["servers"]
        assert len(servers) == len(before) + 1
        assert sorted(servers[-1]) == sorted(before[0])
        assert servers[-1] == {"host": "", "name": "", "port": 0}

    def test_add_object_renders_fields_for_new_item(self, client, app):
        index = len(app.config["CONFIG_DATA"]["servers"])

        html = client.post("/api/array/add/servers").get_data(as_text=True)

        assert f'name="servers[{index}].name"' in html
        assert f'name="servers[{index}].host"' in html

    def test_add_to_empty_schema_typed_array_uses_schema_default(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text("thresholds = []\n")
        schema = {
            "type": "object",
            "properties": {
                "thresholds": {"type": "array", "items": {"type": "integer"}},
            },
        }
        app = create_app(str(config), schema)
        app.config["TESTING"] = True

        response = app.test_client().post("/api/array/add/thresholds")

        assert response.status_code == 200
        assert app.config["CONFIG_DATA"]["thresholds"] == [0]


class TestArrayRemoveEndpoint:
    def test_remove_scalar_drops_that_element(self, client, app):
        before = list(app.config["CONFIG_DATA"]["features"]["names"])

        response = client.delete("/api/array/remove/features.names/0")

        assert response.status_code == 200
        assert app.config["CONFIG_DATA"]["features"]["names"] == before[1:]

    def test_remove_object_drops_that_element(self, client, app):
        before = list(app.config["CONFIG_DATA"]["servers"])

        response = client.delete("/api/array/remove/servers/1")

        assert response.status_code == 200
        assert app.config["CONFIG_DATA"]["servers"] == [before[0], before[2]]

    def test_remove_rerenders_remaining_items(self, client, app):
        html = client.delete("/api/array/remove/servers/0").get_data(as_text=True)

        assert 'name="servers[0].name"' in html
        assert 'name="servers[2].name"' not in html

    def test_remove_out_of_range_leaves_array_untouched(self, client, app):
        before = list(app.config["CONFIG_DATA"]["features"]["names"])

        response = client.delete("/api/array/remove/features.names/99")

        assert response.status_code == 200
        assert app.config["CONFIG_DATA"]["features"]["names"] == before


class TestArrayHelpers:
    def test_add_to_array_nested_inside_array_item(self):
        data = {"servers": [{"name": "a"}]}

        _add_array_element(data, "servers[0].tags")

        assert data == {"servers": [{"name": "a", "tags": [""]}]}

    def test_add_leaves_non_list_value_untouched(self):
        data = {"server": {"port": 8080}}

        _add_array_element(data, "server.port")

        assert data == {"server": {"port": 8080}}

    def test_add_to_missing_nested_path_creates_only_the_array(self):
        data = {}

        _add_array_element(data, "a.b")

        assert data == {"a": {"b": [""]}}

    def test_remove_from_array_nested_inside_array_item(self):
        data = {"servers": [{"tags": ["a", "b"]}]}

        _remove_array_element(data, "servers[0].tags", 0)

        assert data == {"servers": [{"tags": ["b"]}]}

    def test_remove_from_non_list_is_a_no_op(self):
        data = {"server": {"port": 8080}}

        _remove_array_element(data, "server.port", 0)

        assert data == {"server": {"port": 8080}}


class TestFindField:
    def test_finds_root_array_field(self, app):
        data = app.config["CONFIG_DATA"]
        tree = FormGenerator().generate(data, app.config["SCHEMA"])

        field = _find_field(tree, "features.names")

        assert field is not None
        assert field.field_type == "array"
        assert field.path == "features.names"

    def test_finds_child_of_array_item(self, app):
        data = app.config["CONFIG_DATA"]
        tree = FormGenerator().generate(data, app.config["SCHEMA"])

        field = _find_field(tree, "servers[1].host")

        assert field is not None
        assert field.value == "10.0.0.2"

    def test_returns_none_for_missing_path(self, app):
        data = app.config["CONFIG_DATA"]
        tree = FormGenerator().generate(data, app.config["SCHEMA"])

        assert _find_field(tree, "features.missing") is None
