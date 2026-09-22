"""Entry point: python -m rackmon [--config PATH] [--mock] [--port N]"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .config import load_config

DEFAULT_CONFIG_PATHS = [Path("config/config.yaml"), Path("config.yaml")]


def find_config_path(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    for candidate in DEFAULT_CONFIG_PATHS:
        if candidate.exists():
            return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rackmon",
        description="Livestream rack monitoring dashboards "
                    "(screen1=health, screen2=multiview, screen3=stream/checklist)")
    parser.add_argument("--config", help="path to config.yaml "
                        "(default: config/config.yaml or config.yaml)")
    parser.add_argument("--mock", action="store_true",
                        help="run with fake hardware — full demo, no gear needed")
    parser.add_argument("--host", default=None, help="override server host")
    parser.add_argument("--port", type=int, default=None, help="override server port")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    path = find_config_path(args.config)
    config, error = load_config(path, mock_override=True if args.mock else None)
    if error:
        print(f"rackmon: {error}", file=sys.stderr)
        if path is None and not args.mock:
            sys.exit(2)  # nothing to serve, not even an error page
        print("rackmon: starting anyway so the kiosks can display the problem",
              file=sys.stderr)

    host = args.host or (config.server.host if config else "127.0.0.1")
    port = args.port or (config.server.port if config else 8080)

    app = create_app(config, config_error=error)
    print(f"rackmon: dashboards at http://{host}:{port}/screen1 /screen2 /screen3")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
