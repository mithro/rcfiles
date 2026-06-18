# tmux TPM + resurrect/continuum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TPM (vendored as a git submodule) with tmux-resurrect + tmux-continuum so tmux sessions survive server death (reboot/OOM), with 15-minute autosave and strictly manual restore.

**Architecture:** TPM is pinned at `tmux/plugins/tpm` (same convention as `vim/bundle/*`); the plugins TPM manages are cloned outside the repo to `~/.tmux/plugins/` via `TMUX_PLUGIN_MANAGER_PATH`. `setup.sh` gains a headless plugin-install step and a targeted fix for `linkit()` appending duplicate host parts. Spec: `docs/superpowers/specs/2026-06-11-tmux-tpm-resurrect-design.md`.

**Tech Stack:** bash (setup.sh, tab-indented, must pass `shellcheck -S warning` per CI), tmux 3.5a config, git submodules, Python via `uv run` for the test driver.

**Working location:** Isolated git worktree on branch `tmux-tpm-resurrect`, created via the `superpowers:using-git-worktrees` skill. Begin every task with:

```bash
export WORKTREE=/home/tim/github/mithro/rcfiles/.worktrees/tmux-tpm-resurrect
cd "$WORKTREE"
```

All development, edits, and commits happen **here** — never in the base worktree (`~/rcfiles` → `~/github/mithro/rcfiles`).

