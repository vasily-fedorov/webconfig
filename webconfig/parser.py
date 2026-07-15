"""Config file parser and serializer for TOML, JSON, and ENV formats.

Pure functions — no file I/O. Callers handle reading and writing files.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigParseError(Exception):
    """Raised when a config file cannot be parsed."""


@dataclass
class ConfigFile:
    """Parsed configuration file with metadata."""

    path: str
    format: str  # "toml" | "json" | "env"
    data: dict


class ConfigParser:
    """Parse and serialize configuration files.

    Uses stdlib only — no external dependencies.
    """

    @staticmethod
    def parse(text: str, path: str) -> ConfigFile:
        """Parse config text into a ConfigFile.

        Args:
            text: Already-read file content (caller handles file I/O).
            path: File path used to determine format from extension.

        Returns:
            ConfigFile with parsed data.

        Raises:
            ConfigParseError: If parsing fails.
        """
        fmt = _format_from_path(path)
        try:
            if fmt == "toml":
                data = tomllib.loads(text)
            elif fmt == "json":
                data = json.loads(text)
            elif fmt == "env":
                data = _parse_env(text)
            else:
                raise ConfigParseError(f"Unsupported format: {fmt}")
        except ConfigParseError:
            raise
        except (tomllib.TOMLDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ConfigParseError(
                f"Failed to parse {fmt}: {exc}"
            ) from exc

        # Normalize: ensure top-level is always a dict
        if not isinstance(data, dict):
            raise ConfigParseError(
                f"Failed to parse {fmt}: top-level value must be a dict, got {type(data).__name__}"
            )

        return ConfigFile(path=path, format=fmt, data=data)

    @staticmethod
    def serialize(data: dict, path: str) -> str:
        """Serialize a dict back to config text.

        Args:
            data: Configuration dictionary to serialize.
            path: File path used to determine target format from extension.

        Returns:
            Serialized string ready for writing to disk.

        Raises:
            ConfigParseError: If serialization fails.
        """
        fmt = _format_from_path(path)
        try:
            if fmt == "toml":
                return _serialize_toml(data)
            elif fmt == "json":
                return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            elif fmt == "env":
                return _serialize_env(data)
            else:
                raise ConfigParseError(f"Unsupported format: {fmt}")
        except ConfigParseError:
            raise
        except (TypeError, ValueError) as exc:
            raise ConfigParseError(
                f"Failed to serialize to {fmt}: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_from_path(path: str) -> str:
    """Determine format from file extension."""
    p = Path(path)
    suffix = p.suffix.lower()
    name = p.name.lower()
    # Handle dotfiles like .env where suffix is empty
    if name == ".env" or suffix == ".env":
        return "env"
    if suffix == ".toml":
        return "toml"
    elif suffix == ".json":
        return "json"
    raise ConfigParseError(
        f"Unsupported file extension: {suffix or name}. "
        "Use .toml, .json, or .env"
    )


# ── ENV parser ───────────────────────────────────────────────────────────────


def _parse_env(text: str) -> dict[str, str]:
    """Parse a .env-style flat key=value file.

    - Lines starting with ``#`` are comments.
    - Blank lines are skipped.
    - No quoting, no nesting — all values are strings.
    """
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        result[key] = value
    return result


# ── ENV serializer ───────────────────────────────────────────────────────────


def _serialize_env(data: dict, prefix: str = "") -> str:
    """Serialize dict to ENV format. Flattens nested structures with dotted keys."""
    lines: list[str] = []
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            lines.append(_serialize_env(value, full_key))
        elif isinstance(value, list):
            lines.append(f'{full_key}={",".join(_env_str(v) for v in value)}')
        elif value is not None:
            lines.append(f"{full_key}={value}")
        # None values are skipped
    return "\n".join(lines)


def _env_str(value: object) -> str:
    """Convert any scalar to a string for ENV output."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ── TOML serializer ──────────────────────────────────────────────────────────


def _serialize_toml(data: dict) -> str:
    """Serialize dict to TOML text using a custom writer (no external deps).

    Handles:
      - Top-level scalars: ``key = value``
      - Nested dicts: ``[section]`` / ``[parent.child]`` headers
      - Arrays of scalars: ``key = [1, 2, 3]``
      - Arrays of tables: ``[[items]]`` syntax for lists of dicts
      - Booleans: lowercase ``true`` / ``false``
      - Strings: double-quoted with escaping
      - None: silently skipped
    """
    lines: list[str] = []
    _write_toml_table(lines, data, "")
    return "\n".join(lines) + "\n"


def _write_toml_table(lines: list[str], data: dict, prefix: str) -> None:
    """Recursively write a TOML table (or array of tables)."""
    if not isinstance(data, dict):
        return

    # Separate keys by type
    scalars: dict[str, object] = {}
    nested: dict[str, dict] = {}
    arrays: dict[str, list] = {}
    array_tables: dict[str, list[dict]] = {}

    for key, value in data.items():
        if isinstance(value, dict):
            nested[key] = value
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            array_tables[key] = value
        elif isinstance(value, list):
            arrays[key] = value
        elif value is not None:
            scalars[key] = value
        # None values are silently skipped

    # Prepend a blank line before sections (not before the first top-level block)
    if prefix and lines:
        lines.append("")

    # Write section header
    if prefix:
        lines.append(f"[{prefix}]")

    # Write simple scalars
    for key, value in scalars.items():
        lines.append(f"{key} = {_toml_value(value)}")

    # Write inline arrays
    for key, value in arrays.items():
        lines.append(f"{key} = {_toml_value(value)}")

    # Write nested tables
    for key, value in nested.items():
        full_key = f"{prefix}.{key}" if prefix else key
        _write_toml_table(lines, value, full_key)

    # Write arrays of tables
    for key, items in array_tables.items():
        full_key = f"{prefix}.{key}" if prefix else key
        for item in items:
            if lines:
                lines.append("")
            lines.append(f"[[{full_key}]]")
            _write_toml_inline_table(lines, item)


def _write_toml_inline_table(lines: list[str], data: dict) -> None:
    """Write key-value pairs inside a ``[[table]]`` block (no recursive headers)."""
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, dict):
            # Nested dict inside array of tables — use dotted prefix for sub-table
            continue  # not handled yet; skip silently per spec
        elif isinstance(value, list):
            lines.append(f"{key} = {_toml_value(value)}")
        else:
            lines.append(f"{key} = {_toml_value(value)}")


def _toml_value(value: object) -> str:
    """Format a single TOML value (bool, str, int, float, list, None)."""
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        items = [
            _toml_value(v)
            for v in value
            if v is not None
        ]
        return f'[{", ".join(items)}]'
    return str(value)
