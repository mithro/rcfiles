#!/usr/bin/env python3
"""Choose the X display for the shared headed (stealth) Playwright MCP server,
then exec it.

ExecStart= wrapper for playwright-stealth-mcp.service. Prefers the Chrome
Remote Desktop display (:20) so a human connected over CRD can watch / help
debug the browser; falls back to the TigerVNC display (:99) when :20 is
already being used by ANOTHER Claude session (some process descended from a
`claude` process with DISPLAY=:20 -- e.g. a leftover per-session stdio
playwright-mcp), or when the :20 X server isn't up. A human being connected
over CRD is deliberately NOT a reason to fall back.

The choice is made once per on-demand start: Chrome inherits DISPLAY from this
process when it is (lazily) launched, and the unit idles out and restarts.
usage: pick-display.py PROGRAM [ARGS...]
"""

import os
import socket
import sys

PREFERRED = os.environ.get("PW_PREFERRED_DISPLAY", ":20")
FALLBACK = os.environ.get("PW_FALLBACK_DISPLAY", ":99")


def log(msg):
    print(f"pick-display: {msg}", file=sys.stderr, flush=True)


def x_server_up(display):
    """True if the X server for `display` accepts a connection."""
    num = display.lstrip(":").split(".")[0]
    path = f"/tmp/.X11-unix/X{num}"
    for addr in (path, "\0" + path):  # filesystem socket, then abstract
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.settimeout(2)
            s.connect(addr)
            return True
        except OSError as e:
            log(f"{display}: connect {addr!r} failed: {e}")
        finally:
            s.close()
    return False


def read_proc(pid, name):
    try:
        with open(f"/proc/{pid}/{name}", "rb") as f:
            return f.read()
    except OSError:  # raced with exit, or not ours
        return None


def ppid_of(pid):
    stat = read_proc(pid, "stat")
    if stat is None:
        return None
    # comm may contain spaces/parens: fields resume after the LAST ')'
    return int(stat[stat.rindex(b")") + 2 :].split()[1])


def is_claude(pid):
    comm = read_proc(pid, "comm")
    return comm is not None and comm.strip() == b"claude"


def claude_ancestor(pid):
    seen = set()
    while pid and pid > 1 and pid not in seen:
        seen.add(pid)
        if is_claude(pid):
            return pid
        pid = ppid_of(pid)
    return None


def claude_users_of(display):
    """[(pid, claude_pid, cmdline)] of claude-descended processes on display."""
    want = b"DISPLAY=" + display.encode()
    users = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        env = read_proc(pid, "environ")
        if env is None or want not in env.split(b"\0"):
            continue
        owner = claude_ancestor(pid)
        if owner is not None:
            cmd = (read_proc(pid, "cmdline") or b"").replace(b"\0", b" ")
            users.append((pid, owner, cmd.decode(errors="replace")[:120]))
    return users


def choose():
    if not x_server_up(PREFERRED):
        log(f"{PREFERRED} X server not reachable -> {FALLBACK}")
        return FALLBACK
    users = claude_users_of(PREFERRED)
    if users:
        for pid, owner, cmd in users:
            log(f"{PREFERRED} in use by claude pid {owner}: pid {pid} {cmd}")
        log(f"-> {FALLBACK}")
        return FALLBACK
    log(f"{PREFERRED} free -> {PREFERRED}")
    return PREFERRED


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    os.environ["DISPLAY"] = choose()
    os.execv(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
