# tmux: TPM + resurrect/continuum session persistence

- **Date:** 2026-06-11
- **Status:** Approved (brainstormed with Tim)
- **Scope:** `tmux/`, `setup.sh`, `.gitmodules`

## Problem

tmux sessions are lost whenever the tmux server dies — reboots, and
notably OOM kills on the desktop VM (Renode/Mono previously took out the
whole slice). There is currently no plugin infrastructure in the tmux
config at all; vim already vendors plugins as git submodules, but tmux
has nothing equivalent.

## Requirements

1. Plugin management via TPM (tmux plugin manager), deployed to **all
   rcfiles hosts** through `setup.sh`.
2. Session persistence with **full-fidelity saves**: session/window/pane
   layout, working directories, whitelisted running programs, and pane
   scrollback contents.
3. **Autosave** every 15 minutes via tmux-continuum; **restore stays
   manual** (`prefix+Ctrl-r`). `@continuum-restore` is deliberately not
   set — no surprise restores of stale state on clean starts.
4. Program restore whitelist: resurrect defaults **plus `ssh`, `mosh`
   (process name `mosh-client`), and `claude`**.
5. A host with no network or uninitialised submodules must still get a
   working (plugin-less) tmux.

## Design

### 1. Repo structure

One new git submodule:

```
tmux/plugins/tpm  ->  https://github.com/tmux-plugins/tpm
```

- Consistent with the existing `vim/bundle/*` vendoring convention;
  `setup.sh` already runs `git submodule update --init --recursive`, so
  TPM arrives pinned on every host with no extra network step at tmux
  start time.
- **Only TPM is vendored.** resurrect and continuum are managed *by* TPM
  and cloned into `~/.tmux/plugins/` (outside the repo) via
  `TMUX_PLUGIN_MANAGER_PATH`. The rcfiles working tree stays clean — no
  `.gitignore` entries for plugin clones needed.
- `linkit()` is unaffected by the new directory: its loop only processes
  plain files (`[ -f ]`) directly under `tmux/`, so `tmux/plugins/` is
  invisible to it.

### 2. tmux.conf additions (appended at end of base `tmux/tmux.conf`)

```tmux
# ── Plugins (managed by TPM, vendored at ~/rcfiles/tmux/plugins/tpm) ──
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'

# Save full state: pane scrollback contents...
set -g @resurrect-capture-pane-contents 'on'
# ...and relaunch these programs on restore (in addition to the
# conservative defaults: vi vim nvim emacs man less more tail top htop).
set -g @resurrect-processes 'ssh mosh-client claude'

# Autosave every 15 min. Restore is MANUAL (prefix+Ctrl-r);
# @continuum-restore is deliberately not set.
set -g @continuum-save-interval '15'

# Plugins are cloned outside the repo; TPM itself is a pinned submodule.
set-environment -g TMUX_PLUGIN_MANAGER_PATH "$HOME/.tmux/plugins/"
if-shell "test -x ~/rcfiles/tmux/plugins/tpm/tpm" \
    "run-shell ~/rcfiles/tmux/plugins/tpm/tpm"
```

Decisions baked into this block:

- **No `set -g @plugin 'tmux-plugins/tpm'` line.** Listing tpm would
  make TPM clone a second, unpinned copy of itself into
  `~/.tmux/plugins/`. The submodule is the single source of truth for
  TPM's version.
- **`if-shell` guard** on the `run-shell` line: a host where submodules
  were never initialised still gets a fully working plain tmux
  (requirement 5).
- Key bindings are plugin defaults: `prefix+Ctrl-s` save,
  `prefix+Ctrl-r` restore, `prefix+I` install plugins, `prefix+U`
  update plugins.
- **This block is deployed via `tmux/tmux.conf-postfix`, not the base
  `tmux.conf`.** linkit appends the postfix after host parts, so the
  `run-shell` loader runs last and continuum wraps the FINAL
  `status-right` (see §4). The block's *location* — not a "keep this
  last" comment — is what guarantees ordering.

### 3. setup.sh changes

- New `tmux_plugins` function, called after `linkit tmux` (headless
  `bin/install_plugins` starts a tmux server and sources `~/.tmux.conf`,
  so the config — including `TMUX_PLUGIN_MANAGER_PATH` — must already be
  deployed): runs `~/rcfiles/tmux/plugins/tpm/bin/install_plugins` so
  resurrect/continuum exist before the first interactive tmux launch. Wrapped so a
  network failure prints a warning instead of killing the `set -e`
  script (same guard pattern as the recent systemd changes,
  `21a6627`). On failure, plugins can later be installed interactively
  with `prefix+I`.
