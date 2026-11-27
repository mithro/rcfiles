#!/usr/bin/env python3
"""Report every Chrome profile on this machine: the running browser and its
root pid, the Chrome sign-in, sync, and the Claude in Chrome extension's state.

Read-only and offline. It reads Chrome's own files and /proc; it never starts,
signals or attaches to a browser, and never prints tokens. Standard library
only. Linux only.

  chrome-profiles.py                    # boxed table for a terminal
  chrome-profiles.py --format markdown  # table to paste into a document
  chrome-profiles.py --json             # machine readable (--format json)
  chrome-profiles.py --web-logins       # add the Google web logins column
  chrome-profiles.py --cache            # also look in ~/.cache (Playwright)
  chrome-profiles.py --scan DIR         # also walk DIR, however deep

Where it looks. A user-data-dir is any directory holding a `Local State` file
with a `profile.info_cache` (Electron apps have the file but not the cache).
  $XDG_CONFIG_HOME/*            Chrome, Chromium and anything started with
                                --user-data-dir=~/.config/<name>
  ~/chrome/*                    the chrome-personal.sh / chrome-work.sh dirs
  ~/.local/share, ~/.local/state  to a limited depth
  ~/snap, ~/.var/app            snap and flatpak browsers
  every running browser         wherever its --user-data-dir points
Throwaway profiles in ~/.cache, tmp/ directories and repositories are only
found with --cache or --scan, or while a browser is running on them.

Where each fact comes from:
  profiles     <user-data-dir>/Local State -> profile.info_cache
  chrome login info_cache[..].user_name (the account Chrome itself is signed
               in to)
  sync         <profile>/Preferences -> google.services.consented_to_sync and
               sync.has_setup_completed
  web logins   <profile>/Preferences -> account_info (Google accounts signed
               in on the web in that profile; not the same as the Chrome login)
  running      /proc: a chrome or chromium executable with no --type= argument
               is a browser; its --user-data-dir (or the channel default)
               names the directory. That pid is the root of its process tree.
  windows      Local State -> profile.last_active_profiles. One browser
               process serves every profile in its directory, so this is the
               only record of which profiles have windows; written lazily.
  claude ext   <profile>/Preferences (or Secure Preferences)
               -> extensions.settings.<extension id>; version from its manifest
  enabled      the same entry: an empty `disable_reasons` list means enabled
               (older Chrome: `state` == 1)
  account      the extension's chrome.storage.local, a LevelDB in
               <profile>/Local Extension Settings/<extension id>: `accountUuid`
               and `tokenOrg.uuid`. The extension stores no email address.
  email        looked up from the account UUID in two places: ~/.claude.json
               `oauthAccount` (the account Claude Code uses), and the claude.ai
               site data (IndexedDB) of every profile found, where the
               signed-in account's UUID and email sit side by side. "?" means
               no profile on this machine has that account's claude.ai data.
  signed in    `tokenScope` present and no `lastAuthFailureReason`. This is
               the extension's last recorded state, not a live check.

JSON shape:
  {"user_data_dirs": [{"user_data_dir": str,
                       "running": null | {"pid", "exe", "display", "cdp_port"},
                       "profiles": [{"dir", "name", "exists", "chrome_signin",
                                     "sync", "web_accounts", "windows_open",
                                     "claude_extension": {"installed", ...}}]}],
   "unmatched_running": {user-data-dir: {...}}}
Profiles listed in Local State whose directory is gone have "exists": false;
the tables leave them out and say how many were skipped.
"""
import argparse
import glob
import json
import os
import re
import struct
import sys
import unicodedata
from collections import Counter

EXTENSION_ID = "fcoeoabgfenejglbffodgkkbkcdhcgfn"  # Claude in Chrome (Web Store)

