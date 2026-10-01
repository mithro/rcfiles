#!/usr/bin/env python3
"""Back up this machine's Claude Code session storage to big-storage.

Copies, without ever deleting on the destination:
  ~/.claude/projects/                       transcripts + per-project memory
  ~/.claude/history.jsonl                   prompt history
  ~/.claude/todos/                          per-session todo state
  ~/.config/superpowers/conversation-archive/   episodic-memory plugin archive

Destination: /backups/machines/<this-machine>/claude-sessions/ on
big-storage.welland.mithis.com. On big-storage itself this is a local copy;
everywhere else it is rsync over ssh using the dedicated key
~/.ssh/keys/claude-sessions-backup, which big-storage's authorized_keys pins
with rrsync to that one directory (so a leaked key can only touch its own
machine's backup). Run hourly by claude-sessions-backup.timer.

Why no --delete: Claude Code's cleanupPeriodDays sweep deletes local
transcripts; the whole point of this backup is that those deletions do NOT
propagate. Transcripts are append-only, so a plain mirror is enough.
"""

import datetime
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile

BACKUP_HOST = "big-storage.welland.mithis.com"
BACKUP_ROOT = pathlib.Path("/backups/machines")
KEY = pathlib.Path.home() / ".ssh" / "keys" / "claude-sessions-backup"

# Machines whose kernel hostname is not the name used under /backups/machines.
LABELS = {
    "x1c-work": "x1c-work.welland.mithis.com",
    "desktop": "desktop.buddy.mithis.com",
    "big-storage": "big-storage.welland.mithis.com",
}

# (source, name under claude-sessions/). Trailing slash = directory contents.
SOURCES = [
    ("~/.claude/projects/", "projects/"),
    ("~/.claude/history.jsonl", "history.jsonl"),
    ("~/.claude/todos/", "todos/"),
    ("~/.config/superpowers/conversation-archive/", "conversation-archive/"),
]

RSYNC_OPTS = [
    "-a",
    "--partial",
    "--timeout=900",
    "--exclude=*.tmp",
    "--exclude=*.lock",
    "--stats",
]
# -F /dev/null: ignore ~/.ssh/config so no other IdentityFile (some hosts keep
# an unencrypted, unrestricted key there) can be offered instead of KEY, and
# no ControlMaster socket from an interactive login can be reused, which would
# silently bypass the rrsync restriction. Host keys come from the per-host file
# the shared ssh config already uses for big-storage (rsync splits -e on
# spaces, so only one file can be named here).
SSH = (
    f"ssh -F /dev/null -i {KEY} -o IdentitiesOnly=yes -o BatchMode=yes"
    " -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=20"
    " -o UserKnownHostsFile=~/.ssh/known_hosts.big-storage"
)


def machine_label() -> str:
    # Kernel hostname first: the ten64s are configured with their FQDN, and
    # socket.getfqdn() can come back short when DNS has no reverse entry.
    host = socket.gethostname()
    if "." in host:
        return host
    if host in LABELS:
        return LABELS[host]
    fqdn = socket.getfqdn()
    return fqdn if "." in fqdn else host


def main() -> int:
    label = machine_label()
    local = socket.gethostname().split(".")[0] == "big-storage"
    if local:
        dest_root = BACKUP_ROOT / label / "claude-sessions"
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = lambda name: str(dest_root / name)  # noqa: E731
        rsync_base = ["rsync", *RSYNC_OPTS]
    else:
        if not KEY.exists():
            print(
                f"missing ssh key {KEY}; generate it and authorize it on {BACKUP_HOST}",
                file=sys.stderr,
            )
            return 2
        # rrsync on the server makes paths relative to this machine's claude-sessions dir.
        dest = lambda name: f"tim@{BACKUP_HOST}:{name}"  # noqa: E731
        rsync_base = ["rsync", *RSYNC_OPTS, "-e", SSH]

    print(
        f"claude-sessions-backup: {label} -> {'local ' + str(dest_root) if local else BACKUP_HOST}"
    )
    failures = 0
    for src, name in SOURCES:
        src_path = pathlib.Path(os.path.expanduser(src))
        if not src_path.exists():
            print(f"  skip {src}: not present")
            continue
        cmd = [*rsync_base, str(src_path), dest(name)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        stats = {
            ln.split(":")[0].strip(): ln.split(":", 1)[1].strip()
            for ln in r.stdout.splitlines()
            if ":" in ln
        }
        if r.returncode == 0:
            print(
                f"  ok   {src}: {stats.get('Number of regular files transferred', '?')} files sent, "
                f"{stats.get('Total transferred file size', '?')} ({stats.get('Number of files', '?')} total)"
            )
        else:
            failures += 1
            print(
                f"  FAIL {src}: rsync exit {r.returncode}\n{r.stderr.strip()[:1000]}",
                file=sys.stderr,
            )

    # Timestamp marker so the destination shows when the last full run finished.
    stamp = (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        + "\n"
    )
    if local:
        (dest_root / ".last-backup").write_text(stamp)
    else:
        with tempfile.TemporaryDirectory() as td:
            marker = pathlib.Path(td) / ".last-backup"
            marker.write_text(stamp)
            r = subprocess.run(
                [*rsync_base, str(marker), dest(".last-backup")],
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                failures += 1
                print(f"  FAIL marker: {r.stderr.strip()[:500]}", file=sys.stderr)
    print(f"  done at {stamp.strip()} with {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    if shutil.which("rsync") is None:
        print("rsync not installed", file=sys.stderr)
        sys.exit(2)
    sys.exit(main())