**Path rules (important — two kinds of `~/rcfiles` appear in this plan):**
- In *shell commands*, use `$WORKTREE`. Anywhere an earlier draft said `~/rcfiles`/`cd ~/rcfiles`, it means the worktree. (`~/rcfiles` is a symlink to the *base* worktree; running build commands there would violate the isolation rule.)
- Inside *committed file contents* — the `tmux/tmux.conf` plugin block (its comments, `set-environment … '~/.tmux/plugins/'`, and the `run-shell ~/rcfiles/tmux/plugins/tpm/tpm` + `if-shell` guard) — the literal `~`/`~/rcfiles` paths are the **production deploy paths** and are correct as written. Do **not** rewrite them to `$WORKTREE`.
- The worktree checked out a pristine `b33062d`, so `setup.sh` here has **no** uncommitted edits (the base worktree's `claude()`/`git*` changes are absent). Still `git add` specific paths, never `git add -A`.

**Live deployment is deferred to Task 7.** Tasks 1–6 are repo changes plus *hermetic* verification confined to `$WORKTREE/tmp` — they never touch `~/.tmux.conf`, the running tmux server, or `~/.tmux/plugins`. The on-machine deploy + first real save run only after the branch is integrated, against `~/rcfiles`.

> **Execution note:** this machine's PreToolUse hooks deny `2>/dev/null` (stderr→null) and have denied `;`-separated compound commands; `&&` chains and separate invocations work. Split commands rather than stalling on a denial.

---

### Task 1: Fix linkit() duplicate host-part append (TDD)

The bug: `linkit()` iterates suffixes `-$BASE_DOMAIN`, `-$DOMAIN`, `-$HOSTNAME`; on `*.mithis.com` hosts `BASE_DOMAIN == DOMAIN == mithis.com`, so `tmux.conf-mithis.com` is appended twice (the deployed `~/.tmux.conf` on this machine shows the duplication). Fix: dedupe **by path**.

**Files:**
- Modify: `setup.sh` (the `linkit()` function)
- Test: `tmp/test_linkit_dedupe.py` (repo-local tmp/, already gitignored; deleted in Task 7)

- [ ] **Step 1: Write the failing test**

Create `$WORKTREE/tmp/test_linkit_dedupe.py` (run `mkdir -p "$WORKTREE/tmp"` first; never use /tmp):

```python
#!/usr/bin/env python3
"""Verify linkit() appends a duplicated host-part suffix only once.

Reproduces the BASE_DOMAIN == DOMAIN case (any *.mithis.com host) where
setup.sh's linkit() appended tmux.conf-mithis.com twice to the
generated ~/.tmux.conf.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Resolve relative to THIS file so the test targets the WORKTREE's
# setup.sh (the file under edit) -- NOT ~/rcfiles, which is a symlink to
# the base worktree whose setup.sh is the unfixed copy.
REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SH = REPO_ROOT / "setup.sh"
TMP_ROOT = REPO_ROOT / "tmp"  # repo-local, gitignored; never /tmp


def main() -> int:
    match = re.search(
        r"^function linkit \{.*?^\}", SETUP_SH.read_text(), re.M | re.S
    )
    if not match:
        print("FAIL: could not extract linkit() from setup.sh")
        return 1

    with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmpdir:
        home = Path(tmpdir) / "home"
        tmux_dir = Path(tmpdir) / "rcfiles" / "tmux"
        home.mkdir()
        tmux_dir.mkdir(parents=True)
        (tmux_dir / "tmux.conf").write_text("# base config\n")
        (tmux_dir / "tmux.conf-mithis.com").write_text("# host part\n")

        script = "\n".join(
            [
                f"HOME={home}",
                f"RCFILES={tmux_dir.parent}",
                "BASE_DOMAIN=mithis.com",
                "DOMAIN=mithis.com",
                "HOSTNAME=desktop.mithis.com",
                match.group(0),
                "linkit tmux",
            ]
        )
        subprocess.run(["bash", "-c", script], check=True)

        generated = (home / ".tmux.conf").read_text()
        count = generated.count("# host part")

    print(f"host part appended {count} time(s); expected 1")
    return 0 if count == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "$WORKTREE" && uv run python tmp/test_linkit_dedupe.py`
Expected: prints `host part appended 2 time(s); expected 1`, exit code 1 (verify with `echo $?`).

- [ ] **Step 3: Apply the fix**

In `setup.sh`, inside `linkit()`, replace this block (TAB indentation — file uses `noet ts=4`):

```bash
		TMP=~/.$F.tmp
		for FILE_PART in "$FP-$BASE_DOMAIN" "$FP-$DOMAIN" "$FP-$HOSTNAME"; do
			if [ -f $FILE_PART ]; then
				echo $FILE_PART "->" ~/.$F
				cat $FILE_PART >> $TMP
			fi
		done
```

with:

```bash
		TMP=~/.$F.tmp
		# BASE_DOMAIN/DOMAIN/HOSTNAME can expand to the same suffix (e.g.
		# BASE_DOMAIN == DOMAIN == mithis.com); append each part file once.
		SEEN_PARTS=" "
		for FILE_PART in "$FP-$BASE_DOMAIN" "$FP-$DOMAIN" "$FP-$HOSTNAME"; do
			case "$SEEN_PARTS" in
				*" $FILE_PART "*) continue ;;
			esac
			SEEN_PARTS="$SEEN_PARTS$FILE_PART "
			if [ -f $FILE_PART ]; then
				echo $FILE_PART "->" ~/.$F
				cat $FILE_PART >> $TMP
			fi
		done
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "$WORKTREE" && uv run python tmp/test_linkit_dedupe.py`
Expected: `host part appended 1 time(s); expected 1`, exit code 0.

- [ ] **Step 5: Lint**

Run: `bash -n "$WORKTREE/setup.sh" && shellcheck -S warning "$WORKTREE/setup.sh"`
Expected: no output from `bash -n`; shellcheck clean. If shellcheck flags anything, confirm it is pre-existing on master (not introduced by the fix): `git -C "$WORKTREE" show master:setup.sh | shellcheck -S warning -`.

- [ ] **Step 6: Commit**

```bash
cd "$WORKTREE" && git add setup.sh && git commit -m "setup.sh: Dedupe linkit host parts when domain suffixes coincide"
```

---

### Task 2: Vendor TPM as a git submodule

**Files:**
- Create: `tmux/plugins/tpm` (submodule)
- Modify: `.gitmodules` (automatic via `git submodule add`)
- Modify: `.github/workflows/quality-check.yml` (shellcheck `ignore_paths`)

> Submodule-in-worktree note: `git submodule add` run from `$WORKTREE` records the submodule on this branch and stores its git dir under the main repo's `.git/modules/`. That is fine. If git complains that the path already exists in `.git/modules`, add with a distinct name or `git submodule add --force` — but on a fresh submodule this should be clean.

- [ ] **Step 1: Add the submodule**

```bash
cd "$WORKTREE" && git submodule add https://github.com/tmux-plugins/tpm tmux/plugins/tpm
```

- [ ] **Step 2: Verify**

Run: `test -x "$WORKTREE/tmux/plugins/tpm/tpm" && test -x "$WORKTREE/tmux/plugins/tpm/bin/install_plugins" && echo OK`
Expected: `OK`
Run: `cd "$WORKTREE" && git status --short`
Expected: staged `.gitmodules` and `tmux/plugins/tpm` only (the worktree is otherwise clean).

- [ ] **Step 3: Add tpm to shellcheck ignore_paths in CI**

In `.github/workflows/quality-check.yml`, the shellcheck job's `ignore_paths` block currently lists `vim/bundle`, `vim/bundle-disable`, `gdb/gdb-dashboard`. Add a line for the new submodule (consistent with existing entries even though CI doesn't check out submodules):