BROWSER_EXES = {"chrome", "chromium", "chromium-browser"}
# Where a browser keeps its profiles when started without --user-data-dir:
# (executable path prefix, directory relative to $XDG_CONFIG_HOME or to ~).
DEFAULT_DIRS = [
    ("/opt/google/chrome/", "config", "google-chrome"),
    ("/opt/google/chrome-beta/", "config", "google-chrome-beta"),
    ("/opt/google/chrome-unstable/", "config", "google-chrome-unstable"),
    ("/opt/google/chrome-canary/", "config", "google-chrome-canary"),
    ("/usr/lib/chromium/", "config", "chromium"),
    ("/usr/lib/chromium-browser/", "config", "chromium"),
    ("/snap/chromium/", "home", "snap/chromium/common/chromium"),
]
# (directory relative to ~, how many levels below it a user-data-dir may sit).
SEARCH_ROOTS = [("chrome", 1), (".local/share", 4), (".local/state", 2), ("snap", 4), (".var/app", 4)]
PRUNE = {"node_modules", ".git", "Trash", "Steam"}


# --- a minimal read-only LevelDB reader ------------------------------------
# Chrome keeps the LOCK of a live database, so a real LevelDB library cannot
# open it. Reading the files directly needs no lock. Enough of the format is
# implemented to list every live key: write-ahead logs, tables, Snappy.

