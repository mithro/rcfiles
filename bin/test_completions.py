#!/usr/bin/env python3
"""Tests for tab completion: bin/claude-complete and bash/completion/*.

Self-contained / stdlib-only — run with:
    uv run python bin/test_completions.py
Exits non-zero if any case fails; prints one line per case.

Three layers, each skipped (not failed) when what it needs is absent, so the
suite is useful both in CI (no claude, no tmux) and on a real machine:

  1. the engine against *fixture* help text      — always runs
  2. the engine against the installed binaries   — needs claude / claude-teleport
  3. real bash driving the completion functions  — needs bash-completion

Layer 2 is the one that answers "is every option offered?": it compares the
candidates with every `--flag` the binary's own --help mentions.
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASH_COMPLETION = "/usr/share/bash-completion/bash_completion"


def _load():
    loader = SourceFileLoader("claude_complete", os.path.join(HERE, "claude-complete"))
    spec = importlib.util.spec_from_loader("claude_complete", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


cc = _load()

RESULTS = {"pass": 0, "fail": 0, "skip": 0}


def check(name, ok, detail=""):
    RESULTS["pass" if ok else "fail"] += 1
    print(
        f"{'PASS' if ok else 'FAIL'}  {name}"
        + (f"\n      {detail}" if detail and not ok else "")
    )


def skip(name, why):
    RESULTS["skip"] += 1
    print(f"SKIP  {name} ({why})")


# --------------------------------------------------------------------------
# Layer 1: fixtures
# --------------------------------------------------------------------------

ROOT_HELP = """\
Usage: claude [options] [command] [prompt]

Claude Code - starts an interactive session by default

Arguments:
  prompt                                Your prompt

