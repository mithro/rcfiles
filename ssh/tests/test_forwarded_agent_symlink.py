#!/usr/bin/env python3
"""Tests for the forwarded-agent symlink logic in tmux/zprofile.

The symlink ~/.ssh/forwarded-agent.sock is one of two ssh-agent-mux backends
(ssh/ssh-agent-mux.toml). Every login runs tmux/zprofile, which decides whether
to repoint it at that login's own SSH-forwarded agent socket.

The policy under test is "last login WITH A WORKING FORWARD wins": a login that
has no working forwarded agent of its own must not disturb a symlink that
already points at another session's live forwarded agent.

That case is not hypothetical. A mosh login *always* hits it: `mosh` runs
`ssh <host> mosh-server new ...`, mosh-server daemonises, and the launcher ssh
exits immediately -- at which point sshd unlinks the forwarded agent socket it
created. The orphaned mosh-server still carries the now-dead path in its
environment and passes it to the login shell, so zprofile sees a non-empty
SSH_AUTH_SOCK naming a socket that no longer exists.

These tests run the real, unmodified tmux/zprofile against a sandbox $HOME with
PATH stubs for tmux and systemctl, then assert on the resulting symlink.
"""

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ZPROFILE = REPO_ROOT / "tmux" / "zprofile"
# Sandboxes go in the repo-local, gitignored tmp/ rather than /tmp.
SCRATCH = REPO_ROOT / "tmp"

STUB = "#!/bin/sh\nexit 0\n"