def varint(buf, pos):
    result = shift = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def snappy_decompress(buf):
    _, pos = varint(buf, 0)
    out = bytearray()
    while pos < len(buf):
        tag = buf[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:  # literal
            length = tag >> 2
            if length >= 60:
                nbytes = length - 59
                length = int.from_bytes(buf[pos:pos + nbytes], "little")
                pos += nbytes
            length += 1
            out += buf[pos:pos + length]
            pos += length
            continue
        if kind == 1:  # copy, 1-byte offset
            length = ((tag >> 2) & 7) + 4
            offset = ((tag >> 5) << 8) | buf[pos]
            pos += 1
        else:  # copy, 2- or 4-byte offset
            nbytes = 2 if kind == 2 else 4
            length = (tag >> 2) + 1
            offset = int.from_bytes(buf[pos:pos + nbytes], "little")
            pos += nbytes
        start = len(out) - offset
        if offset >= length:
            out += out[start:start + length]
        else:  # overlapping copy repeats the last `offset` bytes
            for i in range(length):
                out.append(out[start + i])
    return bytes(out)


def read_block(data, offset, size):
    raw = data[offset:offset + size]
    if data[offset + size] == 1:
        raw = snappy_decompress(raw)
    elif data[offset + size] != 0:
        raise ValueError("unsupported block compression")
    end = len(raw) - 4 - 4 * struct.unpack("<I", raw[-4:])[0]
    pos, key = 0, b""
    while pos < end:
        shared, pos = varint(raw, pos)
        unshared, pos = varint(raw, pos)
        value_len, pos = varint(raw, pos)
        key = key[:shared] + raw[pos:pos + unshared]
        pos += unshared
        yield key, raw[pos:pos + value_len]
        pos += value_len


def read_table(data):
    """Yield (sequence, kind, key, value) from an .ldb file; kind 1 = live, 0 = deleted."""
    footer = data[-48:]
    if footer[-8:] != bytes.fromhex("57fb808b247547db"):
        raise ValueError("not a LevelDB table")
    _, pos = varint(footer, 0)
    _, pos = varint(footer, pos)
    index_offset, pos = varint(footer, pos)
    index_size, pos = varint(footer, pos)
    for _, handle in read_block(data, index_offset, index_size):
        block_offset, p = varint(handle, 0)
        block_size, p = varint(handle, p)
        for internal_key, value in read_block(data, block_offset, block_size):
            trailer = struct.unpack("<Q", internal_key[-8:])[0]
            yield trailer >> 8, trailer & 0xFF, internal_key[:-8], value


def read_log(data):
    """Yield (sequence, kind, key, value) from a .log file (32 KiB blocks of record fragments)."""
    pos, record = 0, b""
    while pos + 7 <= len(data):
        if 32768 - pos % 32768 < 7:  # too little room for a header: block padding
            pos += 32768 - pos % 32768
            continue
        length, kind = struct.unpack("<HB", data[pos + 4:pos + 7])
        if kind == 0:  # preallocated or zeroed tail
            break
        fragment = data[pos + 7:pos + 7 + length]
        pos += 7 + length
        if kind in (1, 2):  # full, or first fragment
            record = b""
        record += fragment
        if kind not in (1, 4) or len(record) < 12:  # not yet the last fragment
            continue
        sequence, count = struct.unpack("<QI", record[:12])
        p = 12
        for i in range(count):
            entry_kind = record[p]
            key_len, p = varint(record, p + 1)
            key = record[p:p + key_len]
            p += key_len
            value = b""
            if entry_kind == 1:
                value_len, p = varint(record, p)
                value = record[p:p + value_len]
                p += value_len
            yield sequence + i, entry_kind, key, value


def leveldb_entries(directory):
    """Every record in a LevelDB directory, newest and oldest alike. Tolerates a file changing underfoot."""
    for name in sorted(os.listdir(directory)):
        reader = read_table if name.endswith(".ldb") else read_log if name.endswith(".log") else None
        if not reader:
            continue
        try:
            with open(os.path.join(directory, name), "rb") as f:
                yield from reader(f.read())
        except (OSError, ValueError, IndexError, struct.error) as e:
            print(f"warning: {directory}/{name}: {type(e).__name__}: {e}", file=sys.stderr)


def leveldb_dict(directory):
    """The database's current contents: the newest live value of each key."""
    newest = {}
    for sequence, kind, key, value in leveldb_entries(directory):
        if key not in newest or newest[key][0] < sequence:
            newest[key] = (sequence, kind, value)
    return {k: v for k, (_, kind, v) in newest.items() if kind == 1}



# --- finding browsers and profiles -------------------------------------------

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def home():
    return os.path.expanduser("~")


def config_home(env=os.environ):
    return env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME") or home(), ".config")


def parse_cmdline(raw):
    """(is a browser rather than a child, {--option: value}) from /proc/<pid>/cmdline.

    Chrome rewrites its command line with spaces instead of NULs (the browser
    as well as its children), so cut before each " --option". A value keeps
    its own spaces; the last option also swallows any trailing URL, which only
    matters for the port, so that is cut back to its digits.
    """
    args = re.split(r"[\0 ]+(?=--)", raw.rstrip("\0"))
    opts = dict(a.rstrip("\0").split("=", 1) for a in args if a.startswith("--") and "=" in a)
    if "--remote-debugging-port" in opts:
        opts["--remote-debugging-port"] = re.match(r"\d*", opts["--remote-debugging-port"]).group()
    return "--type" not in opts, opts


def default_user_data_dir(exe, env):
    for prefix, base, rel in DEFAULT_DIRS:
        if exe.startswith(prefix):
            return os.path.join(config_home(env) if base == "config" else env.get("HOME") or home(), rel)
    return None


def running_browsers(proc_root="/proc"):
    """{user-data-dir: {pid, exe, display, cdp_port}} for every Chrome browser process."""
    found = {}
    for proc in glob.glob(os.path.join(proc_root, "[0-9]*")):
        try:
            exe = os.readlink(proc + "/exe")
            if exe.endswith(" (deleted)"):  # replaced by an update while running
                exe = exe[:-len(" (deleted)")]
            if os.path.basename(exe) not in BROWSER_EXES:
                continue
            with open(proc + "/cmdline", "rb") as f:
                is_browser, opts = parse_cmdline(f.read().decode("utf-8", "replace"))
            if not is_browser:
                continue  # renderer, GPU, utility, zygote, crashpad
            with open(proc + "/environ", "rb") as f:
                env = dict(e.split("=", 1) for e in f.read().decode("utf-8", "replace").split("\0") if "=" in e)
        except OSError:
            continue  # exited, or not ours to read
        udd = (opts.get("--user-data-dir") or env.get("CHROME_USER_DATA_DIR")
               or default_user_data_dir(exe, env) or f"?unknown-default-for:{exe}")
        if not udd.startswith("?"):
            udd = os.path.realpath(udd)
        port = opts.get("--remote-debugging-port")
        if port is not None:
            try:  # with port 0 Chrome writes the port it really chose here
                with open(os.path.join(udd, "DevToolsActivePort")) as f:
                    port = f.readline().strip() or port
            except OSError:
                pass
        found[udd] = {
            "pid": int(os.path.basename(proc)),
            "exe": exe,
            # Both are reported: which one Chrome draws on depends on its ozone
            # platform choice, which a browser's command line need not show.
            # Often None: a running Chrome's /proc/<pid>/environ reads empty.
            "display": " ".join(f"{k}={env[k]}" for k in ("DISPLAY", "WAYLAND_DISPLAY") if env.get(k)) or None,
            "cdp_port": port or None,
        }
    return found


def walk(root, depth):
    """Directories holding a `Local State`, at most `depth` levels below `root` (None: any depth)."""
    try:
        device = os.stat(root).st_dev
    except OSError:
        return
    stack = [(root, 0)]
    while stack:
        path, level = stack.pop()
        if level and os.path.isfile(os.path.join(path, "Local State")):
            yield path
            continue  # a user-data-dir holds no further user-data-dirs
        if depth is not None and level >= depth:
            continue
        try:
            with os.scandir(path) as entries:
                for e in entries:
                    if (e.name not in PRUNE and e.is_dir(follow_symlinks=False)
                            and e.stat(follow_symlinks=False).st_dev == device):
                        stack.append((e.path, level + 1))
        except OSError:
            continue  # unreadable: nothing of ours in there


def user_data_dirs(running, cache=False, scan=()):
    """Every directory that looks like a Chrome user-data-dir, plus any in use right now."""
    roots = [(config_home(), 1)] + [(os.path.join(home(), rel), depth) for rel, depth in SEARCH_ROOTS]
    if cache:
        roots.append((os.path.join(home(), ".cache"), 2))
    roots += [(os.path.abspath(d), None) for d in scan]
    dirs = {os.path.realpath(d) for root, depth in roots for d in walk(root, depth)}
    dirs |= {d for d in running if not d.startswith("?")}
    return sorted(dirs)


def describe(udd, running):
    state = load_json(os.path.join(udd, "Local State")) or {}
    cache = state.get("profile", {}).get("info_cache")
    if not cache:
        # A headless browser writes no info_cache but still has profile
        # directories. An Electron app keeps Preferences at the top instead.
        cache = {os.path.basename(os.path.dirname(p)): {}
                 for pattern in ("Default", "Profile *")
                 for p in glob.glob(os.path.join(glob.escape(udd), pattern, "Preferences"))}
    if not cache:
        return None  # an Electron app, or not a browser profile directory
    open_profiles = state.get("profile", {}).get("last_active_profiles") or []
    browser = running.get(udd)
    profiles = []
    for dirname, info in sorted(cache.items()):
        prefs = load_json(os.path.join(udd, dirname, "Preferences"))
        services = (prefs or {}).get("google", {}).get("services", {})
        sync = (prefs or {}).get("sync", {})
        signed_in = info.get("user_name") or None
        if not signed_in:
            sync_on = None
        elif prefs is None:  # fall back to Local State's copy of the consent bit
            sync_on = bool(info.get("is_consented_primary_account"))
        else:
            sync_on = bool(services.get("consented_to_sync") and sync.get("has_setup_completed"))
        exists = os.path.isdir(os.path.join(udd, dirname))
        profiles.append({
            "dir": dirname,
            "name": info.get("name"),
            "exists": exists,
            "chrome_signin": signed_in,
            "sync": sync_on,
            "web_accounts": [a.get("email") for a in (prefs or {}).get("account_info", []) if a.get("email")],
            "windows_open": bool(browser) and dirname in open_profiles,
            "claude_extension": extension_state(os.path.join(udd, dirname)) if exists else {"installed": False},
        })
    return {"user_data_dir": udd, "running": browser, "profiles": profiles}


# --- the Claude in Chrome extension ------------------------------------------

def extension_state(profile_path):
    """What Chrome and the extension itself record about Claude in Chrome in one profile."""
    entry = None
    for prefs_file in ("Preferences", "Secure Preferences"):
        settings = (load_json(os.path.join(profile_path, prefs_file)) or {}).get("extensions", {}).get("settings", {})
        entry = entry or settings.get(EXTENSION_ID)
    if entry is None:
        return {"installed": False}
    reasons = entry.get("disable_reasons", [])  # a list now, a bitmask in older Chrome
    out = {
        "installed": True,
        "version": entry.get("manifest", {}).get("version") or entry.get("path", "").rpartition("/")[2].split("_")[0],
        "enabled": not reasons and entry.get("state", 1) == 1,
        "disable_reasons": reasons,
    }
    store = os.path.join(profile_path, "Local Extension Settings", EXTENSION_ID)
    if not os.path.isdir(store):
        return out

    def value(key):
        try:
            return json.loads(storage[key])
        except (KeyError, ValueError):
            return None

    storage = leveldb_dict(store)
    failure = value(b"lastAuthFailureReason")
    out.update({
        "account_uuid": value(b"accountUuid"),
        "org_uuid": (value(b"tokenOrg") or {}).get("uuid"),
        "signed_in": b"tokenScope" in storage and not failure,
        "auth_failure": failure,
        "browser_name": value(b"bridgeDisplayName") or value(b"bridgeDefaultDisplayName"),
        "device_id": value(b"bridgeDeviceId"),
    })
    return out


# An "email"/"email_address"/"emailAddress" key, then its value. The store is
# V8-serialised, not JSON: a few tag and length bytes separate key and value.
EMAIL = re.compile(rb"email(?:_address|Address)?[^A-Za-z0-9]{1,8}?([A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")


def emails_for(uuids, profile_paths):
    """{account uuid: (email, where it was found)} for as many of `uuids` as this machine can name."""
    found = {}
    account = (load_json(os.path.join(home(), ".claude.json")) or {}).get("oauthAccount") or {}
    if account.get("accountUuid") in uuids and account.get("emailAddress"):
        found[account["accountUuid"]] = (account["emailAddress"], "~/.claude.json")
    # claude.ai caches the signed-in account as JSON-like records in IndexedDB.
    # Count which email sits closest to each UUID across every profile's copy.
    votes = {u: Counter() for u in uuids if u not in found}
    needles = {u: u.encode() for u in votes}
    for profile_path in profile_paths if votes else ():
        idb = os.path.join(profile_path, "IndexedDB", "https_claude.ai_0.indexeddb.leveldb")
        if not os.path.isdir(idb):
            continue
        for _, _, _, blob in leveldb_entries(idb):
            for text in (blob, blob.replace(b"\0", b"")) if b"@\0" in blob else (blob,):  # UTF-16 strings too
                for uuid, needle in needles.items():
                    at = text.find(needle)
                    while at != -1:
                        window = text[max(0, at - 600):at + 600]
                        near = min(EMAIL.finditer(window), key=lambda m: abs(m.start() - 600), default=None)
                        if near:
                            votes[uuid][near.group(1).decode()] += 1
                        at = text.find(needle, at + 1)
    for uuid, counter in votes.items():
        if counter:
            found[uuid] = (counter.most_common(1)[0][0], "claude.ai site data")
    return found


def collect(cache=False, scan=()):
    running = running_browsers()
    dirs = [d for d in (describe(u, running) for u in user_data_dirs(running, cache, scan)) if d]
    exts = [p["claude_extension"] for d in dirs for p in d["profiles"]]
    emails = emails_for({e["account_uuid"] for e in exts if e.get("account_uuid")},
                        [os.path.join(d["user_data_dir"], p["dir"]) for d in dirs for p in d["profiles"] if p["exists"]])
    for e in exts:
        if e["installed"]:
            e["account_email"], e["email_source"] = emails.get(e.get("account_uuid"), (None, None))
    known = {d["user_data_dir"] for d in dirs}
    return {"user_data_dirs": dirs,
            "unmatched_running": {u: b for u, b in running.items() if u not in known}}


# --- output --------------------------------------------------------------------

def rows_for(report, web_logins):
    """(header, [[row, ...] per user-data-dir], number of stale profiles left out)."""
    header = ["user-data-dir", "profile", "name", "running", "windows", "chrome login", "sync",
              "claude ext", "enabled", "signed in", "claude account"]
    if web_logins:
        header.append("web logins")
    groups, stale = [], 0
    for d in report["user_data_dirs"]:
        b = d["running"]
        run = (f"pid {b['pid']}" + (f" cdp {b['cdp_port']}" if b["cdp_port"] else "")) if b else "no"
        udd = d["user_data_dir"]
        if udd == home() or udd.startswith(home() + os.sep):
            udd = "~" + udd[len(home()):]
        group = []
        for p in d["profiles"]:
            if not p["exists"]:
                stale += 1
                continue
            e = p["claude_extension"]
            uuid = e.get("account_uuid")
            row = [
                udd,
                p["dir"],
                p["name"] or "",
                run,
                ("open" if p["windows_open"] else "-") if b else "",
                p["chrome_signin"] or "-",
                {True: "on", False: "off", None: "-"}[p["sync"]],
                (e.get("version") or "?") if e["installed"] else "-",
                "" if not e["installed"] else "yes" if e["enabled"] else f"NO {e['disable_reasons']}",
                "" if not uuid else "yes" if e["signed_in"] else f"no ({e['auth_failure'] or 'no token'})",
                "" if not uuid else e["account_email"] or f"? ({uuid[:8]})",
            ]
            if web_logins:
                row.append(", ".join(p["web_accounts"]) or "-")
            group.append(row)
        if group:
            groups.append(group)
    return header, groups, stale


def width(text):
    """Terminal columns `text` occupies (wide CJK counts two, combining marks none)."""
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def print_table(header, groups):
    widths = [max(width(r[i]) for r in [header] + [r for g in groups for r in g]) for i in range(len(header))]

    def rule(left, mid, right):
        print(left + mid.join("─" * (w + 2) for w in widths) + right)

    def line(cells):
        print("│" + "│".join(" " + c + " " * (w - width(c) + 1) for c, w in zip(cells, widths)) + "│")

    rule("┌", "┬", "┐")
    line(header)
    for group in groups:
        rule("├", "┼", "┤")
        for n, row in enumerate(group):
            # Name the directory, and its one browser process, once per group.
            line(row if n == 0 else ["", *row[1:3], "", *row[4:]])
    rule("└", "┴", "┘")


def print_markdown(header, groups):
    def line(cells):
        print("| " + " | ".join(c.replace("|", "\\|") or " " for c in cells) + " |")

    line(header)
    line(["---"] * len(header))
    for group in groups:
        for row in group:
            line([f"`{row[0]}`", *row[1:]])


def main():
    summary, _, details = __doc__.partition("\n\n")
    ap = argparse.ArgumentParser(description=summary, epilog=details,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--format", choices=("table", "markdown", "json"), default="table")
    ap.add_argument("--json", action="store_const", const="json", dest="format", help="same as --format json")
    ap.add_argument("--web-logins", action="store_true", help="add a column of Google accounts signed in on the web")
    ap.add_argument("--cache", action="store_true", help="also look in ~/.cache (Playwright's throwaway profiles)")
    ap.add_argument("--scan", action="append", default=[], metavar="DIR",
                    help="also walk DIR to any depth, staying on its filesystem (repeatable)")
    args = ap.parse_args()

    report = collect(args.cache, args.scan)
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2)
        print()
        return
    header, groups, stale = rows_for(report, args.web_logins)
    (print_table if args.format == "table" else print_markdown)(header, groups)
    notes = []
    if stale:
        notes.append(f"{stale} profile(s) listed in a Local State but missing on disk were left out (see --json).")
    for u, b in report["unmatched_running"].items():
        notes.append(f"Running Chrome with no readable profile list: pid {b['pid']} {u}")
    if notes:
        print()
        print("\n".join(notes))


if __name__ == "__main__":
    main()
