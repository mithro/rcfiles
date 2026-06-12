# tmux TPM + resurrect/continuum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TPM (vendored as a git submodule) with tmux-resurrect + tmux-continuum so tmux sessions survive server death (reboot/OOM), with 15-minute autosave and strictly manual restore.

**Architecture:** TPM is pinned at `tmux/plugins/tpm` (same convention as `vim/bundle/*`); the plugins TPM manages are cloned outside the repo to `~/.tmux/plugins/` via `TMUX_PLUGIN_MANAGER_PATH`. `setup.sh` gains a headless plugin-install step and a targeted fix for `linkit()` appending duplicate host parts. Spec: `docs/superpowers/specs/2026-06-11-tmux-tpm-resurrect-design.md`.

**Tech Stack:** bash (setup.sh, tab-indented, must pass `shellcheck -S warning` per CI), tmux 3.5a config, git submodules, Python via `uv run` for the test driver.

**Working location:** Directly on `master` in `~/rcfiles` (no worktree). Rationale: changes must be verified against this machine's live `$HOME` deployment (`setup.sh` hardcodes `RCFILES=~/rcfiles`), and the repo's history is direct-to-master with small commits. The repo has unrelated uncommitted changes (`git/gitconfig`, `git/gitignore`, `setup.sh`, `ssh/keys/`) — **always `git add` specific paths, never `git add -A` or `git commit -a`.**

> **Note on pre-existing setup.sh modifications:** `setup.sh` already has uncommitted changes in the working tree. Before Task 1, run `git diff setup.sh` and confirm the diff does NOT touch `linkit()` or the function-call list at the bottom. If it does, stop and ask the user how to proceed. Our commits stage `setup.sh` whole-file, so pre-existing edits would ride along — surface this to the user at the first setup.sh commit and let them decide (commit theirs first, or accept combined). (Plan-review verification found the current diff only touches the `claude()` function.)
>
> **Execution note:** this machine's PreToolUse hooks have denied `;`-separated compound shell commands while `&&` chains run fine. If a hook denial appears, split the command into separate invocations rather than stalling.

---

### Task 1: Fix linkit() duplicate host-part append (TDD)

The bug: `linkit()` iterates suffixes `-$BASE_DOMAIN`, `-$DOMAIN`, `-$HOSTNAME`; on `*.mithis.com` hosts `BASE_DOMAIN == DOMAIN == mithis.com`, so `tmux.conf-mithis.com` is appended twice (the deployed `~/.tmux.conf` on this machine shows the duplication). Fix: dedupe **by path**.

**Files:**
- Modify: `setup.sh` (the `linkit()` function, currently lines ~58–98)
- Test: `tmp/test_linkit_dedupe.py` (repo-local tmp/, already gitignored; deleted in Task 7)

- [ ] **Step 1: Write the failing test**

Create `~/rcfiles/tmp/test_linkit_dedupe.py` (note: `mkdir -p ~/rcfiles/tmp` first; never use /tmp):

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

SETUP_SH = Path.home() / "rcfiles" / "setup.sh"
# Repo convention: never use /tmp; keep scratch dirs under rcfiles/tmp.
TMP_ROOT = Path.home() / "rcfiles" / "tmp"


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

Run: `cd ~/rcfiles && uv run python tmp/test_linkit_dedupe.py`
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

Run: `cd ~/rcfiles && uv run python tmp/test_linkit_dedupe.py`
Expected: `host part appended 1 time(s); expected 1`, exit code 0.

- [ ] **Step 5: Lint**

Run: `bash -n ~/rcfiles/setup.sh && shellcheck -S warning ~/rcfiles/setup.sh`
Expected: no output from `bash -n`; shellcheck reports nothing new versus master (run `git stash && shellcheck -S warning setup.sh; git stash pop` for a baseline only if it reports anything).

- [ ] **Step 6: Commit**

```bash
cd ~/rcfiles && git add setup.sh && git commit -m "setup.sh: Dedupe linkit host parts when domain suffixes coincide"
```
(Watch for pre-existing setup.sh edits riding along — see note in header.)

---

### Task 2: Vendor TPM as a git submodule

**Files:**
- Create: `tmux/plugins/tpm` (submodule)
- Modify: `.gitmodules` (automatic via `git submodule add`)
- Modify: `.github/workflows/quality-check.yml` (shellcheck `ignore_paths`)

- [ ] **Step 1: Add the submodule**

```bash
cd ~/rcfiles && git submodule add https://github.com/tmux-plugins/tpm tmux/plugins/tpm
```

- [ ] **Step 2: Verify**

