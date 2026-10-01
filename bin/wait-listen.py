#!/usr/bin/env python3
"""Block until HOST:PORT accepts a TCP connection (or fail after a deadline).

ExecStartPost= helper for the socket-activated MCP server units
(systemd/user/playwright-mcp.service, ngsw-mcp.service). systemd's After= only
orders on "started", and these servers do not sd_notify, so without this the
proxy's first forwarded connection could race the bind and be refused.

usage: wait-listen.py HOST PORT SECONDS
"""

import socket
import sys
import time


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit("usage: wait-listen.py HOST PORT SECONDS")
    host, port, secs = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
    deadline = time.monotonic() + secs
    while True:
        try:
            socket.create_connection((host, port), timeout=1).close()
            return
        except OSError:
            if time.monotonic() > deadline:
                sys.exit(f"{host}:{port} did not accept a connection within {secs:g}s")
            time.sleep(0.2)


if __name__ == "__main__":
    main()
