# Systemd SSH Agent Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad-hoc ssh-agent and ssh-agent-mux process management in zprofile with systemd user services that persist across SSH disconnects and auto-restart on failure.

**Architecture:** Two systemd user units — `ssh-agent.service` (hand-crafted, uses wrapper script for per-PID socket indirection) and `ross-williams-ssh-agent-mux.service` (installed via `--install-service`, augmented with drop-in override). Linger enabled so services survive between logins. Zprofile simplified to only update the forwarded agent symlink and ensure services are started.

**Tech Stack:** systemd user services, zsh (zprofile), bash (setup.sh), systemd-coredump

**Spec:** `docs/superpowers/specs/2026-03-28-systemd-ssh-agent-services-design.md`

---

## File Structure

### New Files
| File | Purpose |
|------|---------|
| `ssh/systemd/ssh-agent.service` | Systemd user unit for local ssh-agent |
| `ssh/systemd/ssh-agent-start.sh` | Wrapper: per-PID socket + atomic symlink + exec ssh-agent |
| `ssh/systemd/ross-williams-ssh-agent-mux.service.d/override.conf` | Drop-in: Restart=always, LimitCORE, ordering |

### Modified Files
| File | Lines Affected | Change |
|------|---------------|--------|
| `setup.sh` | 212-225 (pkgs), 276-298 (ssh_agent_mux), 342 (call site) | Add systemd-coredump, add systemd setup, rename function |
| `tmux/zprofile` | 45-187 (agent section) | Replace agent startup with systemctl + forwarded symlink only |
| `ssh/README.md` | Agent section | Update to document systemd services |

---

### Task 1: Create ssh-agent systemd service unit

**Files:**
- Create: `ssh/systemd/ssh-agent.service`

- [ ] **Step 1: Create the service unit file**

```ini
[Unit]
Description=SSH Authentication Agent
Documentation=man:ssh-agent(1)

[Service]
Type=simple
ExecStart=%h/bin/ssh-agent-start.sh
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Verify the file**

Run: `cat ssh/systemd/ssh-agent.service`
Expected: Contents as above, valid INI syntax.

- [ ] **Step 3: Commit**

```bash
git add ssh/systemd/ssh-agent.service
git commit -m "Add systemd user service unit for ssh-agent"
```

---

### Task 2: Create ssh-agent-start.sh wrapper script

**Files:**
- Create: `ssh/systemd/ssh-agent-start.sh`

- [ ] **Step 1: Create the wrapper script**

```sh
#!/bin/sh
# Wrapper for ssh-agent that implements per-PID socket + atomic symlink.
# Used by ssh-agent.service (systemd user unit).
#
# Each instance gets a unique local.<pid>.sock, with local.sock as an
# atomic symlink to the current one. This survives restarts cleanly:
# the new instance creates a new socket and atomically replaces the symlink.

set -e

AGENT_DIR="$HOME/.ssh/agent"

# Ensure the directory exists
mkdir -p "$AGENT_DIR"

# Clean up stale per-PID sockets from prior crashes
rm -f "$AGENT_DIR"/local.*.sock

# Create per-PID socket path ($$=PID of this shell, which becomes ssh-agent via exec)
SOCK="$AGENT_DIR/local.$$.sock"

# Atomic symlink: local.sock -> local.<pid>.sock
# Use temp + mv for atomicity (rename is atomic on same filesystem)
ln -sf "$SOCK" "$AGENT_DIR/local.sock.tmp.$$"
mv -f "$AGENT_DIR/local.sock.tmp.$$" "$AGENT_DIR/local.sock"

# Run ssh-agent in foreground (-D), binding to the per-PID socket.
# exec replaces this shell, so ssh-agent inherits the same PID that
# we used in the socket filename.
exec /usr/bin/ssh-agent -D -a "$SOCK"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x ssh/systemd/ssh-agent-start.sh`

- [ ] **Step 3: Verify syntax**

Run: `bash -n ssh/systemd/ssh-agent-start.sh && echo OK`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add ssh/systemd/ssh-agent-start.sh
git commit -m "Add ssh-agent-start.sh wrapper for per-PID socket indirection"
```

