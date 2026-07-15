"""CLI argument parsing and main entry point."""

import argparse
import sys
import webbrowser
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="webconfig",
        description="Edit config files (TOML/JSON/ENV) via Web UI",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to config file (.toml, .json, .env)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Server port (default: 8080)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Path to JSON Schema file",
    )
    parser.add_argument(
        "--preset",
        choices=["light", "dark", "auto"],
        default="auto",
        help="Color preset (default: auto = system preference)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    args = parse_args(argv)

    # Validate config file exists
    if not args.config.exists():
        print(f"Error: file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    # Validate extension
    suffix = args.config.suffix.lower()
    if suffix not in (".toml", ".json", ".env"):
        print(
            f"Error: unsupported format '{suffix}'. Use .toml, .json, or .env",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load and validate schema if provided
    schema = None
    if args.schema:
        if not args.schema.exists():
            print(f"Error: schema file not found: {args.schema}", file=sys.stderr)
            sys.exit(1)
        import json

        try:
            schema = json.loads(args.schema.read_text())
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON Schema: {e}", file=sys.stderr)
            sys.exit(1)

    # Import and start server
    from webconfig.server import create_app

    app = create_app(
        config_path=str(args.config),
        schema=schema,
        preset=args.preset,
    )

    url = f"http://{args.host}:{args.port}"
    print(f" * Server starting at {url}")
    print(f" * Editing: {args.config}")
    if schema:
        print(f" * Schema:   {args.schema}")
    print(" * Press Ctrl+C to stop")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        app.run(host=args.host, port=args.port, debug=False)
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"  Port {args.port} may already be in use.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n * Server stopped.")