- **Targeted `linkit` fix:** the suffix loop appends a part file once
  per matching suffix, and on hosts where `$BASE_DOMAIN == $DOMAIN`
  (e.g. `mithis.com`) the same part is appended **twice** — the
  currently deployed `~/.tmux.conf` on this machine exhibits the
  duplication. Fix: dedupe **by path** — skip a part file whose path has
  already been appended (the bug is the same path appearing twice in the
  suffix list). This directly affects the file this project regenerates.
- **`linkit` postfix support:** add an optional `<base>-postfix` file
  appended after the host-specific parts (generated order: base → host
  parts → postfix). Generic feature; used here so the TPM loader in
  `tmux/tmux.conf-postfix` runs last (see §4).

### 4. Host-override / continuum ordering (postfix mechanism)

continuum's autosave works by prepending `#(continuum_save.sh)` to
`status-right` **once, at plugin-load time** (`add_resurrect_save_interpolation`
in `continuum.tmux`; one-shot global `set-option`, no hook/timer). So
whatever sets `status-right` LAST wins: if a host part's
`set -g status-right` runs after the TPM loader, it silently wipes
continuum's hook and autosave never fires.

Verified empirically on tmux 3.5a (isolated socket, continuum stand-in):
a `run-shell` loader executes synchronously during config parse, BEFORE
later lines — so the original assumption ("run-shell runs after the whole
file is parsed") is FALSE. `linkit` appends host parts after the base
file, so a loader placed in the base file loads *before* the host
`status-right` override → hook lost on every `*.mithis.com` host.

**Fix — `linkit` postfix support.** `linkit` gains an optional
`<base>-postfix` file appended LAST, after all host-specific parts
(generated order: base → host parts → postfix). The TPM plugin block
(options + guarded `run-shell` loader) lives in `tmux/tmux.conf-postfix`,
so in the generated `~/.tmux.conf` the loader runs after the host
`status-right` override; continuum reads the FINAL `status-right` and its
hook survives. Host parts stay free to override `status-right`/colours
exactly as before. This is a generic `linkit` feature (any config may
have a postfix), not a tmux-specific hack. The test plan verifies
`status-right` contains `continuum_save.sh` on a host *with* overrides.

### 5. Testing (on this machine — has overrides, worst case)

1. Re-run `setup.sh`; generated `~/.tmux.conf` contains the host
   snippet exactly once (linkit fix verified).
2. Start a fresh tmux server; `~/.tmux/plugins/` contains resurrect and
   continuum; no error output.
3. `tmux show -g status-right` shows continuum's wrapper
   (`continuum_save.sh`) around the host-specific status string —
   ordering guaranteed by the postfix file loading after host parts.
4. Manual save (`prefix+Ctrl-s`) writes a save file under resurrect's
   save directory; after one autosave interval a newer save appears.
5. Kill the tmux server, restart, `prefix+Ctrl-r`: layout, working
   dirs, scrollback contents, and a whitelisted program (e.g. an ssh
   session) come back.

## Risks / verification items for implementation

- **`mosh` restore is approximate.** The pane's actual process is
  `mosh-client` with ephemeral args (session key in env), so a raw
  re-run may fail after the remote side is gone. If so, fall back to
  resurrect's arrow syntax (`'prog->command to run'`) or drop mosh from
  the whitelist; verify during testing.
- **`claude` process name** may appear as `node`/script path rather
  than `claude` in the saved command; may need resurrect's `~` (contains)
  matcher. Verify during testing.
- **Resurrect save directory** default differs across versions
  (`~/.tmux/resurrect` vs `~/.local/share/tmux/resurrect`); confirm the
  actual path during testing, and set `@resurrect-dir` explicitly if it
  matters for backups.
- Scrollback capture depth (visible screen vs full history) to be
  confirmed during testing; document the observed behaviour.

## Out of scope

- Auto-restore on server start (`@continuum-restore`) — explicitly
  rejected.
- Vendoring resurrect/continuum themselves as submodules (approach C —
  rejected in favour of TPM workflow).
- Any other tmux plugins.