def make_socket(path: Path) -> Path:
    """Create a real AF_UNIX socket file at path.

    zprofile tests these with `[ -S ... ]`, which checks the file *type* only,
    so a bound-then-closed socket is indistinguishable from a live agent.

    AF_UNIX addresses are capped at ~108 bytes, which the repo-local sandbox
    paths exceed, so bind to the bare filename from inside the parent
    directory and restore the cwd afterwards.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    cwd = Path.cwd()
    try:
        os.chdir(path.parent)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(path.name)
        sock.close()
    finally:
        os.chdir(cwd)
    return path


def make_sandbox(tmp: Path) -> Path:
    """Build a sandbox $HOME resembling a host with the agent setup deployed."""
    home = tmp / "home"
    agent = home / ".ssh" / "agent"
    agent.mkdir(parents=True)

    # Local ssh-agent, reached through the per-PID indirection setup.sh uses.
    make_socket(agent / "local.4242.sock")
    (agent / "local.sock").symlink_to(agent / "local.4242.sock")

    # Pre-create the mux socket so zprofile's wait loop returns immediately.
    make_socket(agent / "mux.sock")

    binhome = tmp / "bin"
    binhome.mkdir()
    for stub in ("tmux", "systemctl"):
        p = binhome / stub
        p.write_text(STUB)
        p.chmod(0o755)

    return home


def run_zprofile(
    home: Path, binhome: Path, auth_sock: str
) -> subprocess.CompletedProcess:
    """Run the real zprofile as a login would, with SSH_AUTH_SOCK inherited."""
    env = {
        "HOME": str(home),
        "PATH": f"{binhome}:{os.environ['PATH']}",
        "TERM": "xterm-256color",
        "SSH_CONNECTION": "10.1.20.51 49016 10.1.10.1 22",
        "SSH_AUTH_SOCK": auth_sock,
    }
    return subprocess.run(
        ["zsh", str(ZPROFILE)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def check(name: str, home: Path, expected: Path) -> bool:
    """Assert forwarded-agent.sock resolves to expected; report pass/fail."""
    link = home / ".ssh" / "forwarded-agent.sock"
    actual = os.readlink(link) if link.is_symlink() else "<no symlink>"
    if str(actual) == str(expected):
        print(f"PASS  {name}")
        return True
    print(f"FAIL  {name}")
    print(f"        expected: {expected}")
    print(f"        actual:   {actual}")
    return False


def scenario(fn):
    """Run one scenario in a fresh sandbox; returns True if it passed."""
    SCRATCH.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
        tmp = Path(td)
        home = make_sandbox(tmp)
        return fn(home, tmp / "bin")


def test_mosh_login_does_not_clobber_live_forward(home, binhome):
    """A mosh login (dead SSH_AUTH_SOCK) must leave a live forward alone.

    This is the reported bug: the ssh session owning socket A is still up, but
    connecting a new mosh session repointed the symlink at the local agent,
    so the mux stopped serving the laptop's forwarded keys.
    """
    agent = home / ".ssh" / "agent"
    live = make_socket(agent / "s.HOSTKEY.sshd.LIVE")
    (home / ".ssh" / "forwarded-agent.sock").symlink_to(live)

    dead = agent / "s.HOSTKEY.sshd.DEAD"  # never created: sshd already unlinked it
    run_zprofile(home, binhome, str(dead))

    return check("mosh login does not clobber a live forward", home, live)


def test_no_agent_login_does_not_clobber_live_forward(home, binhome):
    """An `ssh` without -A (empty SSH_AUTH_SOCK) must also leave it alone."""
    agent = home / ".ssh" / "agent"
    live = make_socket(agent / "s.HOSTKEY.sshd.LIVE")
    (home / ".ssh" / "forwarded-agent.sock").symlink_to(live)

    run_zprofile(home, binhome, "")

    return check("no-agent login does not clobber a live forward", home, live)


def test_working_forward_wins(home, binhome):
    """A login WITH a working forward takes over -- last working forward wins."""
    agent = home / ".ssh" / "agent"
    old = make_socket(agent / "s.HOSTKEY.sshd.OLD")
    (home / ".ssh" / "forwarded-agent.sock").symlink_to(old)

    new = make_socket(agent / "s.HOSTKEY.sshd.NEW")
    run_zprofile(home, binhome, str(new))

    return check("login with a working forward takes over", home, new)


def test_dangling_symlink_repaired_to_local(home, binhome):
    """A dangling symlink is repaired to the local agent.

    Replacing a broken pointer is not overwriting a working forward, and it
    preserves the original intent: keep ssh-agent-mux from logging
    'Ignoring missing upstream agent socket' on every request.
    """
    agent = home / ".ssh" / "agent"
    (home / ".ssh" / "forwarded-agent.sock").symlink_to(agent / "s.HOSTKEY.sshd.GONE")

    run_zprofile(home, binhome, "")

    return check("dangling symlink repaired to local agent", home, agent / "local.sock")


def test_missing_symlink_created_pointing_at_local(home, binhome):
    """First login ever: no symlink at all, so create one at the local agent."""
    agent = home / ".ssh" / "agent"

    run_zprofile(home, binhome, "")

    return check("missing symlink created at local agent", home, agent / "local.sock")


def test_mux_sock_forward_is_ignored(home, binhome):
    """SSH_AUTH_SOCK already pointing at the mux must not create a loop."""
    agent = home / ".ssh" / "agent"
    live = make_socket(agent / "s.HOSTKEY.sshd.LIVE")
    (home / ".ssh" / "forwarded-agent.sock").symlink_to(live)

    run_zprofile(home, binhome, str(agent / "mux.sock"))

    return check("mux.sock as forward is ignored", home, live)


TESTS = [
    test_mosh_login_does_not_clobber_live_forward,
    test_no_agent_login_does_not_clobber_live_forward,
    test_working_forward_wins,
    test_dangling_symlink_repaired_to_local,
    test_missing_symlink_created_pointing_at_local,
    test_mux_sock_forward_is_ignored,
]


def main() -> int:
    if not ZPROFILE.is_file():
        print(f"zprofile not found at {ZPROFILE}", file=sys.stderr)
        return 2

    results = [scenario(t) for t in TESTS]
    passed, total = sum(results), len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
