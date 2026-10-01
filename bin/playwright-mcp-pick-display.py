#!/usr/bin/env python3
"""Choose the X display for the shared headed (stealth) Playwright MCP server,
then exec it.

ExecStart= wrapper for playwright-stealth-mcp.service. Prefers the Chrome
Remote Desktop display (:20) so a human connected over CRD can watch / help
debug the browser; falls back to the TigerVNC display (:99) when :20 is
already being used by ANOTHER Claude session, or when the :20 X server isn't
up. A human being connected over CRD is deliberately NOT a reason to fall back.

"Used by another Claude session" means: some process that is an actual X
client of :20 (it holds a unix-socket connection to the :20 X server, found by
pairing `ss -xp` endpoints) and is descended from a `claude` process -- e.g. a
leftover per-session stdio playwright-mcp's Chrome. Merely having DISPLAY=:20
in the environment does NOT count: the systemd user manager exports
DISPLAY=:20 (CRD imports it), so every Claude session can inherit it.

Two modes, because the decision cannot be made inside the unit's sandbox:
with a private mount namespace (ProtectSystem=/ProtectHome=/PrivateTmp=) a
user-manager service lives in its own user namespace, and the kernel then
refuses it /proc/PID/fd and /proc/PID/environ of every other process (so
`ss -p` shows no owners either). The unit therefore runs
  ExecStartPre=+... --write FILE    (unsandboxed: decide, write ":20"/":99")
  ExecStart=...     --exec FILE PROGRAM [ARGS...]   (sandboxed: set DISPLAY, exec)

The choice is made once per start: Chrome inherits DISPLAY from the server
when it is (lazily) launched. Every open Claude session holds an MCP GET
stream, so the unit rarely idles out -- a start that fell back to :99 can stay
there until `systemctl --user stop playwright-stealth-mcp.service`.
usage: playwright-mcp-pick-display.py --write FILE
       playwright-mcp-pick-display.py --exec FILE PROGRAM [ARGS...]
"""

import os
import re
import socket
import subprocess
import sys

PREFERRED = os.environ.get("PW_PREFERRED_DISPLAY", ":20")
FALLBACK = os.environ.get("PW_FALLBACK_DISPLAY", ":99")


def log(msg):
    print(f"pick-display: {msg}", file=sys.stderr, flush=True)


def x_socket_path(display):
    return f"/tmp/.X11-unix/X{display.lstrip(':').split('.')[0]}"


def x_server_up(display):
    """True if the X server for `display` accepts a connection."""
    path = x_socket_path(display)
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


def x_client_pids(display):
    """Pids holding a unix-socket connection to `display`'s X server.

    `ss -xpn` lists both ends of each connection: the server end has the
    socket path as its local address and the client's inode as its peer; the
    client end has that inode as its local port and names its process(es).
    """
    res = subprocess.run(["ss", "-xpnH"], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        log(f"ss -xpnH failed ({res.returncode}): {res.stderr.strip()}")
        return None
    path = x_socket_path(display)
    rows = [line.split(maxsplit=8) for line in res.stdout.splitlines()]
    rows = [r for r in rows if len(r) >= 8]
    # fields: netid state recv-q send-q local-addr local-port peer-addr peer-port [users]
    server_peers = {r[7] for r in rows if r[4] in (path, "@" + path)}
    pids = set()
    for r in rows:
        if r[5] in server_peers and len(r) == 9:
            pids.update(int(p) for p in re.findall(r"pid=(\d+)", r[8]))
    return pids


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
    """The nearest `claude` STRICT ancestor of pid (pid itself never counts)."""
    seen = set()
    pid = ppid_of(pid)
    while pid and pid > 1 and pid not in seen:
        seen.add(pid)
        if is_claude(pid):
            return pid
        pid = ppid_of(pid)
    return None


def claude_users_of(display):
    """[(pid, claude_pid, cmdline)] of claude-descended X clients of display,
    or None if they could not be determined."""
    pids = x_client_pids(display)
    if pids is None:
        return None
    users = []
    for pid in sorted(pids):
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
    if users is None:
        log(f"cannot list {PREFERRED} X clients; assuming free -> {PREFERRED}")
        return PREFERRED
    if users:
        for pid, owner, cmd in users:
            log(f"{PREFERRED} in use by claude pid {owner}: pid {pid} {cmd}")
        log(f"-> {FALLBACK}")
        return FALLBACK
    log(f"{PREFERRED} free -> {PREFERRED}")
    return PREFERRED


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--write":
        with open(args[1], "w") as f:
            f.write(choose() + "\n")
    elif len(args) >= 3 and args[0] == "--exec":
        with open(args[1]) as f:
            display = f.read().strip()
        if not display.startswith(":"):
            sys.exit(f"pick-display: bad display {display!r} in {args[1]}")
        log(f"DISPLAY={display}")
        os.environ["DISPLAY"] = display
        os.execv(args[2], args[2:])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