```yaml
          ignore_paths: >-
            vim/bundle
            vim/bundle-disable
            gdb/gdb-dashboard
            tmux/plugins/tpm
```

Run: `cd "$WORKTREE" && uv run --with yamllint yamllint -c .yamllint .github/`
Expected: no output (clean).

- [ ] **Step 4: Commit**

```bash
cd "$WORKTREE" && git add .gitmodules tmux/plugins/tpm .github/workflows/quality-check.yml && git commit -m "tmux: Vendor tpm (tmux plugin manager) as git submodule"
```

---

### Task 3: Add plugin block to tmux.conf

**Files:**
- Modify: `tmux/tmux.conf` (append at end, after the `status-right` line)

- [ ] **Step 1: Append the plugin block**

Append to `$WORKTREE/tmux/tmux.conf` (keep this the last block in the base file). The literal `~/rcfiles` and `~/.tmux/plugins/` paths *inside* this block are the production deploy paths — write them verbatim, do NOT substitute `$WORKTREE`:

```tmux

# ── Plugins ──────────────────────────────────────────────────────────
# TPM (tmux plugin manager) is vendored as a git submodule at
# ~/rcfiles/tmux/plugins/tpm (pinned; updated via git, not prefix+U).
# The plugins TPM manages are cloned OUTSIDE the repo into
# ~/.tmux/plugins/ (TMUX_PLUGIN_MANAGER_PATH below).
#   prefix+I = install plugins   prefix+U = update plugins
#
# tmux-resurrect: prefix+Ctrl-s = save, prefix+Ctrl-r = restore.
# tmux-continuum: autosaves every 15 min. Restore stays MANUAL --
# @continuum-restore is deliberately not set, so a fresh server never
# auto-loads stale state.
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'

# Save pane scrollback contents...
set -g @resurrect-capture-pane-contents 'on'
# ...and relaunch these programs on restore, in addition to resurrect's
# conservative defaults (vi vim nvim emacs man less more tail top htop).
set -g @resurrect-processes 'ssh mosh-client claude'

set -g @continuum-save-interval '15'

set-environment -g TMUX_PLUGIN_MANAGER_PATH '~/.tmux/plugins/'

# Keep this run-shell as the LAST line of this base file. Host-specific
# parts appended after it by setup.sh linkit() may safely override
# display options (e.g. status-right): run-shell jobs execute only
# after the whole generated config is parsed, so continuum wraps the
# FINAL status-right with its autosave hook. Host parts must NOT set
# @resurrect-*/@continuum-* options (too late by then). If autosave
# ever stops, check: tmux show -g status-right  (should contain
# continuum_save.sh).
if-shell "test -x ~/rcfiles/tmux/plugins/tpm/tpm" \
    "run-shell ~/rcfiles/tmux/plugins/tpm/tpm"
```

- [ ] **Step 2: Syntax-check the config on an isolated server**

Run: `tmux -L conftest -f "$WORKTREE/tmux/tmux.conf" new-session -d \; kill-server`
Expected: no output, exit 0. (Plugins aren't installed and the `if-shell` guard is false from a worktree — that's fine; this only checks the base file parses. The `-L conftest` socket keeps it away from your real running server. Full plugin behaviour is verified hermetically in Task 5.)

- [ ] **Step 3: Commit**

```bash
cd "$WORKTREE" && git add tmux/tmux.conf && git commit -m "tmux: Add TPM with resurrect/continuum session persistence"
```

---

### Task 4: setup.sh headless plugin install

