#!/usr/bin/env python3
"""Tests for claude-sessions-backup.py's planning and staleness logic.

Self-contained / stdlib-only to match the script it tests -- run with:
    uv run python bin/test_claude_sessions_backup.py
Exits non-zero if any case fails; prints one line per case.

plan_jobs() is the unit under test for the transfer layout because every bug
this script has had was in the rsync arguments (a dropped trailing slash that
nested projects/projects/, a named single-file destination that rrsync 3.5.0
rejects, symlinked project directories copied as links), and those can be
checked without a network. Real rsync is used for the end-to-end layout case.
"""

import datetime
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    spec = importlib.util.spec_from_file_location(
        "claude_sessions_backup", os.path.join(HERE, "claude-sessions-backup.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


csb = _load()
UTC = datetime.UTC
FAILED = []


def case(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}{'' if ok else ': ' + str(detail)}")
    if not ok:
        FAILED.append(name)


def make_tree(root: pathlib.Path):
    """A home-like tree: a projects dir with one real and one symlinked project."""
    projects = root / "claude" / "projects"
    (projects / "-home-real").mkdir(parents=True)
    (projects / "-home-real" / "a.jsonl").write_text("real\n")
    other = root / "claude-other" / "projects" / "-home-linked"
    other.mkdir(parents=True)
    (other / "b.jsonl").write_text("linked\n")
    (projects / "-home-linked").symlink_to(other)
    (projects / "odd[name]").mkdir()
    (root / "claude" / "history.jsonl").write_text("history\n")
    # A Claude Desktop config dir with state worth keeping and state that is
    # cache or credentials (names as found in ~/.config/Claude).
    desktop = root / "desktop"
    for d in ("claude-code-sessions/acct/org", "Code Cache/js", "claude-code/2.1.325"):
        (desktop / d).mkdir(parents=True)
    (desktop / "claude-code-sessions/acct/org/local_1.json").write_text("{}\n")
    (desktop / "claude_desktop_config.json").write_text("{}\n")
    (desktop / "Code Cache/js/x").write_text("cache\n")
    (desktop / "claude-code/2.1.325/claude").write_text("binary\n")
    (desktop / "config.json").write_text('{"oauth:tokenCache": "secret"}\n')
    (desktop / "Cookies").write_text("cookies\n")
    (desktop / "Cookies-journal").write_text("")
    # Excluded names deeper down must be kept: the excludes are top-level only.
    (desktop / "scratch-workspaces/Cache").mkdir(parents=True)
    (desktop / "scratch-workspaces/Cache/keep").write_text("user file\n")
    (desktop / "scratch-workspaces/config.json").write_text("{}\n")
    # An excluded entry that is a symlink to a directory elsewhere must not be
    # followed by plan_jobs' separate linked-directory job.
    elsewhere = root / "elsewhere-local-storage"
    elsewhere.mkdir()
    (elsewhere / "leveldb").write_text("session token\n")
    (desktop / "Local Storage").symlink_to(elsewhere)
    # Take the desktop filters from the real SOURCES so a broken wiring there
    # is caught; only the path is swapped for the test tree.
    filters = next(f for _s, n, f in csb.SOURCES if n == "claude-desktop")
    return [
        (str(projects), "projects", []),
        (str(root / "claude" / "history.jsonl"), "history.jsonl", []),
        (str(root / "claude" / "todos"), "todos", []),
        (str(desktop), "claude-desktop", filters),
    ]


def test_plan_shapes():
    with tempfile.TemporaryDirectory(dir=HERE) as td:
        root = pathlib.Path(td)
        sources = make_tree(root)
        jobs = csb.plan_jobs(sources, "tim@host:")
        by_dest = {
            dest: (label, extra, src) for label, extra, src, dest in jobs if dest
        }
        case(
            "directory source ends in a slash",
            by_dest["tim@host:projects/"][2].endswith("/projects/"),
        )
        case("directory destination is its own name", "tim@host:projects/" in by_dest)
        case(
            "symlinked project is excluded from the main transfer",
            by_dest["tim@host:projects/"][1] == ["--exclude=/-home-linked"],
            by_dest["tim@host:projects/"][1],
        )
        linked = by_dest.get("tim@host:projects/-home-linked/")
        case(
            "symlinked project is sent from its resolved path",
            linked is not None
            and linked[2] == str(root / "claude-other/projects/-home-linked") + "/",
            linked,
        )
        case(
            "a file is sent into the directory, never to a name",
            by_dest["tim@host:./"][2].endswith("/history.jsonl"),
        )
        case(
            "an excluded symlinked directory gets no separate job",
            not any("Local Storage" in d for d in by_dest),
            list(by_dest),
        )
        case(
            "a missing source is reported, not transferred",
            [j for j in jobs if j[2] is None] == [(sources[2][0], None, None, None)],
        )
        case(
            "local prefix builds absolute destinations",
            csb.plan_jobs(sources, "/b/m/")[0][3] == "/b/m/projects/",
        )


def test_escape():
    case(
        "filter metacharacters are escaped",
        csb.rsync_escape("a[b]*?\\") == "a\\[b]\\*\\?\\\\",
    )


def test_real_rsync_layout():
    """Run the planned jobs twice with real rsync: flat layout, files updated in place."""
    if shutil.which("rsync") is None:
        print("skip real rsync layout: rsync not installed")
        return
    with tempfile.TemporaryDirectory(dir=HERE) as td:
        root = pathlib.Path(td)
        sources = make_tree(root)
        dest = root / "dest"
        dest.mkdir()
        for round_no in (1, 2):
            (root / "claude" / "history.jsonl").write_text("history\n" * round_no)
            for _label, extra, src, dst in csb.plan_jobs(sources, f"{dest}/"):
                if src is None:
                    continue
                r = subprocess.run(
                    ["rsync", *csb.RSYNC_OPTS, *extra, src, dst],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                case(
                    f"round {round_no}: rsync {dst[len(str(dest)) :]} exits 0",
                    r.returncode == 0,
                    r.stderr,
                )
        case(
            "no nested projects/projects", not (dest / "projects" / "projects").exists()
        )
        case(
            "real project copied",
            (dest / "projects/-home-real/a.jsonl").read_text() == "real\n",
        )
        linked = dest / "projects/-home-linked"
        case(
            "linked project copied as a directory",
            linked.is_dir() and not linked.is_symlink(),
        )
        case(
            "linked project content copied",
            (linked / "b.jsonl").read_text() == "linked\n",
        )
        case(
            "file lands at the top level",
            (dest / "history.jsonl").read_text() == "history\n" * 2,
        )
        desk = dest / "claude-desktop"
        case(
            "desktop session index copied",
            (desk / "claude-code-sessions/acct/org/local_1.json").exists(),
        )
        case(
            "desktop config copied",
            (desk / "claude_desktop_config.json").exists(),
        )
        left_out = [
            n
            for n in (
                "Code Cache",
                "claude-code",
                "config.json",
                "Cookies",
                "Cookies-journal",
                "Local Storage",
            )
            if (desk / n).exists() or (desk / n).is_symlink()
        ]
        case(
            "desktop caches, binaries and credentials left out", not left_out, left_out
        )
        case(
            "excluded names below the top level are kept",
            (desk / "scratch-workspaces/Cache/keep").exists()
            and (desk / "scratch-workspaces/config.json").exists(),
        )

    case(
        "the real SOURCES include Claude Desktop with its excludes",
        any(
            name == "claude-desktop" and "--exclude=/config.json" in filters
            for _src, name, filters in csb.SOURCES
        ),
    )


def test_stale_machines():
    with tempfile.TemporaryDirectory(dir=HERE) as td:
        root = pathlib.Path(td)
        now = datetime.datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
        for name, stamp in [
            ("fresh.example", "2026-11-18T11:00:00Z"),
            ("old.example", "2026-09-29T16:32:52Z"),
            ("self.example", "2026-01-01T00:00:00Z"),
            ("junk.example", "not a date"),
        ]:
            d = root / name / "claude-sessions"
            d.mkdir(parents=True)
            (d / ".last-backup").write_text(stamp + "\n")
        (root / "no-backup.example").mkdir()
        got = csb.stale_machines(root, now, skip="self.example")
        case(
            "fresh machine is not reported",
            not any("fresh.example" in w for w in got),
            got,
        )
        case(
            "stale machine is reported with its age",
            any(w.startswith("old.example") and "49 days" in w for w in got),
            got,
        )
        case("this machine is skipped", not any("self.example" in w for w in got), got)
        case(
            "unparseable marker is reported",
            any(w.startswith("junk.example") for w in got),
            got,
        )
        case("machines without a backup dir are ignored", len(got) == 2, got)


def test_update_state():
    with tempfile.TemporaryDirectory(dir=HERE) as td:
        csb.STATE_DIR = pathlib.Path(td) / "state"
        t0 = datetime.datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        day = datetime.timedelta(days=1)
        warning = csb.STATE_DIR / "warning"
        case(
            "success gives no warning",
            csb.update_state(True, t0, []) == [] and warning.read_text() == "",
        )
        case(
            "a recent failure gives no warning",
            csb.update_state(False, t0 + day, []) == [],
        )
        got = csb.update_state(False, t0 + 3 * day, [])
        case(
            "a long failure warns with the last success",
            len(got) == 1 and "2026-11-01" in got[0],
            got,
        )
        case(
            "the warning file carries it",
            warning.read_text().startswith("claude-sessions-backup: this machine"),
        )
        got = csb.update_state(True, t0 + 4 * day, ["other.example: stale"])
        case(
            "success clears it but keeps other machines",
            got == ["other.example: stale"],
            got,
        )
        (csb.STATE_DIR / "last-success").unlink()
        csb.update_state(False, t0 + 5 * day, [])
        got = csb.update_state(False, t0 + 8 * day, [])
        case(
            "never-succeeded machine warns from its first failure",
            len(got) == 1 and "failing since" in got[0],
            got,
        )


if __name__ == "__main__":
    test_plan_shapes()
    test_escape()
    test_real_rsync_layout()
    test_stale_machines()
    test_update_state()
    if FAILED:
        print(f"\n{len(FAILED)} case(s) failed")
        sys.exit(1)
    print("\nall cases passed")
