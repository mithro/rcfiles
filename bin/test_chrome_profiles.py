#!/usr/bin/env python3
"""Tests for chrome-profiles.py.

Self-contained / stdlib-only to match the script it tests -- run with:
    uv run python bin/test_chrome_profiles.py
Exits non-zero if any case fails; prints one line per case.

Everything runs against a fake $HOME and a fake /proc built in a temporary
directory inside the repository's tmp/, so no real profile is read. The
LevelDB stores are written here as write-ahead logs, the one on-disk form
that needs no compression or index to produce.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    spec = importlib.util.spec_from_file_location(
        "chrome_profiles", os.path.join(HERE, "chrome-profiles.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cp = _load()
FAILED = []
UUID_A = "11111111-2222-3333-4444-555555555555"
UUID_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SECRET = "SECRET-SENTINEL"  # stands in for every token the extension stores


def check(name, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        print(f"       got:  {got!r}\n       want: {want!r}")
        FAILED.append(name)


def varint(n):
    out = bytearray()
    while n >= 0x80:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def log_file(entries, sequence=1):
    """A LevelDB .log holding one write batch: {key: value, or None for a deletion}."""
    batch = struct.pack("<QI", sequence, len(entries))
    for key, value in entries.items():
        batch += (
            b"\x00" + varint(len(key)) + key
            if value is None
            else b"\x01" + varint(len(key)) + key + varint(len(value)) + value
        )
    return (
        b"\0\0\0\0" + struct.pack("<HB", len(batch), 1) + batch
    )  # crc (unchecked), length, FULL


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(content, bytes) else "w") as f:
        f.write(content if isinstance(content, (bytes, str)) else json.dumps(content))


def user_data_dir(path, profiles, last_active=()):
    """profiles: {dir: (info_cache entry, Preferences or None for a missing directory)}."""
    write(
        os.path.join(path, "Local State"),
        {
            "profile": {
                "info_cache": {d: info for d, (info, _) in profiles.items()},
                "last_active_profiles": list(last_active),
            }
        },
    )
    for d, (_, prefs) in profiles.items():
        if prefs is not None:
            write(os.path.join(path, d, "Preferences"), prefs)


def extension(**entry):
    return {
        "extensions": {
            "settings": {cp.EXTENSION_ID: {"manifest": {"version": "1.2.3"}, **entry}}
        }
    }


def storage(profile, **values):
    write(
        os.path.join(
            profile, "Local Extension Settings", cp.EXTENSION_ID, "000003.log"
        ),
        log_file({k.encode(): json.dumps(v).encode() for k, v in values.items()}),
    )


def test_parse_cmdline():
    check(
        "cmdline: NUL separated browser",
        cp.parse_cmdline(
            "/opt/x/chrome\0--user-data-dir=/a/b\0--remote-debugging-port=0\0about:blank\0"
        ),
        (True, {"--user-data-dir": "/a/b", "--remote-debugging-port": "0"}),
    )
    check(
        "cmdline: space separated, path with spaces, trailing URL",
        cp.parse_cmdline(
            "/opt/x/chrome --user-data-dir=/a/my dir --no-first-run --remote-debugging-port=9222 about:blank"
        ),
        (True, {"--user-data-dir": "/a/my dir", "--remote-debugging-port": "9222"}),
    )
    check(
        "cmdline: child process",
        cp.parse_cmdline("/opt/x/chrome --type=renderer --user-data-dir=/a/b")[0],
        False,
    )
    check("cmdline: no options", cp.parse_cmdline("/opt/x/chrome\0"), (True, {}))
    spaced_dir = os.path.join(tempfile.mkdtemp(dir=TMP), "my dir")
    os.makedirs(spaced_dir)
    check(
        "cmdline: space separated, URL straight after --user-data-dir",
        cp.parse_cmdline(
            f"/opt/x/chrome --user-data-dir={spaced_dir} https://example.invalid/a b --no-first-run"
        )[1],
        {"--user-data-dir": spaced_dir},
    )
    check(
        "cmdline: NUL separated, URL straight after --user-data-dir",
        cp.parse_cmdline(
            "/opt/x/chrome\0--user-data-dir=/a/b\0https://example.invalid/\0"
        )[1],
        {"--user-data-dir": "/a/b"},
    )
    check(
        "cmdline: relative --user-data-dir is taken from the browser's cwd",
        cp.parse_cmdline("/opt/x/chrome\0--user-data-dir=rel/p\0", cwd="/base")[1],
        {"--user-data-dir": "/base/rel/p"},
    )
    snap_exe = "/snap/chromium/1/usr/lib/chromium-browser/chrome"
    check(
        "default dir: snap's private $HOME is not used",
        [
            cp.default_user_data_dir(snap_exe, {"HOME": "/h/snap/chromium/1", **env})
            for env in (
                {"SNAP_USER_COMMON": "/h/snap/chromium/common"},
                {"SNAP_REAL_HOME": "/h"},
            )
        ],
        ["/h/snap/chromium/common/chromium"] * 2,
    )


def snappy_literal(data):
    """`data` as Snappy that is one long literal (valid, just not compressed)."""
    return (
        varint(len(data)) + bytes([61 << 2]) + struct.pack("<H", len(data) - 1) + data
    )


def table_file(entries, compress):
    """A LevelDB .ldb: one data block, {key: (sequence, value or None for a deletion)}."""

    def block(pairs):
        raw = b"".join(
            varint(0) + varint(len(k)) + varint(len(v)) + k + v for k, v in pairs
        ) + struct.pack("<II", 0, 1)  # one restart point, at offset 0
        return (
            snappy_literal(raw) + b"\x01" if compress else raw + b"\x00"
        ) + b"\0" * 4

    data = block(
        (key + struct.pack("<Q", seq << 8 | (value is not None)), value or b"")
        for key, (seq, value) in sorted(entries.items())
    )
    index = block([(b"\xff", varint(0) + varint(len(data) - 5))])
    handles = varint(0) + varint(0) + varint(len(data)) + varint(len(index) - 5)
    return data + index + handles.ljust(40, b"\0") + bytes.fromhex("57fb808b247547db")


def test_leveldb():
    # 9 bytes: literal "abc", then a 6-byte copy from 3 back (overlapping).
    check(
        "snappy: literal + overlapping copy",
        cp.snappy_decompress(b"\x09\x08abc\x09\x03"),
        b"abcabcabc",
    )
    tmp = tempfile.mkdtemp(dir=TMP)
    write(
        os.path.join(tmp, "000003.log"),
        log_file({b"a": b"old", b"gone": b"x"}, sequence=1),
    )
    write(
        os.path.join(tmp, "000005.log"),
        log_file({b"a": b"new", b"gone": None}, sequence=10),
    )
    write(os.path.join(tmp, "LOCK"), b"")
    check(
        "leveldb: newest value wins, deletions drop the key",
        cp.leveldb_dict(tmp),
        {b"a": b"new"},
    )
    for compress in (False, True):
        tmp = tempfile.mkdtemp(dir=TMP)
        big = bytes(range(256)) * 20
        write(
            os.path.join(tmp, "000004.ldb"),
            table_file(
                {b"a": (5, b"table"), b"big": (6, big), b"gone": (7, None)}, compress
            ),
        )
        write(
            os.path.join(tmp, "000003.log"),
            log_file({b"a": b"older", b"gone": b"x"}, sequence=1),
        )
        write(os.path.join(tmp, "000009.ldb"), b"not a table at all" * 10)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            got = cp.leveldb_dict(tmp)
        check(
            f"leveldb: table ({'snappy' if compress else 'uncompressed'}) beats older log, bad file only warns",
            (got, "000009.ldb" in err.getvalue()),
            ({b"a": b"table", b"big": big}, True),
        )


def build_home(home):
    config = os.path.join(home, ".config")
    main = os.path.join(config, "google-chrome")
    user_data_dir(
        main,
        {
            "Default": (
                {"name": "Main", "user_name": "main@example.invalid"},
                {
                    "google": {"services": {"consented_to_sync": True}},
                    "sync": {"has_setup_completed": True},
                    "account_info": [{"email": "web@example.invalid"}],
                    **extension(disable_reasons=[]),
                },
            ),
            "Profile 1": (
                {"name": "No sync", "user_name": "second@example.invalid"},
                extension(disable_reasons=[1]),
            ),
            "Profile 2": ({"name": "Legacy", "user_name": ""}, extension(state=0)),
            "Profile 9": ({"name": "Gone"}, None),
        },
        last_active=["Default"],
    )
    storage(
        os.path.join(main, "Default"),
        accountUuid=UUID_A,
        tokenOrg={"uuid": "org-1"},
        tokenScope=SECRET,
        codeVerifier=SECRET,
        oauthState=SECRET,
        accessToken=SECRET,
        bridgeDisplayName="laptop",
    )
    storage(
        os.path.join(main, "Profile 1"),
        accountUuid=UUID_B,
        tokenScope=SECRET,
        lastAuthFailureReason="session_expired",
    )
    write(
        os.path.join(home, ".claude.json"),
        {"oauthAccount": {"accountUuid": UUID_A, "emailAddress": "a@example.invalid"}},
    )
    write(
        os.path.join(
            main,
            "Default",
            "IndexedDB",
            "https_claude.ai_0.indexeddb.leveldb",
            "000003.log",
        ),
        log_file(
            {
                # The account's own email sits next to its UUID at the very
                # start of the value; another record's email follows later.
                b"k": b'o"\x04uuid"\x24'
                + UUID_B.encode()
                + b'"\x0demail_address"\x11b@example.invalid'
                + b'"'
                + b" " * 300
                + b'"\x05email"\x15wrong@example.invalid{'
            }
        ),
    )
    # Files this tool cannot make sense of: one directory is reported as an
    # error, the other read as far as it goes.
    write(
        os.path.join(config, "broken", "Local State"),
        {"profile": {"info_cache": {"Default": None}}},
    )
    odd = os.path.join(config, "odd")
    user_data_dir(odd, {"Default": ({"name": 5}, extension(disable_reasons=[]))})
    storage(
        os.path.join(odd, "Default"), accountUuid=5, tokenOrg="x", tokenScope=SECRET
    )
    user_data_dir(
        os.path.join(home, "elsewhere-real"), {"Default": ({"name": "moved"}, {})}
    )
    os.symlink(os.path.join(home, "elsewhere-real"), os.path.join(config, "linked"))
    write(os.path.join(config, "Electron App", "Local State"), {"os_crypt": {}})
    write(os.path.join(config, "Electron App", "Preferences"), {})
    write(os.path.join(config, "headless", "Local State"), {"os_crypt": {}})
    write(os.path.join(config, "headless", "Default", "Preferences"), {})
    for where in (
        "chrome/work",
        ".local/share/usage/accounts/x/chrome",
        ".local/state/ext/profile",
        ".cache/pw/mcp-chrome-1",
        "src/repo/tmp/chrome-profile",
        ".local/share/a/b/c/d/too-deep",
    ):
        user_data_dir(os.path.join(home, where), {"Default": ({"name": where}, {})})


def build_proc(proc, home):
    def process(pid, exe, cmdline):
        os.makedirs(os.path.join(proc, pid))
        os.symlink(exe, os.path.join(proc, pid, "exe"))
        os.symlink(home, os.path.join(proc, pid, "cwd"))
        write(os.path.join(proc, pid, "cmdline"), cmdline)
        write(os.path.join(proc, pid, "environ"), f"HOME={home}\0DISPLAY=:7\0")

    work = os.path.join(home, "chrome", "work")
    write(os.path.join(work, "DevToolsActivePort"), "41000\n/devtools/browser/x\n")
    process("100", "/opt/google/chrome/chrome", "/opt/google/chrome/chrome")
    # A later `chrome URL` hands its URL over and exits; it is not the root.
    process(
        "150",
        "/opt/google/chrome/chrome",
        "/opt/google/chrome/chrome https://example.invalid/",
    )
    process(
        "600",
        "/opt/google/chrome/chrome",
        "/opt/google/chrome/chrome\0--user-data-dir=chrome/relative\0https://example.invalid/\0",
    )
    process(
        "101",
        "/opt/google/chrome/chrome",
        "/opt/google/chrome/chrome --type=renderer --user-data-dir=/nowhere",
    )
    process(
        "200",
        "/opt/google/chrome/chrome (deleted)",
        f"/opt/google/chrome/chrome --remote-debugging-port=0 --user-data-dir={work} about:blank",
    )
    process(
        "300",
        "/usr/lib/chromium/chromium",
        "/usr/lib/chromium/chromium\0--user-data-dir=/elsewhere/x\0",
    )
    process("400", "/usr/bin/python3", "python3 --user-data-dir=/not/a/browser")
    process("500", "/somewhere/chrome", "/somewhere/chrome")


def test_report():
    home = tempfile.mkdtemp(dir=TMP)
    proc = os.path.join(home, "proc")
    saved = {k: os.environ.get(k) for k in ("HOME", "XDG_CONFIG_HOME")}
    os.environ["HOME"] = home
    os.environ.pop("XDG_CONFIG_HOME", None)
    try:
        build_home(home)
        build_proc(proc, home)
        running = cp.running_browsers(proc)
        check(
            "running: browsers by user-data-dir, children and non-browsers skipped",
            {
                u.replace(home, "~"): (b["pid"], b["cdp_port"], b["display"])
                for u, b in running.items()
            },
            {
                "~/.config/google-chrome": (100, None, "DISPLAY=:7"),
                "~/chrome/work": (200, "41000", "DISPLAY=:7"),
                "/elsewhere/x": (300, None, "DISPLAY=:7"),
                "?unknown-default-for:/somewhere/chrome:500": (500, None, "DISPLAY=:7"),
                "~/chrome/relative": (600, None, "DISPLAY=:7"),
            },
        )

        def found(**kw):
            return [u.replace(home, "~") for u in cp.user_data_dirs({}, **kw)]

        default = [
            "~/.config/Electron App",
            "~/.config/broken",
            "~/.config/google-chrome",
            "~/.config/headless",
            "~/.config/odd",
            "~/.local/share/usage/accounts/x/chrome",
            "~/.local/state/ext/profile",
            "~/chrome/work",
            "~/elsewhere-real",  # reached through the ~/.config/linked symlink
        ]
        check("discovery: default roots, depth limited", found(), default)
        check(
            "discovery: --cache",
            found(cache=True),
            sorted(default + ["~/.cache/pw/mcp-chrome-1"]),
        )
        check(
            "discovery: --scan",
            found(scan=[os.path.join(home, "src")]),
            sorted(default + ["~/src/repo/tmp/chrome-profile"]),
        )
        check(
            "discovery: --scan of a user-data-dir itself",
            found(scan=[os.path.join(home, "src", "repo", "tmp", "chrome-profile")]),
            sorted(default + ["~/src/repo/tmp/chrome-profile"]),
        )

        def run(*argv):
            text = io.StringIO()
            with contextlib.redirect_stdout(text):
                sys.argv = ["chrome-profiles.py", *argv]
                cp.main()
            return text.getvalue()

        real_running, cp.running_browsers = cp.running_browsers, lambda: running
        try:
            report = cp.collect()
            out = io.StringIO(run("--web-logins"))
            markdown, as_json = run("--format", "markdown"), run("--json")
        finally:
            cp.running_browsers = real_running
        check("json: main() prints the same report", json.loads(as_json), report)
        check(
            "markdown: a header, a rule and one line per existing profile",
            [line.count("|") for line in markdown.split("\n\n")[0].splitlines()],
            [12]
            * (
                2
                + sum(
                    p["exists"] for d in report["user_data_dirs"] for p in d["profiles"]
                )
            ),
        )
        check(
            "errors: an unreadable directory is reported, not fatal",
            (
                [e["user_data_dir"].replace(home, "~") for e in report["errors"]],
                "Could not read" in out.getvalue(),
            ),
            (["~/.config/broken"], True),
        )
        odd = {
            d["user_data_dir"].replace(home, "~"): d for d in report["user_data_dirs"]
        }["~/.config/odd"]["profiles"][0]
        check(
            "errors: wrong-typed name, account and org are dropped",
            (
                odd["name"],
                odd["claude_extension"]["account_uuid"],
                odd["claude_extension"]["org_uuid"],
            ),
            (None, None, None),
        )
        dirs = {
            d["user_data_dir"].replace(home, "~"): d for d in report["user_data_dirs"]
        }
        check(
            "report: Electron app left out, headless dir kept, running-only dir has no profile list",
            (sorted(dirs), sorted(report["unmatched_running"])),
            (
                sorted(set(default) - {"~/.config/Electron App", "~/.config/broken"}),
                [
                    "/elsewhere/x",
                    os.path.join(home, "chrome", "relative"),
                    "?unknown-default-for:/somewhere/chrome:500",
                ],
            ),
        )
        main = {p["dir"]: p for p in dirs["~/.config/google-chrome"]["profiles"]}
        check(
            "report: sign-in, sync, windows, web logins",
            [
                (
                    p["exists"],
                    p["chrome_signin"],
                    p["sync"],
                    p["windows_open"],
                    p["web_accounts"],
                )
                for p in main.values()
            ],
            [
                (True, "main@example.invalid", True, True, ["web@example.invalid"]),
                (True, "second@example.invalid", False, False, []),
                (True, None, None, False, []),
                (False, None, None, False, []),
            ],
        )
        check(
            "report: a dir with no browser has no open windows",
            (
                dirs["~/.local/state/ext/profile"]["running"],
                dirs["~/chrome/work"]["running"]["pid"],
            ),
            (None, 200),
        )
        ext = {d: p["claude_extension"] for d, p in main.items()}
        check(
            "extension: enabled, disabled (reasons), disabled (legacy state), missing",
            [(e["installed"], e.get("enabled")) for e in ext.values()],
            [(True, True), (True, False), (True, False), (False, None)],
        )
        check(
            "extension: account, sign-in state, email from ~/.claude.json and from site data",
            [
                (
                    e["version"],
                    e["signed_in"],
                    e["auth_failure"],
                    e["account_email"],
                    e["email_source"],
                    e["browser_name"],
                )
                for e in (ext["Default"], ext["Profile 1"])
            ],
            [
                ("1.2.3", True, None, "a@example.invalid", "~/.claude.json", "laptop"),
                (
                    "1.2.3",
                    False,
                    "session_expired",
                    "b@example.invalid",
                    "claude.ai site data",
                    None,
                ),
            ],
        )
        check(
            "extension: installed but never opened has no account",
            ext["Profile 2"].get("account_uuid"),
            None,
        )
        lines = out.getvalue().split("\n\n")[0].splitlines()
        check(
            "table: every line the same width",
            len({cp.width(line) for line in lines}),
            1,
        )
        check(
            "table: stale profile left out and counted",
            ("Gone" in out.getvalue(), "1 profile(s) listed" in out.getvalue()),
            (False, True),
        )
        check(
            "secrets: nothing from the extension's token storage in any output",
            [SECRET in text for text in (out.getvalue(), markdown, as_json)],
            [False] * 3,
        )
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(HERE), "tmp"), exist_ok=True)
    TMP = tempfile.mkdtemp(
        prefix="test-chrome-profiles-", dir=os.path.join(os.path.dirname(HERE), "tmp")
    )
    try:
        test_parse_cmdline()
        test_leveldb()
        test_report()
    finally:
        shutil.rmtree(TMP)
    print(f"\n{len(FAILED)} failed" if FAILED else "\nall passed")
    sys.exit(1 if FAILED else 0)
