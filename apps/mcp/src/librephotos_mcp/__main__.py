"""CLI entry point. Only the MCP SDK writes protocol output to stdout."""

import argparse
import logging
import sys
from urllib.parse import urlsplit

from mcp.server.transport_security import TransportSecuritySettings

from librephotos_mcp.config import Config
from librephotos_mcp.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="LibrePhotos MCP adapter")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    # Avoid verbose SDK and HTTP request logs, including upstream URLs.
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpx2").setLevel(logging.CRITICAL)
    try:
        config = Config.from_environment(args.transport)
        server = create_server(config)
    except (ValueError, OSError):
        parser.exit(
            2,
            "Invalid MCP configuration. Check the service URL, credentials file, and OAuth settings.\n",
        )
    if args.transport == "stdio":
        server.run("stdio")
    else:
        resource = urlsplit(config.resource_url)
        allowed = [resource.netloc]
        if resource.port is None:
            allowed.append(f"{resource.hostname}:*")
        server.run(
            "streamable-http",
            host=args.host,
            port=args.port,
            stateless_http=True,
            transport_security=TransportSecuritySettings(
                allowed_hosts=allowed, allowed_origins=[f"{resource.scheme}://{resource.netloc}"]
            ),
        )


if __name__ == "__main__":
    main()
