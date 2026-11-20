#!/usr/bin/env python3
"""Refresh every Claude Code marketplace and update every user-scope plugin.

Run by setup.sh's `claude` step. Plugins never update themselves, so one
installed in January stays on that version until something updates it. In
2026 that cost a laptop months of transcripts: episodic-memory 1.0.15 bundled
an old Claude Code that ignored cleanupPeriodDays (see
dot-claude/etc-claude-code/README.md), and the fix had shipped long before.

A plugin that fails to update is reported, and the script exits 1 after it
has tried every plugin.
"""

import json
import shutil
import subprocess
import sys


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=False).returncode


def user_plugins(claude):
    out = subprocess.run(
        [claude, "plugin", "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [p["id"] for p in json.loads(out) if p.get("scope") == "user"]


def main():
    claude = shutil.which("claude")
    if claude is None:
        print("claude-plugins-update: claude not installed, skipping")
        return 0
    failed = []
    if run([claude, "plugin", "marketplace", "update"]) != 0:
        failed.append("marketplace update")
    for plugin in user_plugins(claude):
        if run([claude, "plugin", "update", "--scope", "user", plugin]) != 0:
            failed.append(plugin)
    if failed:
        print("claude-plugins-update: failed: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("claude-plugins-update: done (restart Claude Code to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