---

### Task 3: Create ssh-agent-mux drop-in override

**Files:**
- Create: `ssh/systemd/ross-williams-ssh-agent-mux.service.d/override.conf`

- [ ] **Step 1: Create directory and override file**

```ini
[Unit]
After=ssh-agent.service
Wants=ssh-agent.service

[Service]
Restart=always
RestartSec=1
LimitCORE=infinity
```

- [ ] **Step 2: Commit**

```bash
git add ssh/systemd/ross-williams-ssh-agent-mux.service.d/override.conf
git commit -m "Add drop-in override for ssh-agent-mux service"
```

---

### Task 4: Update setup.sh — add systemd-coredump to packages

**Files:**
- Modify: `setup.sh:212-225` (pkgs function)

- [ ] **Step 1: Add systemd-coredump to the package list**

In the `pkgs` function, add `systemd-coredump` to the `apt-get install` list. Use `|| true` to make it soft (don't fail if unavailable):

After the main `apt-get -y install` block (line 225), add:

```bash
	# Core dump capture for debugging ssh-agent-mux crashes (soft dependency)
	sudo apt-get -y install systemd-coredump || true
```

- [ ] **Step 2: Verify syntax**

Run: `bash -n setup.sh && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add setup.sh
git commit -m "setup.sh: Add systemd-coredump to package list (soft)"
```

---

### Task 5: Update setup.sh — add systemd service installation

**Files:**
- Modify: `setup.sh:276-298` (ssh_agent_mux function)

- [ ] **Step 1: Add systemd setup to the ssh_agent_mux function**

After the existing content of `ssh_agent_mux` (line 297, before the closing `}`), add:

```bash
	# --- Systemd user services for ssh-agent and ssh-agent-mux ---

	# Enable linger so services survive between login sessions
	loginctl enable-linger "$USER"

	# Install ssh-agent wrapper script
	cp "$RCFILES/ssh/systemd/ssh-agent-start.sh" ~/bin/ssh-agent-start.sh
	chmod 755 ~/bin/ssh-agent-start.sh

	# Install ssh-agent service unit (symlink so updates come from repo)
	mkdir -p ~/.config/systemd/user
	ln -sf "$RCFILES/ssh/systemd/ssh-agent.service" ~/.config/systemd/user/ssh-agent.service

	# Install ssh-agent-mux service via its built-in installer
	# Requires XDG_RUNTIME_DIR for dbus access
	XDG_RUNTIME_DIR="/run/user/$(id -u)" ~/bin/ssh-agent-mux --install-service

	# Install drop-in override (symlink directory so updates come from repo)
	ln -sf "$RCFILES/ssh/systemd/ross-williams-ssh-agent-mux.service.d" \
		~/.config/systemd/user/ross-williams-ssh-agent-mux.service.d

	# Reload and enable
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user daemon-reload
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user enable \
		ssh-agent.service ross-williams-ssh-agent-mux.service
```

- [ ] **Step 2: Verify syntax**

Run: `bash -n setup.sh && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add setup.sh
git commit -m "setup.sh: Install systemd user services for ssh-agent infrastructure"
```

---

### Task 6: Update tmux/zprofile — replace agent startup with systemd

**Files:**
- Modify: `tmux/zprofile:38-187` (entire agent section)

This is the largest change. Replace lines 38-187 with the new systemd-based approach.

- [ ] **Step 1: Replace the agent section**

Replace lines 38-187 (from `# --- SSH Agent Multiplexing ---` through `} 9>"$AGENT_LOCK"` and `_zlog "flock released"`) with:

```zsh
# --- SSH Agent Multiplexing ---
# Provides a stable SSH_AUTH_SOCK that survives tmux reattach and SSH reconnect.
# Local keys are always available; forwarded keys appear automatically.
#
# ssh-agent and ssh-agent-mux run as systemd user services (installed by setup.sh).
# This section only updates the forwarded agent symlink and ensures services are started.

FORWARDED_AGENT_SOCK="$HOME/.ssh/forwarded-agent.sock"
MUX_SOCK="$HOME/.ssh/agent/mux.sock"
AGENT_LOCK="$HOME/.ssh/agent/.lock"

mkdir -p "$HOME/.ssh/agent"

# Capture the forwarded agent BEFORE taking the lock, since SSH_AUTH_SOCK
# still points to the ephemeral forwarded socket at this point.
_FORWARDED_SSH_AUTH_SOCK="$SSH_AUTH_SOCK"
_zlog "forwarded agent captured: $_FORWARDED_SSH_AUTH_SOCK"

_zlog "acquiring flock..."
{
	flock 9
	_zlog "flock acquired"

	# -- Forwarded agent symlink (atomic replace via temp + rename) --
	_zlog "forwarded symlink: checking _FORWARDED_SSH_AUTH_SOCK=$_FORWARDED_SSH_AUTH_SOCK"
	if [ -n "$_FORWARDED_SSH_AUTH_SOCK" ] && [ -S "$_FORWARDED_SSH_AUTH_SOCK" ]; then
		REAL_AUTH_SOCK="$(readlink -f "$_FORWARDED_SSH_AUTH_SOCK")"
		_zlog "forwarded symlink: real path=$REAL_AUTH_SOCK"
		LOCAL_AGENT_SOCK="$HOME/.ssh/agent/local.sock"
		if [ "$REAL_AUTH_SOCK" != "$(readlink -f "$MUX_SOCK")" ] && \
		   [ "$REAL_AUTH_SOCK" != "$(readlink -f "$LOCAL_AGENT_SOCK")" ]; then
			ln -s "$_FORWARDED_SSH_AUTH_SOCK" "$FORWARDED_AGENT_SOCK.tmp.$$"
			mv -f "$FORWARDED_AGENT_SOCK.tmp.$$" "$FORWARDED_AGENT_SOCK"
			_zlog "forwarded symlink: updated -> $_FORWARDED_SSH_AUTH_SOCK"
		else
			_zlog "forwarded symlink: skipped (points to mux or local agent)"
		fi
	else
		_zlog "forwarded symlink: no valid forwarded socket"
	fi

	_zlog "releasing flock"
} 9>"$AGENT_LOCK"
_zlog "flock released"

# -- Ensure systemd services are running --
# Idempotent: no-op if already running (normal case with linger).
# Starts them if this is the first login after boot or after setup.sh.
_zlog "systemd: starting ssh-agent and ssh-agent-mux services..."
XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user start \
	ssh-agent.service ross-williams-ssh-agent-mux.service 2>&1 | while read -r line; do
	_zlog "systemd: $line"
done

# Wait for mux socket to appear (should be near-instant with linger)
_zlog "waiting for mux socket..."
for _i in 1 2 3 4 5 6 7 8 9 10; do
	[ -S "$MUX_SOCK" ] && break
	sleep 0.2
done
if [ -S "$MUX_SOCK" ]; then
	export SSH_AUTH_SOCK="$MUX_SOCK"
	unset SSH_AGENT_PID
	_zlog "mux: SSH_AUTH_SOCK=$MUX_SOCK"
else
	_zlog "mux: WARNING - mux.sock not found after 2s, SSH_AUTH_SOCK not set"
	echo "Warning: ssh-agent-mux socket not available" >&2
fi
```

- [ ] **Step 2: Verify the zprofile still has valid structure**

Check that the file starts with `#!/bin/zsh`, has the logging setup, the new agent section, then the env file section (line ~190 onwards), then the tmux session management. The env file writing and tmux sections (original lines 190-240) must remain unchanged.

- [ ] **Step 3: Verify syntax**

Run: `zsh -n tmux/zprofile && echo OK`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tmux/zprofile
git commit -m "zprofile: Replace ad-hoc agent management with systemd services"
```

---

### Task 7: Update ssh/README.md

**Files:**
- Modify: `ssh/README.md`

- [ ] **Step 1: Update the Key Files section**

Update the `Key Files` section to reflect that agent lifecycle is now managed by systemd. Replace the zprofile description with:

> **`../tmux/zprofile`** — Login hook (runs on SSH login, before tmux):
> - Updates forwarded agent symlink to current sshd socket
> - Ensures systemd user services are started (`systemctl --user start`)
> - Waits for mux socket to appear
> - Serialized with `flock` to prevent races from concurrent SSH logins
> - Writes debug logs to `~/.ssh/agent/zprofile.<pid>.log`

Add a new subsection after "Key Files" documenting the systemd services:

> ### Systemd Services
>
> Agent processes run as systemd user services (with linger enabled so they
> persist between SSH sessions):
>
> - `ssh-agent.service` — Local ssh-agent with per-PID socket indirection.
>   Uses `~/bin/ssh-agent-start.sh` wrapper for atomic `local.sock` symlink.
> - `ross-williams-ssh-agent-mux.service` — Installed by `ssh-agent-mux --install-service`.
>   Drop-in override adds `Restart=always`, `LimitCORE=infinity`, and ssh-agent ordering.
>
> Core dumps from ssh-agent-mux are captured by `systemd-coredump` (viewable with `coredumpctl`).
>
> Useful commands:
> ```bash
> systemctl --user status ssh-agent ross-williams-ssh-agent-mux
> journalctl --user -u ssh-agent -u ross-williams-ssh-agent-mux
> coredumpctl list ssh-agent-mux
> ```

- [ ] **Step 2: Update the Installation section**

Reflect that `setup.sh` now also installs systemd units and enables linger.

- [ ] **Step 3: Commit**

```bash
git add ssh/README.md
git commit -m "ssh/README.md: Document systemd service architecture"
```

---

### Task 8: Test the full setup on the live system

**Files:** None (verification only)

- [ ] **Step 1: Run setup.sh systemd portion**

Since this is a live system, test the systemd setup by running just the relevant function. First kill the old ad-hoc agents:

```bash
# Find and note old ad-hoc agent PIDs
ps aux | grep ssh-agent | grep -v grep

# Run the setup (from repo root)
cd ~/github/mithro/rcfiles
# Source just the ssh_agent_mux function and run it:
bash -c 'source <(sed -n "/^function ssh_agent_mux/,/^}/p" setup.sh) && RCFILES=~/github/mithro/rcfiles && ssh_agent_mux'
```

- [ ] **Step 2: Verify units are installed and enabled**

```bash
XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user list-unit-files | grep -E 'ssh-agent|ross-williams'
```

Expected: Both units listed as `enabled`.

- [ ] **Step 3: Start the services**

```bash
XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user start ssh-agent.service ross-williams-ssh-agent-mux.service
```

- [ ] **Step 4: Verify services are running**

```bash
XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user status ssh-agent.service ross-williams-ssh-agent-mux.service
```

Expected: Both show `active (running)`.

- [ ] **Step 5: Verify sockets exist**

```bash
ls -la ~/.ssh/agent/local.sock ~/.ssh/agent/local.*.sock ~/.ssh/agent/mux.sock
```

Expected: `local.sock` is a symlink to `local.<pid>.sock`, both exist, `mux.sock` exists.

- [ ] **Step 6: Verify agent works through mux**

```bash
SSH_AUTH_SOCK=~/.ssh/agent/mux.sock ssh-add -l
```

Expected: Lists keys (or "The agent has no identities" if none loaded — either is fine, no connection error).

- [ ] **Step 7: Verify ssh-agent has no controlling terminal**

```bash
ps -o pid,tty,args -p $(systemctl --user show ssh-agent -p MainPID --value)
```

Expected: TTY column shows `?` (no controlling terminal).

- [ ] **Step 8: Verify coredump is configured**

```bash
cat /proc/sys/kernel/core_pattern
```

Expected: Contains `systemd-coredump` (after systemd-coredump package is installed).

- [ ] **Step 9: Verify linger is enabled**

```bash
ls /var/lib/systemd/linger/$USER
```

Expected: File exists.

- [ ] **Step 10: Commit any fixes from testing**

If any issues were found and fixed during testing, commit the fixes.