**Files:**
- Modify: `setup.sh` — new `tmux_plugins()` function after the `pkgs()` function, and a `tmux_plugins` call inserted between the `pkgs` and `bash_completions` calls near the bottom. Call MUST come after `pkgs` (installs the tmux binary on fresh hosts) and after `linkit tmux` (deploys the config the installer reads). (Anchors are textual; don't rely on absolute line numbers.)

- [ ] **Step 1: Add the function** (TAB indentation)

```bash
function tmux_plugins {
	TPM_INSTALL="$RCFILES/tmux/plugins/tpm/bin/install_plugins"
	if [ ! -x "$TPM_INSTALL" ]; then
		echo "Warning: tpm submodule missing; skipping tmux plugin install" >&2
		return 0
	fi

	# If a tmux server is already running it may predate the plugin
	# config; re-source so TMUX_PLUGIN_MANAGER_PATH is set on the server
	# BEFORE installing. Otherwise tpm falls back to its own parent dir
	# and clones plugins INSIDE this repo. Errors (e.g. no server
	# running) are expected and non-fatal.
	tmux source-file ~/.tmux.conf || true

	# Headless install of @plugin entries into ~/.tmux/plugins/.
	# Needs network; failure is non-fatal -- install later with prefix+I.
	"$TPM_INSTALL" \
		|| echo "Warning: tmux plugin install failed (no network?)" >&2
}
```

- [ ] **Step 2: Insert the call**

Between the existing `pkgs` and `bash_completions` lines at the bottom of `setup.sh`:

```bash
pkgs

tmux_plugins

bash_completions
```

- [ ] **Step 3: Lint**

Run: `bash -n "$WORKTREE/setup.sh" && shellcheck -S warning "$WORKTREE/setup.sh"`
Expected: clean (as in Task 1 Step 5; confirm any finding is pre-existing on master).

- [ ] **Step 4: Commit**

```bash
cd "$WORKTREE" && git add setup.sh && git commit -m "setup.sh: Install tmux plugins headlessly via tpm"
```

---

### Task 5: Hermetic plugin verification (in worktree)

Proves TPM installs resurrect + continuum and that a save/restore round-trip works — entirely inside `$WORKTREE/tmp`, on a private `-L tpmtest` socket. **Touches nothing in `$HOME` outside the worktree**: not `~/.tmux.conf`, not the running server, not `~/.tmux/plugins`, not `~/.local/share/tmux`. Live deployment is Task 7. No commit in this task (verification only).

- [ ] **Step 1: Write a throwaway hermetic config**

The committed `tmux/tmux.conf` points TPM at the *production* `~/.tmux/plugins/` and guards `run-shell` on `~/rcfiles/...` (false from a worktree). For isolation, use a throwaway config with worktree-local paths baked in (unquoted heredoc expands `$WORKTREE` at write time — one command, within the bash budget):

```bash
mkdir -p "$WORKTREE/tmp/plugins" "$WORKTREE/tmp/resurrect"
cat > "$WORKTREE/tmp/test.tmux.conf" <<EOF
set-environment -g TMUX_PLUGIN_MANAGER_PATH "$WORKTREE/tmp/plugins/"
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'
set -g @resurrect-capture-pane-contents 'on'
set -g @resurrect-processes 'ssh mosh-client claude'
set -g @resurrect-dir "$WORKTREE/tmp/resurrect"
set -g @continuum-save-interval '15'
run-shell "$WORKTREE/tmux/plugins/tpm/tpm"
EOF
```

`@resurrect-dir` is set ONLY here so saves land in the worktree, never in the live `~/.local/share/tmux/resurrect`; it is intentionally absent from the production config (Task 3).

- [ ] **Step 2: Install plugins into the worktree-local path**

```bash
tmux -L tpmtest -f "$WORKTREE/tmp/test.tmux.conf" new-session -d -s install
tmux -L tpmtest run-shell "$WORKTREE/tmux/plugins/tpm/bin/install_plugins"
```

Run: `ls "$WORKTREE/tmp/plugins"`
Expected: `tmux-continuum  tmux-resurrect`.
(tpm's headless `bin/install_plugins` reads the `@plugin` list from the `-L tpmtest` server it runs inside — this is the one verify-by-doing point. If the dirs don't appear, check `tmux -L tpmtest show-environment -g TMUX_PLUGIN_MANAGER_PATH` and that `run-shell .../tpm` loaded; adjust invocation per tpm's README.)

- [ ] **Step 3: Save → kill → restore round-trip**

```bash
tmux -L tpmtest send-keys -t install:0.0 'echo RESTORE-CANARY' Enter
tmux -L tpmtest split-window -t install:0
tmux -L tpmtest send-keys -t install:0.1 'top' Enter
tmux -L tpmtest run-shell "$WORKTREE/tmp/plugins/tmux-resurrect/scripts/save.sh"
```

Run: `ls -la "$WORKTREE/tmp/resurrect"`
Expected: a dated `tmux_resurrect_*.txt` plus a `last` symlink (confirms `@resurrect-dir` is honoured — saves are hermetic).

```bash
tmux -L tpmtest kill-server
tmux -L tpmtest -f "$WORKTREE/tmp/test.tmux.conf" new-session -d -s scratch
tmux -L tpmtest run-shell "$WORKTREE/tmp/plugins/tmux-resurrect/scripts/restore.sh"
```

Run: `tmux -L tpmtest list-windows -t install && tmux -L tpmtest capture-pane -p -t install:0.0 | grep RESTORE-CANARY`
Expected: `install` session restored with the 2-pane window; `RESTORE-CANARY` present (pane-contents capture works).
Run: `tmux -L tpmtest display-message -p -t install:0.1 '#{pane_current_command}'`
Expected: `top` (whitelisted-program relaunch works — `top` is on resurrect's default list).

- [ ] **Step 4: Record findings**

Note for the spec's open questions and for Task 7: observed scrollback-capture depth, and whether `top` relaunched cleanly. `ssh`/`mosh-client`/`claude` matching needs real panes — defer to Task 7 live observation.

- [ ] **Step 5: Tear down (hermetic — nothing outside the worktree)**

```bash
tmux -L tpmtest kill-server
rm -rf "$WORKTREE/tmp/plugins" "$WORKTREE/tmp/resurrect" "$WORKTREE/tmp/test.tmux.conf"
```

`$WORKTREE/tmp` is gitignored and no `~/.tmux*` path was ever written, so repo and live state are both untouched.

---

### Task 6: Documentation

**Files:**
- Modify: `CLAUDE.md` (tmux bullet in Directory Structure + a Key Features entry)
- Modify: `tmux/tmux-help` (user cheat-sheet)

- [ ] **Step 1: Update CLAUDE.md**

In Directory Structure, change the tmux line to:

```markdown
- `tmux/`: Tmux configuration with hostname-specific overrides; TPM vendored at `tmux/plugins/tpm` (plugins clone to `~/.tmux/plugins/`)
```

In Key Features, after the SSH section, add:

```markdown
**Tmux Session Persistence:**
- TPM (tmux plugin manager) is a pinned git submodule at `tmux/plugins/tpm`; managed plugins live outside the repo in `~/.tmux/plugins/` via `TMUX_PLUGIN_MANAGER_PATH`
- tmux-resurrect + tmux-continuum: autosave every 15 minutes, restore is manual (`prefix+Ctrl-r`); `@continuum-restore` deliberately unset
- Saves capture pane scrollback and relaunch whitelisted programs (defaults plus ssh, mosh-client, claude)
- `setup.sh` installs plugins headlessly via `tmux_plugins()`; continuum's autosave hook lives in `status-right`, so host parts may override `status-right` but must not set `@`-options
```

- [ ] **Step 2: Update tmux/tmux-help**

Append:

```
     Ctrl A Ctrl S  save sessions (resurrect; continuum autosaves every 15 min)
     Ctrl A Ctrl R  restore sessions
     Ctrl A I       install plugins (tpm)
     Ctrl A U       update plugins (tpm)
```

- [ ] **Step 3: Commit**

```bash
cd "$WORKTREE" && git add CLAUDE.md tmux/tmux-help && git commit -m "docs: Document tmux plugin manager and session persistence"
```

---

### Task 7: Finish the branch, then deploy & verify live

All development is done. Integrate the branch, **then** run the already-merged code against the live machine. These live steps operate on `~/rcfiles` (the base worktree) by running deployed code — acceptance tests, not edits to the base worktree.

- [ ] **Step 1: Confirm the worktree is clean**

Run: `cd "$WORKTREE" && git status --short && git log --oneline -6`
Expected: no uncommitted/untracked files (Task 5 artifacts removed; `tmp/` is gitignored regardless); commits from Tasks 1–4 and 6 present on `tmux-tpm-resurrect`.

- [ ] **Step 2: Integrate the branch**

Use the `superpowers:finishing-a-development-branch` skill to choose merge / PR and to clean up the worktree afterward (it pairs with `using-git-worktrees`). Do NOT hand-delete the worktree.

- [ ] **Step 3 (post-integration, on `~/rcfiles`): Update base worktree + submodule**

After the branch is on `master` and `~/github/mithro/rcfiles` is updated:

```bash
git -C ~/rcfiles submodule update --init tmux/plugins/tpm
```

Run: `test -x ~/rcfiles/tmux/plugins/tpm/tpm && echo OK`
Expected: `OK`.

- [ ] **Step 4: Deploy the config**

```bash
cat ~/rcfiles/tmux/tmux.conf ~/rcfiles/tmux/tmux.conf-mithis.com > ~/.tmux.conf
```

Run: `grep -c 'mithis.com hosts are blue' ~/.tmux.conf` → Expected `1` (was 2 before this project — linkit fix in effect).
Run: `grep -c 'run-shell ~/rcfiles/tmux/plugins/tpm/tpm' ~/.tmux.conf` → Expected `1`.
(Alternatively run `~/rcfiles/setup.sh`, which regenerates `~/.tmux.conf` via the fixed linkit and runs `tmux_plugins` — heavier, also does apt etc. User's call.)

- [ ] **Step 5: Load into the real server + install plugins**

```bash
tmux source-file ~/.tmux.conf
~/rcfiles/tmux/plugins/tpm/bin/install_plugins
```

Run: `ls ~/.tmux/plugins/` → Expected `tmux-continuum  tmux-resurrect`.
Run: `ls ~/rcfiles/tmux/plugins/` → Expected `tpm` ONLY. If resurrect/continuum appear here, the `TMUX_PLUGIN_MANAGER_PATH` plumbing failed; stop and debug (`tmux show-environment -g TMUX_PLUGIN_MANAGER_PATH`).

- [ ] **Step 6: Verify ordering + keybindings on the real server**

Run: `tmux show-options -g status-right` → contains BOTH `continuum_save.sh` AND the host `hostname -f | sed ...` string (proves the spec's post-parse ordering claim holds with host overrides).
Run: `tmux list-keys -T prefix C-s && tmux list-keys -T prefix C-r` → bound to resurrect `save.sh` / `restore.sh`.

- [ ] **Step 7: First real save + record save dir**

Run: `tmux run-shell ~/.tmux/plugins/tmux-resurrect/scripts/save.sh && ls ~/.local/share/tmux/resurrect/ ~/.tmux/resurrect/`
Expected: a real save in whichever dir exists (records the spec's save-dir answer; the other path errors "No such file" — that is the answer, note it).

- [ ] **Step 8: Confirm autosave (deferred ~15 min) + real-program relaunch**

After ≥15 min: `ls -lt <save-dir> | head -3` shows a save newer than Step 7, and `tmux show-options -g @continuum-save-last-timestamp` advances. Over normal use, confirm `ssh`/`mosh-client`/`claude` panes relaunch on a real `prefix+Ctrl-r`; if they don't, apply the spec-risk fallbacks (`~claude` contains-matcher; drop `mosh-client`).

- [ ] **Step 9: Roll out to other hosts** — storage.mithis.com etc. pick up the change on their next `git pull && ./setup.sh`.

---

## Verification reference (spec risk items → where they're answered)

| Spec risk | Resolved by |
|---|---|
| mosh-client restore approximate | Live real-usage observation (Task 7 Step 8); drop from whitelist or use resurrect arrow syntax if it misbehaves |
| `claude` process-name match | After a live restore with a claude pane (Task 7 Step 8): if not relaunched, try `~claude` (contains-matcher) in `@resurrect-processes` |
| Resurrect save dir default | Hermetic dir forced in Task 5; the real default recorded in Task 7 Step 7 |
| Scrollback capture depth | Task 5 Step 3 CANARY check (hermetic); confirmed live in Task 7 |
