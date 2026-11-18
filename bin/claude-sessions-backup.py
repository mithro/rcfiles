#!/usr/bin/env python3
"""Back up this machine's Claude Code session storage to big-storage.

Copies, without ever deleting on the destination:
  ~/.claude/projects/                       transcripts + per-project memory
  ~/.claude/history.jsonl                   prompt history
  ~/.claude/todos/                          per-session todo state
  ~/.config/superpowers/conversation-archive/   episodic-memory plugin archive

Destination: /backups/machines/<this-machine>/claude-sessions/ on
big-storage.welland.mithis.com, holding projects/, history.jsonl, todos/,
conversation-archive/ and .last-backup directly. On big-storage itself this is
a local copy; everywhere else it is rsync over ssh using the dedicated key
~/.ssh/keys/claude-sessions-backup, which big-storage's authorized_keys pins
with rrsync to that one directory (so a leaked key can only touch its own
machine's backup). Run hourly by claude-sessions-backup.timer.

Why no --delete: Claude Code's cleanupPeriodDays sweep deletes local
transcripts; the whole point of this backup is that those deletions do NOT
propagate. Transcripts are append-only, so a plain mirror is enough.

Staleness: every run rewrites ~/.local/state/claude-sessions-backup/warning,
which bash/include/claude-sessions-backup prints at shell start. It is empty
while backups are fresh; it names this machine when its last full success is
older than STALE_AFTER, and on big-storage it also names every other machine
whose .last-backup is that old. (From 2026-09-30 to 2026-11-18 every machine
failed hourly and only the journal knew.)
"""

import datetime
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time

BACKUP_HOST = "big-storage.welland.mithis.com"
BACKUP_ROOT = pathlib.Path("/backups/machines")
KEY = pathlib.Path.home() / ".ssh" / "keys" / "claude-sessions-backup"
STATE_DIR = (
    pathlib.Path(
        os.environ.get("XDG_STATE_HOME") or pathlib.Path.home() / ".local" / "state"
    )
    / "claude-sessions-backup"
)
STALE_AFTER = datetime.timedelta(hours=48)

# Machines whose kernel hostname is not the name used under /backups/machines.
LABELS = {
    "x1c-work": "x1c-work.welland.mithis.com",
    "desktop": "desktop.buddy.mithis.com",
    "big-storage": "big-storage.welland.mithis.com",
}

# (source, name under claude-sessions/). Whether a source is a directory or a
# file is decided when it is looked at; see plan_jobs() for how each is sent.
SOURCES = [
    ("~/.claude/projects", "projects"),
    ("~/.claude/history.jsonl", "history.jsonl"),
    ("~/.claude/todos", "todos"),
    ("~/.config/superpowers/conversation-archive", "conversation-archive"),
]

RSYNC_OPTS = [
    "-a",
    "--partial",
    "--timeout=900",
    "--exclude=*.tmp",
    "--exclude=*.lock",
    "--stats",
]
# 24 = "some source files vanished": normal while sessions are being written.
RSYNC_OK = (0, 24)
# -F /dev/null: ignore ~/.ssh/config so no other IdentityFile (some hosts keep
# an unencrypted, unrestricted key there) can be offered instead of KEY, and
# no ControlMaster socket from an interactive login can be reused, which would
# silently bypass the rrsync restriction. (desktop did exactly that with the
# pre-isolation script: its backups landed in ~tim on big-storage for weeks.)
# Host keys come from the per-host file the shared ssh config already uses for
# big-storage (rsync splits -e on spaces, so only one file can be named here).
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


def rsync_escape(name: str) -> str:
    """Escape a literal file name for use in an rsync filter pattern."""
    return "".join("\\" + c if c in "*?[\\" else c for c in name)


def plan_jobs(sources, dest_prefix: str):
    """Turn SOURCES into rsync jobs: (label, extra_opts, rsync_src, rsync_dest).

    Arguments are built as strings on purpose. rsync gives a trailing slash on
    the source meaning ("the contents of"), and pathlib drops it: the first
    version of this script passed str(Path("~/.claude/projects/")) and so
    copied the directory *into* projects/, leaving projects/projects/ on the
    server.

    A file is sent into the destination directory under its own name, never to
    a named destination: since rsync 3.5.0 rrsync rewrites an existing
    regular-file destination to /proc/self/fd/N, and rsync then fails with
    "delete_file: unlink(N) failed: Operation not permitted" trying to replace
    that magic link.

    A top-level entry of a source directory that is a symlink to a directory
    (desktop keeps some projects in a second config dir and links them into
    ~/.claude/projects) is excluded from the main transfer and sent from its
    resolved path instead. `rsync -a` would copy the link, not the sessions,
    and rrsync refuses the -L/-k options that would follow it.
    """
    jobs = []
    for src, name in sources:
        path = os.path.expanduser(src)
        if not os.path.exists(path):
            jobs.append((src, None, None, None))
            continue
        if not os.path.isdir(path):
            jobs.append((src, [], path, f"{dest_prefix}./"))
            continue
        real = os.path.realpath(path)
        linked = sorted(
            e.name
            for e in os.scandir(real)
            if e.is_symlink() and e.is_dir(follow_symlinks=True)
        )
        excludes = [f"--exclude=/{rsync_escape(n)}" for n in linked]
        jobs.append((f"{src}/", excludes, f"{real}/", f"{dest_prefix}{name}/"))
        for n in linked:
            target = os.path.realpath(os.path.join(real, n))
            jobs.append(
                (
                    f"{src}/{n}/ -> {target}/",
                    [],
                    f"{target}/",
                    f"{dest_prefix}{name}/{n}/",
                )
            )
    return jobs