Options:
  --add-dir <directories...>            More directories Claude can access
  --allowedTools, --allowed-tools <tools...>
      Comma or space-separated list of tool names to allow (e.g. "Bash(git *)
      Edit")
  -d, --debug [filter]                  Enable debug mode with optional category
                                        filtering (e.g., --debug=hooks,mcp)
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
  --fallback-model <model>              Models to fall back to
                                        (comma-separated, in order). Tried again.
  -h, --help                            Display help for command
  --model <model>                       Model for the current session.
  --output-format <format>              Output format (only works with --print):
                                        "text" (default), "json" (single
                                        result), or "stream-json" (realtime
                                        streaming) (choices: "text", "json",
                                        "stream-json")
  -p, --print                           Print response and exit (useful for
                                        pipes).
  -r, --resume [value]                  Resume a conversation by session ID
  --settings <file-or-json>             Settings file or JSON string
  --plugin-dir <path>                   Load a plugin from a directory
                                        (repeatable: --plugin-dir A --plugin-dir
                                        B.zip) (default: [])

Commands:
  agents [options]                      Manage background agents
  attach <id|name>                      Open a background session
  install [options] [target]            Install the Claude Code native build.
  mcp                                   Configure and manage MCP servers
  plugin|plugins                        Manage Claude Code plugins
  update|upgrade                        Check for updates
"""

MCP_HELP = """\
Usage: claude mcp [options] [command]

Options:
  -h, --help                            Display help for command

Commands:
  add [options] <name> <commandOrUrl> [args...]
      Add an MCP server
  get <name>                            Get details about an MCP server.
  help [command]                        display help for command
"""

MCP_ADD_HELP = """\
Usage: claude mcp add [options] <name> <commandOrUrl> [args...]

Examples:
  # Add HTTP server:
  claude mcp add --transport http sentry https://mcp.sentry.dev/mcp

Options:
  -e, --env <env...>           Set environment variables (e.g. -e KEY=value)
  -s, --scope <scope>          Configuration scope (local, user, or project)
                               (default: "local")
  -t, --transport <transport>  Transport type (stdio, sse, http). Defaults to
                               stdio.
"""

AGENTS_HELP = """\
Usage: claude agents [options]

Options:
  --effort <level>                      Default effort level for sessions
                                        dispatched from agent view
  --json                                Print active sessions
"""


FIXTURE_PAGES = {
    (): ROOT_HELP,
    ("mcp",): MCP_HELP,
    ("mcp", "add"): MCP_ADD_HELP,
    ("agents",): AGENTS_HELP,
}


class FakeHelp:
    """Stands in for ClaudeHelp: fixture text instead of running claude."""

    def get(self, chain):
        return cc.parse_help(FIXTURE_PAGES.get(tuple(chain), ""))


def claude(*words):
    """Complete the last word of `claude <words>`; return (values, directives)."""
    line = ["claude", *words]
    reply = cc.complete_claude(line, len(line) - 1, "/nonexistent", FakeHelp())
    return [v for v, _ in reply.items], reply.directives


def test_fixtures():
    opts, cmds = cc.parse_help(ROOT_HELP)
    names = [n for o in opts for n in o.names]
    check(
        "parse: aliased option on a wrapped line",
        "--allowed-tools" in names and "--allowedTools" in names,
    )
    check("parse: short + long", "-r" in names and "--resume" in names)
    check("parse: command aliases", ["plugin", "plugins"] in [c.names for c in cmds])
    by = {o.names[-1]: o for o in opts}
    check(
        "choices: exact (choices: ...)",
        by["--output-format"].choices == ["text", "json", "stream-json"],
    )
    check(
        "choices: prose list",
        by["--effort"].choices == ["low", "medium", "high", "xhigh", "max"],
    )
    check(
        "choices: prose with spaces is not a list", by["--fallback-model"].choices == []
    )
    check("choices: (default: []) is not a list", by["--plugin-dir"].choices == [])
    check("choices: flags never have any", by["--print"].choices == [])
    add_opts, _ = cc.parse_help(MCP_ADD_HELP)
    scope = next(o for o in add_opts if "--scope" in o.names)
    check("choices: 'a, b, or c'", scope.choices == ["local", "user", "project"])
    check(
        "parse: Examples: section is not options",
        all(o.names[0].startswith("-") for o in add_opts) and len(add_opts) == 3,
    )

    v, _ = claude("")
    check(
        "root: subcommands incl. aliases",
        {"mcp", "plugin", "plugins", "upgrade"} <= set(v),
        v,
    )
    v, _ = claude("--")
    check("root: -- lists long options only", "--resume" in v and "-r" not in v, v)
    v, _ = claude("-")
    check("root: - lists short options too", "-r" in v and "--resume" in v, v)
    check(
        "value: choices",
        claude("--output-format", "")[0] == ["text", "json", "stream-json"],
    )
    check("value: --opt=value form", claude("--output-format=j")[0] == ["json"])
    check("value: short option", claude("--effort", "x")[0] == ["xhigh"])
    check("value: models", "opus" in claude("--model", "")[0])
    check("value: path-like arg -> @files", claude("--settings", "")[1] == ["@files"])
    check("value: dir-like arg -> @dirs", claude("--add-dir", "")[1] == ["@dirs"])
    check("variadic: keeps taking values", claude("--add-dir", "a", "")[1] == ["@dirs"])
    check(
        "variadic: ends at the next option",
        "opus" in claude("--add-dir", "a", "--model", "")[0],
    )
    check(
        "optional arg: a following option is not its value",
        claude("--debug", "--eff")[0] == ["--effort"],
    )
    check("flag: does not swallow the next word", "mcp" in claude("-p", "")[0])
    v, _ = claude("mcp", "")
    check("subcommand: nested commands", v == ["add", "get", "help"], v)
    check(
        "subcommand: own options only",
        claude("mcp", "add", "--")[0] == ["--env", "--scope", "--transport"],
    )
    check(
        "subcommand: option value",
        claude("mcp", "add", "-t", "")[0] == ["stdio", "sse", "http"],
    )
    check(
        "subcommand: borrows root choices",
        claude("agents", "--effort", "")[0]
        == ["low", "medium", "high", "xhigh", "max"],
    )
    check("subcommand: help <command>", claude("mcp", "help", "")[0] == ["add", "get"])
    check(
        "positional: install target", claude("install", "")[0] == ["stable", "latest"]
    )
    check("after --: no options", claude("--", "--")[0] == [])

    r = cc.Reply("")
    r.add([("aaa", "first"), ("b", "second")])
    check(
        "render: descriptions when several",
        r.render(80) == ["aaa  (first)", "b    (second)"],
        r.render(80),
    )
    check(
        "render: descriptions can be turned off",
        r.render(80, describe=False) == ["aaa", "b"],
    )
    r = cc.Reply("a")
    r.add([("aaa", "first"), ("b", "second")])
    check(
        "render: a single candidate is the bare value",
        r.render(80) == ["aaa"],
        r.render(80),
    )
    r = cc.Reply("")
    r.add([("x" * 10, "y" * 200), ("z", "")])
    check(
        "render: clipped to the terminal width",
        all(len(ln) < 40 for ln in r.render(40)),
        r.render(40),
    )

    check(
        "munge: every non-alphanumeric",
        cc.munge("/home/t/a.b/.w_x") == "-home-t-a-b--w-x",
    )


def test_sessions():
    """Session listing against a throwaway CLAUDE_CONFIG_DIR."""
    old = cc.CONFIG_DIR
    with tempfile.TemporaryDirectory(dir=REPO) as tmp:
        cc.CONFIG_DIR = tmp
        try:
            a, b = (
                "aaaaaaaa-0000-4000-8000-000000000001",
                "bbbbbbbb-0000-4000-8000-000000000002",
            )
            for proj, sid, mtime, body in (
                ("-p1", a, 1000, '{"type":"ai-title","aiTitle":"older one"}\n'),
                (
                    "-p2",
                    b,
                    2000,
                    "x" * 100000
                    + '\n{"type":"custom-title","customTitle":"new \\"one\\""}\n',
                ),
            ):
                os.makedirs(os.path.join(tmp, "projects", proj), exist_ok=True)
                path = os.path.join(tmp, "projects", proj, sid + ".jsonl")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(body)
                os.utime(path, (mtime, mtime))
            with open(
                os.path.join(tmp, "projects", "-p1", "not-a-session.jsonl"),
                "w",
                encoding="utf-8",
            ) as fh:
                fh.write("{}")
            got = cc.sessions("")
            check(
                "sessions: newest first, all projects",
                [s for s, _ in got] == [b, a],
                got,
            )
            check(
                "sessions: title from the transcript tail",
                got[0][1].endswith(': new "one"'),
                got[0][1],
            )
            check(
                "sessions: one project only",
                [s for s, _ in cc.sessions("", "-p1")] == [a],
            )
            check("sessions: prefix", [s for s, _ in cc.sessions("bbbb")] == [b])
            r = cc.complete_resume(["claude-resume", ""], 1)
            check(
                "claude-resume: offers sessions unsorted",
                r.directives == ["@nosort"] and len(r.items) == 2,
            )
            r = cc.complete_resume(["claude-resume", a, ""], 2)
            check("claude-resume: takes one argument", r.items == [])
        finally:
            cc.CONFIG_DIR = old


# --------------------------------------------------------------------------
# Layer 2: the installed binaries
# --------------------------------------------------------------------------


def help_flags(text):
    return set(re.findall(r"(?<![\w-])--[a-z][\w-]*", text))


def test_live_claude():
    binary = shutil.which("claude")
    if not binary:
        return skip("live claude", "claude not installed")
    hlp = cc.ClaudeHelp(binary)
    root = hlp.text(())
    opts, cmds = hlp.get(())
    section = root[root.index("\nOptions:") : root.index("\nCommands:")]
    declared = set(
        re.findall(r"^  (?:-\w, )?(--[\w-]+)|, (--[\w-]+)", section, re.MULTILINE)
    )
    declared = {a or b for a, b in declared}
    reply = cc.complete_claude(["claude", "--"], 1, os.getcwd(), hlp)
    offered = {v for v, _ in reply.items}
    check(
        f"live claude: all {len(declared)} long options offered",
        declared <= offered,
        sorted(declared - offered),
    )
    check(
        "live claude: nothing offered that --help lacks",
        offered <= help_flags(root),
        sorted(offered - help_flags(root)),
    )
    reply = cc.complete_claude(["claude", ""], 1, os.getcwd(), hlp)
    offered = {v for v, _ in reply.items}
    listed = {n for c in cmds for n in c.names if len(n) > 1}
    check(
        f"live claude: all {len(listed)} subcommands offered",
        listed and listed <= offered,
        sorted(listed - offered),
    )
    # every subcommand's help page must parse into something or be option-less
    bad = []
    for c in cmds:
        text = hlp.text((c.names[0],))
        sub_opts, _ = hlp.get((c.names[0],))
        if "\nOptions:" in text and not sub_opts:
            bad.append(c.names[0])
    check("live claude: every subcommand help page parses", not bad, bad)
    multi = [o.names[-1] for o in opts if o.arg and len(o.choices) > 1]
    check(
        "live claude: value choices found",
        {"--permission-mode", "--output-format", "--effort"} <= set(multi),
        multi,
    )


def test_live_teleport():
    binary = shutil.which("claude-teleport")
    if not binary:
        return skip("live claude-teleport", "claude-teleport not installed")
    cobra = cc.Cobra(binary)

    def tp(*words):
        line = ["claude-teleport", *words]
        r = cc.complete_teleport(line, len(line) - 1, cobra)
        return [v for v, _ in r.items], r.directives

    # (--teleport is claude's own flag, which the help text only warns about)
    declared = help_flags(cc.run([binary, "--help"])) - {"--teleport"}
    offered = set(tp("--")[0])
    for sub in ("abandon", "list", "compare-config", "placeholder"):
        offered |= set(tp(sub, "--")[0])
    check(
        f"live teleport: all {len(declared)} documented flags offered",
        declared <= offered,
        sorted(declared - offered),
    )
    check("live teleport: --to/--from aliases", {"--to", "--from"} <= set(tp("--")[0]))
    check(
        "live teleport: alias found by prefix", tp("--fr")[0] == ["--from"], tp("--fr")
    )
    check("live teleport: short flags", "-v" in tp("-")[0])
    check("live teleport: subcommands", {"list", "status", "doctor"} <= set(tp("")[0]))
    check("live teleport: host flag -> @hosts", tp("--to", "")[1] == ["@hosts"])
    check(
        "live teleport: alias takes a value",
        tp("--via", "x", "--from", "")[1] == ["@hosts"],
    )
    check(
        "live teleport: --state values",
        tp("--state", "")[0] == ["auto", "running", "suspended", "idle"],
        tp("--state", ""),
    )
    check("live teleport: --state=prefix", tp("--state=r")[0] == ["running"])
    check("live teleport: bool flag takes no value", "list" in tp("--dry-run", "")[0])
    check(
        "live teleport: subcommand flags",
        "--host" in tp("list", "--")[0] and "--state" not in tp("list", "--")[0],
    )
    check("live teleport: doctor <host>", tp("doctor", "")[1] == ["@hosts"])
    check("live teleport: -o is nospace", "@nospace" in tp("-o", "")[1])


# --------------------------------------------------------------------------
# Layer 3: real bash
# --------------------------------------------------------------------------

BASH_DRIVER = r"""
source "$BC"
export PATH="$REPO/bin:$PATH"
source "$REPO/bash/completion/$FILE"
compopt() { :; }  # only legal while readline is driving a completion
COMP_WORDS=("$@")
COMP_CWORD=$(( $# - 1 ))
COMP_LINE=$LINE
COMP_POINT=${#COMP_LINE}
COMP_TYPE=9
COMP_KEY=9
spec=$(complete -p "$1") || exit 3
[[ $spec =~ -F\ ([^ ]+) ]] || exit 4
"${BASH_REMATCH[1]}" "$1" "${COMP_WORDS[COMP_CWORD]}" "${COMP_WORDS[COMP_CWORD-1]}"
printf '%s\n' "${COMPREPLY[@]}"
"""


def bash_complete(file, *words, cwd=None, line=None):
    """Run the real completion function for `words` in a real bash; the last
    word is the one being completed. COMP_WORDS is given pre-split the way
    readline would split it; pass `line` when that differs from joining the
    words with spaces (`--effort=x` is the three words --effort = x)."""
    env = dict(
        os.environ,
        BC=BASH_COMPLETION,
        REPO=REPO,
        FILE=file,
        COLUMNS="200",
        LINE=line or " ".join(words),
    )
    p = subprocess.run(
        ["bash", "--norc", "--noprofile", "-c", BASH_DRIVER, "bash", *words],
        capture_output=True, text=True, timeout=60, env=env, cwd=cwd, check=False,
    )  # fmt: skip
    if p.returncode != 0 or p.stderr.strip():
        return [f"<rc={p.returncode} stderr={p.stderr.strip()[:300]}>"]
    return [ln for ln in p.stdout.splitlines() if ln]


def firsts(lines):
    return [ln.split()[0] for ln in lines]


def test_bash():
    if not os.path.exists(BASH_COMPLETION):
        return skip("bash layer", "bash-completion not installed")

    with tempfile.TemporaryDirectory(dir=REPO) as tmp:
        os.mkdir(os.path.join(tmp, "subdir"))
        open(os.path.join(tmp, "file.json"), "w").close()

        if shutil.which("claude"):
            got = bash_complete("claude", "claude", "--permission-m")
            check(
                "bash claude: single match is the bare option",
                got == ["--permission-mode"],
                got,
            )
            got = bash_complete("claude", "claude", "--perm")
            check(
                "bash claude: several matches carry descriptions",
                firsts(got) == ["--permission-mode", "--permission-prompts"]
                and "(" in got[0],
                got,
            )
            got = bash_complete("claude", "claude", "--effort", "")
            check("bash claude: option value", "xhigh" in got, got)
            # readline splits `--effort=x` into three words: --effort = x
            got = bash_complete(
                "claude", "claude", "--effort", "=", "x", line="claude --effort=x"
            )
            check(
                "bash claude: --opt=value replaces only the value",
                got == ["xhigh"],
                got,
            )
            got = bash_complete("claude", "claude", "--add-dir", "", cwd=tmp)
            check("bash claude: directory argument", got == ["subdir"], got)
            got = bash_complete("claude", "claude", "--settings", "", cwd=tmp)
            check(
                "bash claude: file argument",
                sorted(got) == ["file.json", "subdir"],
                got,
            )
            got = bash_complete("claude", "claude", "mcp", "")
            check(
                "bash claude: subcommands",
                {"add", "list", "remove"} <= set(firsts(got)),
                got,
            )
        else:
            skip("bash claude", "claude not installed")

        if shutil.which("claude-teleport"):
            got = bash_complete("claude-teleport", "claude-teleport", "--stat")
            check("bash teleport: loads via its symlink", got == ["--state"], got)
            got = bash_complete("claude-teleport", "claude-teleport", "--state", "sus")
            check("bash teleport: flag value", got == ["suspended"], got)
            got = bash_complete("claude-teleport", "claude-teleport", "--to", "localh")
            check(
                "bash teleport: ssh host completion runs",
                not any(g.startswith("<rc=") for g in got),
                got,
            )
        else:
            skip("bash teleport", "claude-teleport not installed")

        got = bash_complete("claude-resume", "claude-resume", "zzzz-no-such")
        check("bash claude-resume: loads via its symlink", got == [], got)

    # Upstream's tmux completion needs the bash-completion >= 2.12 API.
    with open(BASH_COMPLETION, encoding="utf-8") as fh:
        modern = "_comp_initialize" in fh.read()
    if not modern:
        skip("bash tmux", "bash-completion older than 2.12")
    elif (
        shutil.which("tmux")
        and subprocess.run(
            ["tmux", "list-commands"], capture_output=True, check=False
        ).returncode
        == 0
    ):
        cmds = subprocess.run(
            ["tmux", "list-commands", "-F", "#{command_list_name}"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        got = bash_complete("tmux", "tmux", "")
        check(
            f"bash tmux: all {len(cmds)} commands offered",
            set(cmds) <= set(got),
            sorted(set(cmds) - set(got))[:10],
        )
        got = bash_complete("tmux", "tmux", "-")
        check("bash tmux: global options", {"-L", "-S", "-f", "-V"} <= set(got), got)
        got = bash_complete("tmux", "tmux", "new-session", "-")
        usage = subprocess.run(
            ["tmux", "list-commands", "new-session"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        want = {"-" + c for grp in re.findall(r"\[-(\w+)\]", usage) for c in grp} | set(
            re.findall(r"\[(-\w) ", usage)
        )
        check(
            f"bash tmux: all {len(want)} new-session options",
            want <= set(got),
            sorted(want - set(got)),
        )
        got = bash_complete("tmux", "tmux", "neww", "-")
        usage = subprocess.run(
            ["tmux", "list-commands", "new-window"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        want = {"-" + c for grp in re.findall(r"\[-(\w+)\]", usage) for c in grp} | set(
            re.findall(r"\[(-\w) ", usage)
        )
        check(
            "bash tmux: options after a command alias (neww)",
            want and want <= set(got),
            sorted(want - set(got)),
        )

        # Values upstream leaves as a TODO, filled in by bash/completion/tmux.
        def tmux(*args):
            return subprocess.run(
                ["tmux", *args], capture_output=True, text=True, check=False
            ).stdout.split("\n")[:-1]

        sess = tmux("list-sessions", "-F", "#{session_name}")
        plain = [x for x in sess if re.fullmatch(r"[\w-]+", x)]
        got = bash_complete("tmux", "tmux", "attach", "-t", "")
        check("bash tmux: target-session", set(sess) <= set(got), got[:5])
        if plain:
            name = plain[0]
            wins = tmux("list-windows", "-t", "=" + name, "-F", "#{window_index}")
            got = bash_complete(
                "tmux",
                "tmux",
                "select-window",
                "-t",
                name[:-1] if len(name) > 1 else name,
            )
            check(
                "bash tmux: target-window offers session:window",
                f"{name}:{wins[0]}" in got,
                got[:5],
            )
            # readline splits `-t name:` at the colon; only the part after it is replaced
            got = bash_complete(
                "tmux",
                "tmux",
                "select-window",
                "-t",
                name,
                ":",
                "",
                line=f"tmux select-window -t {name}:",
            )
            check(
                "bash tmux: target-window after the colon",
                got == wins,
                (got[:5], wins[:5]),
            )
            got = bash_complete(
                "tmux",
                "tmux",
                "select-pane",
                "-t",
                name,
                ":",
                wins[0] + ".",
                line=f"tmux select-pane -t {name}:{wins[0]}.",
            )
            check(
                "bash tmux: target-pane",
                got and all(g.startswith(wins[0] + ".") for g in got),
                got[:5],
            )
            got = bash_complete(
                "tmux",
                "tmux",
                "kill-window",
                "-t",
                name,
                ":",
                wins[0],
                "-",
                line=f"tmux kill-window -t {name}:{wins[0]} -",
            )
            check(
                "bash tmux: options still parse after a colon target", "-a" in got, got
            )
        got = bash_complete("tmux", "tmux", "set-option", "-g", "status-")
        check(
            "bash tmux: option names",
            {"status-left", "status-right"} <= set(got),
            got[:5],
        )
        got = bash_complete("tmux", "tmux", "select-layout", "")
        check(
            "bash tmux: layout names", "tiled" in got and "even-horizontal" in got, got
        )
        got = bash_complete("tmux", "tmux", "bind-key", "-T", "")
        check("bash tmux: key tables", {"root", "prefix"} <= set(got), got)
        got = bash_complete("tmux", "tmux", "source-file", "Makef", cwd=REPO)
        check(
            "bash tmux: upstream's own values still work (file)",
            got == ["Makefile"],
            got,
        )
    else:
        skip("bash tmux", "no tmux server to ask")


if __name__ == "__main__":
    test_fixtures()
    test_sessions()
    test_live_claude()
    test_live_teleport()
    test_bash()
    print(
        f"\n{RESULTS['pass']} passed, {RESULTS['fail']} failed, {RESULTS['skip']} skipped"
    )
    sys.exit(1 if RESULTS["fail"] else 0)