Run: `test -x ~/rcfiles/tmux/plugins/tpm/tpm && test -x ~/rcfiles/tmux/plugins/tpm/bin/install_plugins && echo OK`
Expected: `OK`
Run: `cd ~/rcfiles && git status --short`
Expected: staged `.gitmodules` and `tmux/plugins/tpm` only (plus the pre-existing unrelated modifications).

- [ ] **Step 3: Add tpm to shellcheck ignore_paths in CI**

In `.github/workflows/quality-check.yml`, the shellcheck job's `ignore_paths` block currently lists `vim/bundle`, `vim/bundle-disable`, `gdb/gdb-dashboard`. Add a line for the new submodule (consistent with existing entries even though CI doesn't check out submodules):

```yaml
          ignore_paths: >-
            vim/bundle
            vim/bundle-disable
            gdb/gdb-dashboard
            tmux/plugins/tpm
```

Run: `cd ~/rcfiles && uv run --with yamllint yamllint -c .yamllint .github/`
Expected: no output (clean).

- [ ] **Step 4: Commit**

```bash
cd ~/rcfiles && git add .gitmodules tmux/plugins/tpm .github/workflows/quality-check.yml && git commit -m "tmux: Vendor tpm (tmux plugin manager) as git submodule"
```

---

### Task 3: Add plugin block to tmux.conf

**Files:**
- Modify: `tmux/tmux.conf` (append at end, after the `status-right` line)

- [ ] **Step 1: Append the plugin block**

Append to `~/rcfiles/tmux/tmux.conf` (keep this the last block in the base file):

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

Run: `tmux -L conftest -f ~/rcfiles/tmux/tmux.conf new-session -d \; kill-server`
Expected: no output, exit 0. (Plugins aren't installed yet — TPM just defines its keybindings; that's fine. The `-L conftest` socket keeps this away from your real running server.)

- [ ] **Step 3: Commit**

```bash
cd ~/rcfiles && git add tmux/tmux.conf && git commit -m "tmux: Add TPM with resurrect/continuum session persistence"
```

---

### Task 4: setup.sh headless plugin install

**Files:**
- Modify: `setup.sh` — new `tmux_plugins()` function after the `pkgs()` function (closing brace currently ~line 268), and a `tmux_plugins` call inserted between the `pkgs` and `bash_completions` calls near the bottom (~line 406). Call MUST come after `pkgs` (installs the tmux binary on fresh hosts) and after `linkit tmux` (deploys the config the installer reads).

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

Run: `bash -n ~/rcfiles/setup.sh && shellcheck -S warning ~/rcfiles/setup.sh`
Expected: clean (as in Task 1 Step 5).

- [ ] **Step 4: Commit**

```bash
cd ~/rcfiles && git add setup.sh && git commit -m "setup.sh: Install tmux plugins headlessly via tpm"
```

---

### Task 5: Deploy and verify on this machine

Your real tmux server is running with the OLD config — every step here that touches a server uses either your real server (explicitly, for the source-file step) or the isolated `-L plugtest` socket.

- [ ] **Step 1: Regenerate ~/.tmux.conf** (what fixed linkit produces: base + host part exactly once)

```bash
cat ~/rcfiles/tmux/tmux.conf ~/rcfiles/tmux/tmux.conf-mithis.com > ~/.tmux.conf
```

Run: `grep -c 'mithis.com hosts are blue' ~/.tmux.conf`
Expected: `1` (was 2 before this project).
Run: `grep -c 'run-shell ~/rcfiles/tmux/plugins/tpm/tpm' ~/.tmux.conf`
Expected: `1`.

- [ ] **Step 2: Load new config into the REAL running server, then install plugins**

```bash
tmux source-file ~/.tmux.conf
~/rcfiles/tmux/plugins/tpm/bin/install_plugins
```

Expected: install output naming `tmux-resurrect` and `tmux-continuum` with success ("download success" / "Already installed").
Run: `ls ~/.tmux/plugins/`
Expected: `tmux-continuum  tmux-resurrect`
Run: `ls ~/rcfiles/tmux/plugins/`
Expected: `tpm` ONLY — if resurrect/continuum appear here, the TMUX_PLUGIN_MANAGER_PATH plumbing failed; stop and debug (check `tmux show-environment -g TMUX_PLUGIN_MANAGER_PATH`).

- [ ] **Step 3: Verify continuum wrapped status-right on the real server**

Run: `tmux show-options -g status-right`
Expected: contains both `continuum_save.sh` AND the host-specific `hostname -f | sed ...` string — proving the post-parse ordering claim from the spec holds with host overrides.