def parse_stamp(text: str):
    try:
        return datetime.datetime.strptime(text.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.UTC
        )
    except ValueError:
        return None


def describe_age(age: datetime.timedelta) -> str:
    hours = int(age.total_seconds() // 3600)
    return f"{hours // 24} days" if hours >= 48 else f"{hours} hours"


def stale_machines(root: pathlib.Path, now: datetime.datetime, skip: str):
    """Warnings for every machine under root whose .last-backup is too old."""
    out = []
    for marker in sorted(root.glob("*/claude-sessions/.last-backup")):
        machine = marker.parent.parent.name
        if machine == skip:
            continue
        try:
            stamp = parse_stamp(marker.read_text())
        except OSError:
            stamp = None
        if stamp is None:
            out.append(f"{machine}: unreadable .last-backup")
        elif now - stamp > STALE_AFTER:
            out.append(
                f"{machine}: last backup {stamp:%Y-%m-%d %H:%M}Z ({describe_age(now - stamp)} ago)"
            )
    return out


def update_state(succeeded: bool, now: datetime.datetime, extra_warnings) -> list:
    """Record the outcome and rewrite the warning file the shell prints."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    last_success = STATE_DIR / "last-success"
    first_failure = STATE_DIR / "failing-since"
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n"
    warnings = []
    if succeeded:
        last_success.write_text(stamp)
        first_failure.unlink(missing_ok=True)
    else:
        if not first_failure.exists():
            first_failure.write_text(stamp)
        # Age of the last success, or of the first recorded failure on a
        # machine that has never succeeded since this file existed.
        ref_file = last_success if last_success.exists() else first_failure
        ref = parse_stamp(ref_file.read_text()) or now
        if now - ref > STALE_AFTER:
            what = (
                "last succeeded" if last_success.exists() else "has been failing since"
            )
            warnings.append(
                f"this machine {what} {ref:%Y-%m-%d %H:%M}Z ({describe_age(now - ref)} ago);"
                " see: journalctl --user -u claude-sessions-backup"
            )
    warnings.extend(extra_warnings)
    text = "".join(f"claude-sessions-backup: {w}\n" for w in warnings)
    (STATE_DIR / "warning").write_text(text)
    return warnings


def main() -> int:
    label = machine_label()
    local = socket.gethostname().split(".")[0] == "big-storage"
    if local:
        # Never recreate /backups/machines on the root fs when the volume isn't
        # mounted (as happened after the 2026-10-20 crash).
        if not os.path.ismount("/backups") or not BACKUP_ROOT.is_dir():
            print(
                f"/backups is not mounted (or {BACKUP_ROOT} is missing); refusing to back up",
                file=sys.stderr,
            )
            return 2
        dest_root = BACKUP_ROOT / label / "claude-sessions"
        dest_root.mkdir(parents=True, exist_ok=True)
        dest_prefix = f"{dest_root}/"
        rsync_base = ["rsync", *RSYNC_OPTS]
    else:
        if not KEY.exists():
            print(
                f"missing ssh key {KEY}; generate it and authorize it on {BACKUP_HOST}",
                file=sys.stderr,
            )
            return 2
        # rrsync on the server makes paths relative to this machine's claude-sessions dir.
        dest_prefix = f"tim@{BACKUP_HOST}:"
        rsync_base = ["rsync", *RSYNC_OPTS, "-e", SSH]

    print(
        f"claude-sessions-backup: {label} -> {'local ' + str(dest_root) if local else BACKUP_HOST}"
    )
    failures = 0
    for job_label, extra, src, dest in plan_jobs(SOURCES, dest_prefix):
        if src is None:
            print(f"  skip {job_label}: not present")
            continue
        r = subprocess.run(
            [*rsync_base, *extra, src, dest],
            capture_output=True,
            text=True,
            check=False,
        )
        stats = {
            ln.split(":")[0].strip(): ln.split(":", 1)[1].strip()
            for ln in r.stdout.splitlines()
            if ":" in ln
        }
        if r.returncode in RSYNC_OK:
            print(
                f"  ok   {job_label}: {stats.get('Number of regular files transferred', '?')} files sent, "
                f"{stats.get('Total transferred file size', '?')} ({stats.get('Number of files', '?')} total)"
            )
        else:
            failures += 1
            print(
                f"  FAIL {job_label}: rsync exit {r.returncode}\n{r.stderr.strip()[:1000]}",
                file=sys.stderr,
            )

    # Timestamp marker so the destination shows when the last full run finished.
    # Only a run with no failures moves it: it is what the staleness check reads.
    now = datetime.datetime.now(datetime.UTC)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n"
    if failures:
        pass
    elif local:
        (dest_root / ".last-backup").write_text(stamp)
    else:
        with tempfile.TemporaryDirectory() as td:
            marker = pathlib.Path(td) / ".last-backup"
            marker.write_text(stamp)
            r = subprocess.run(
                [*rsync_base, str(marker), f"{dest_prefix}./"],
                capture_output=True,
                text=True,
                check=False,
            )
            if r.returncode != 0:
                failures += 1
                print(f"  FAIL marker: {r.stderr.strip()[:500]}", file=sys.stderr)

    others = stale_machines(BACKUP_ROOT, now, skip=label) if local else []
    for w in update_state(failures == 0, now, others):
        print(f"  WARNING {w}", file=sys.stderr)
    print(f"  done at {stamp.strip()} with {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    if shutil.which("rsync") is None:
        print("rsync not installed", file=sys.stderr)
        sys.exit(2)
    started = time.monotonic()
    code = main()
    print(f"  took {time.monotonic() - started:.0f}s")
    sys.exit(code)
