# Bash tab completion

Completions for commands the distro's `bash-completion` package does not cover
(or does not cover fully). `setup.sh` (`bash_completions`) symlinks every
command-named file here into `~/.local/share/bash-completion/completions/`,
where bash-completion's lazy loader finds it the first time that command is
completed — nothing is sourced at shell startup.

| File | Completes | How it knows what to offer |
|------|-----------|----------------------------|
| `claude` | `claude` | parses `claude [sub…] --help` (cached per installed version) |
| `claude-teleport` → `claude` | `claude-teleport` | asks the binary: cobra's `__complete` |
| `claude-resume` → `claude` | `claude-resume` | session transcripts under `~/.claude/projects/` |
| `tmux` | `tmux` | upstream bash-completion script (asks `tmux list-commands`) + local value completion |
| `upstream/tmux` | — | vendored copy of upstream, refreshed by `./update-tmux` |

The rule throughout: **no option list is written down here.** Each completion
asks the installed program what it accepts, so upgrading the program upgrades
its completion. A hand-kept list was what this replaced; it had silently
fallen ~40 options behind `claude`.

## claude, claude-teleport, claude-resume

`claude` is a thin shim; all decisions are made by `bin/claude-complete`
(Python, stdlib only, ~45 ms per <kbd>Tab</kbd>).

- **Options and subcommands** come from the binary, at any depth
  (`claude plugin marketplace <Tab>`), including aliases.
- **Option values** come from the help text where it states them
  (`--permission-mode`, `--output-format`, `--effort`, `--scope`, …), in both
  `--opt value` and `--opt=value` form.
- **Things on this machine**: session ids (`claude --resume`, `claude-resume`,
  `claude-teleport`), MCP server names, installed/available plugins,
  marketplaces, background-session ids, teleport job ids, tmux sessions and
  windows, ssh hosts (`claude-teleport --to/--from/--via`), files and
  directories.
- **Descriptions** are shown beside candidates when there is more than one.
  Session ids are listed newest first with age, `live` if running, and title:

      $ claude --resume <Tab><Tab>
      70f1563b-d84c-4a02-94c3-8f8dc2c7d97f  (2m, live: tab complete)
      e302bab1-8c84-4377-a47c-8688e9207630  (19m: Review SSH command extraction PR)

  Set `CLAUDE_COMPLETE_DESCRIPTIONS=0` for bare, multi-column listings.

`claude --resume` offers only the current directory's sessions, because that
is all `claude --resume <id>` can resolve; `claude-resume` and
`claude-teleport` offer sessions from every project. The newest 50 are listed;
typing a prefix searches all of them.

The only hand-maintained data is in `bin/claude-complete`: the `MODELS` list
(no binary reports model names) and the small tables saying which argument
wants a host, a session, a path and so on.

The help cache lives in `~/.cache/claude-complete/` and is keyed by the
binary's real path and mtime, so it never needs clearing by hand.

## tmux

Upstream's script already offers every command and flag of the *running* tmux.
What it leaves as a TODO is most argument values; `tmux` here wraps the one
upstream function responsible and adds windows (`session:window`), panes,
clients, buffers, key tables, option names (`tmux set -g status-<Tab>`), hook
names, layouts and socket names. It also makes `session:window` targets
survive readline splitting words at `:`.

When the distro starts shipping `tmux` completion itself (bash-completion
≥ 2.17), the wrapper loads that one instead of `upstream/tmux`.

## Testing

    uv run python bin/test_completions.py      # or: make test

runs the engine against fixtures, then against the installed `claude` /
`claude-teleport` (checking every `--flag` their `--help` mentions is offered),
then drives the real completion functions in a real bash. Layers whose
prerequisites are missing are skipped, not failed.