- [ ] **Step 4: Verify resurrect keybindings**

Run: `tmux list-keys -T prefix C-s && tmux list-keys -T prefix C-r`
Expected: bindings to resurrect's `save.sh` and `restore.sh`.

- [ ] **Step 5: Full save/restore round-trip on the isolated socket**

```bash
tmux -L plugtest -f ~/.tmux.conf new-session -d -s resttest
tmux -L plugtest send-keys -t resttest:0.0 'echo RESTORE-CANARY' Enter
tmux -L plugtest split-window -t resttest:0
tmux -L plugtest send-keys -t resttest:0.1 'top' Enter
tmux -L plugtest run-shell ~/.tmux/plugins/tmux-resurrect/scripts/save.sh
```
(`top` is on resurrect's default whitelist — it exercises program relaunch, covering the spec's test item 5.)

Then find the save directory (version-dependent default — record which):
Run: `ls -la ~/.local/share/tmux/resurrect/ ~/.tmux/resurrect/`
Expected: exactly one of these exists, containing a dated `tmux_resurrect_*.txt` and a `last` symlink.

Kill and restore:
```bash
tmux -L plugtest kill-server
tmux -L plugtest -f ~/.tmux.conf new-session -d -s scratch
tmux -L plugtest run-shell ~/.tmux/plugins/tmux-resurrect/scripts/restore.sh
```
Run: `tmux -L plugtest list-windows -t resttest && tmux -L plugtest capture-pane -p -t resttest:0.0 | grep RESTORE-CANARY`
Expected: `resttest` exists with the 2-pane window; `RESTORE-CANARY` appears (pane-contents capture working).
Run: `tmux -L plugtest display-message -p -t resttest:0.1 '#{pane_current_command}'`
Expected: `top` (whitelisted program relaunched).

Clean up the test server AND its save files (so your real `prefix+Ctrl-r` never restores test state):
```bash
tmux -L plugtest kill-server
rm -rf ~/.local/share/tmux/resurrect ~/.tmux/resurrect
```
(Deleting the whole dir is safe at this point: the only saves in existence are the plugtest ones we just created — plus possibly one continuum autosave from the real server if >15 min elapsed since Step 2; either way Step 6 immediately takes a fresh real save.)

- [ ] **Step 6: Take a first REAL save**

Run: `tmux run-shell ~/.tmux/plugins/tmux-resurrect/scripts/save.sh && ls ~/.local/share/tmux/resurrect/ ~/.tmux/resurrect/`
Expected: a fresh save of your actual sessions in the directory identified in Step 5 (the other path will error "No such file" — that's the answer to the spec's save-dir question; record it).

- [ ] **Step 7: Verify autosave fires** (deferred check — interval is 15 min)

After ≥15 min of normal use: `ls -lt <save-dir> | head -3`
Expected: a save file newer than the manual one from Step 6. (Check `tmux show-options -g @continuum-save-last-timestamp` updates as well.)

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
cd ~/rcfiles && git add CLAUDE.md tmux/tmux-help && git commit -m "docs: Document tmux plugin manager and session persistence"
```

---

### Task 7: Cleanup and final verification

- [ ] **Step 1: Remove the tmp test driver** (conventions: clean up tmp files; the test source is preserved in this plan and the linkit fix is committed)

```bash
rm ~/rcfiles/tmp/test_linkit_dedupe.py
```

- [ ] **Step 2: Final repo state check**

Run: `cd ~/rcfiles && git status --short && git log --oneline -8`
Expected: only the pre-existing unrelated modifications remain unstaged; new commits from Tasks 1–6 present.

- [ ] **Step 3: Confirm Task 5 Step 7 (autosave) result**

If 15 minutes have passed, verify and record. If not, leave a note for the user.

- [ ] **Step 4: Offer the user a full `./setup.sh` run**

A full run exercises `tmux_plugins()` end-to-end but also does apt installs etc. — user's call, not automatic. Other hosts (e.g. storage.mithis.com) pick the change up on their next `git pull && ./setup.sh`.

---

## Verification reference (spec risk items → where they're answered)

| Spec risk | Resolved by |
|---|---|
| mosh-client restore approximate | Real-usage observation after deploy; drop from whitelist or use resurrect arrow syntax if it misbehaves |
| `claude` process-name match | After a restore with a claude pane: if not relaunched, try `~claude` (contains-matcher) in `@resurrect-processes` |
| Resurrect save dir default | Task 5 Step 5/6 records the actual path |
| Scrollback capture depth | Task 5 Step 5 CANARY check; observed behaviour documented in Task 6 if it deviates |
