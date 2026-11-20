#!/usr/bin/env python3
"""Tests for bin/claude-plugins-update.py, against a stub `claude` on PATH.

Run with:
    uv run python bin/test_claude_plugins_update.py
Exits non-zero if any case fails; prints one line per case.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "claude-plugins-update.py")

PLUGINS = [
    {"id": "episodic-memory@superpowers-marketplace", "scope": "user"},
    {"id": "hook-x@mithro-personal", "scope": "user", "enabled": False},
    {"id": "proj-only@somewhere", "scope": "project"},
]

# The stub logs each call and fails `plugin update` for any id in $STUB_FAIL.
STUB = """#!/bin/sh
echo "$*" >> "$STUB_LOG"
if [ "$1 $2" = "plugin list" ]; then cat "$STUB_LIST"; exit 0; fi
if [ "$1 $2" = "plugin update" ]; then
\tfor last; do :; done
\tcase " $STUB_FAIL " in *" $last "*) exit 1;; esac
fi
exit 0
"""


def run_case(tmp, fail="", with_claude=True):
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir, exist_ok=True)
    log = os.path.join(tmp, "log")
    if os.path.exists(log):
        os.unlink(log)
    stub = os.path.join(bindir, "claude")
    if with_claude:
        with open(stub, "w") as f:
            f.write(STUB)
        os.chmod(stub, 0o755)
    elif os.path.exists(stub):
        os.unlink(stub)
    listing = os.path.join(tmp, "list.json")
    with open(listing, "w") as f:
        json.dump(PLUGINS, f)
    env = {
        "PATH": bindir + ":/usr/bin:/bin",
        "STUB_LOG": log,
        "STUB_LIST": listing,
        "STUB_FAIL": fail,
    }
    proc = subprocess.run(
        [sys.executable, SCRIPT], env=env, capture_output=True, text=True, check=False
    )
    calls = []
    if os.path.exists(log):
        with open(log) as f:
            calls = f.read().splitlines()
    return proc, calls


def main():
    results = []

    def check(name, cond, detail=""):
        results.append(cond)
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f": {detail}"))

    scratch = os.path.join(HERE, "..", "tmp")  # gitignored; never /tmp
    os.makedirs(scratch, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        proc, calls = run_case(tmp)
        expected = [
            "plugin marketplace update",
            "plugin list --json",
            "plugin update --scope user episodic-memory@superpowers-marketplace",
            "plugin update --scope user hook-x@mithro-personal",
        ]
        check(
            "updates every user-scope plugin, skips project scope",
            calls == expected,
            calls,
        )
        check("exit 0 when all succeed", proc.returncode == 0, proc.stderr)

        proc, calls = run_case(tmp, fail="episodic-memory@superpowers-marketplace")
        check(
            "keeps going after a failed plugin",
            calls[-1].endswith("hook-x@mithro-personal"),
            calls,
        )
        check("exit 1 when one fails", proc.returncode == 1, proc.returncode)
        check(
            "names the failed plugin",
            "episodic-memory@superpowers-marketplace" in proc.stderr,
            proc.stderr,
        )

        proc, calls = run_case(tmp, with_claude=False)
        check(
            "no claude: skip with exit 0",
            proc.returncode == 0 and calls == [],
            (proc.returncode, calls),
        )

    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
