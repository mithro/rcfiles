# Systemd User Services for SSH Agent Infrastructure

## Problem

The current ssh-agent and ssh-agent-mux processes are started by `tmux/zprofile` on
each SSH login. They have two reliability issues:

1. **ssh-agent-mux dies on SSH disconnect** — it retains a controlling terminal (`pts/N`)
   because it's started with `&` + `disown` rather than proper daemonization. When the
   SSH connection drops and the pty is destroyed, the kernel sends SIGHUP and kills it.
   The local ssh-agent survives because it double-forks and calls setsid.

2. **No automatic restart** — if either process crashes or is killed, nothing restarts it
   until the next SSH login triggers zprofile.

Additionally, there is a path mismatch: `ssh-agent-mux.toml` references
`~/.ssh/forwarded-agent.sock` but zprofile creates the forwarded symlink at
`~/.ssh/agent/forwarded.sock`. The mux has never been able to see the forwarded agent.

## Solution

Replace the ad-hoc process management in zprofile with systemd user services.

### New Files

#### `ssh/systemd/ssh-agent.service`

Systemd user unit for the local ssh-agent.

- **Type:** `simple` (ssh-agent runs in foreground via `-D` flag)
- **ExecStart:** wrapper script `ssh-agent-start.sh` that:
  1. Cleans up stale `local.*.sock` files from prior crashes
  2. Creates `local.<pid>.sock` socket path
  3. Atomically updates `local.sock` symlink to point to it
  4. `exec`s into `/usr/bin/ssh-agent -D -a <per-pid-socket>`
- **Restart:** `on-failure`, `RestartSec=1`
- **Install:** `WantedBy=default.target`

#### `ssh/systemd/ssh-agent-mux.service`

Systemd user unit for ssh-agent-mux.

- **Type:** `simple` (ssh-agent-mux runs in foreground)
- **ExecStart:** `%h/bin/ssh-agent-mux` (reads config from `~/.config/ssh-agent-mux/`)
- **Dependencies:** `After=ssh-agent.service`, `Wants=ssh-agent.service`
  (soft dependency — mux tolerates missing backends but should start after the agent)
- **Restart:** `on-failure`, `RestartSec=1`
- **Core dumps:** `LimitCORE=infinity` — with `systemd-coredump` installed, crashes are
  captured and browsable via `coredumpctl`
- **Install:** `WantedBy=default.target`

#### `ssh/systemd/ssh-agent-start.sh`

Wrapper script for ssh-agent that implements the per-PID socket + atomic symlink pattern.

```
#!/bin/sh
AGENT_DIR="$HOME/.ssh/agent"
# Clean up stale per-PID sockets from prior crashes
rm -f "$AGENT_DIR"/local.*.sock
# Create per-PID socket path
SOCK="$AGENT_DIR/local.$$.sock"
# Atomic symlink: local.sock -> local.<pid>.sock
ln -sf "$SOCK" "$AGENT_DIR/local.sock.tmp.$$"
mv -f "$AGENT_DIR/local.sock.tmp.$$" "$AGENT_DIR/local.sock"
# Run in foreground, bind to per-PID socket
exec /usr/bin/ssh-agent -D -a "$SOCK"
```

### Modified Files

#### `ssh/ssh-agent-mux.toml`

Fix the forwarded agent path to match what zprofile actually creates:

```toml
agent_sock_paths = [
    "~/.ssh/agent/local.sock",
    "~/.ssh/agent/forwarded.sock",    # was: ~/.ssh/forwarded-agent.sock
]
listen_path = "~/.ssh/agent/mux.sock"
log_level = "warn"
```

#### `setup.sh`

In the package install section:
- Add `systemd-coredump` to the package list

In the `ssh_agent_mux` function (or a new `ssh_agent_systemd` function):
- `loginctl enable-linger $USER`
- Create `~/.config/systemd/user/` directory
- Symlink unit files from repo: `ssh/systemd/*.service` -> `~/.config/systemd/user/`
- Install wrapper script: `ssh/systemd/ssh-agent-start.sh` -> `~/bin/ssh-agent-start.sh`
- `systemctl --user daemon-reload`
- `systemctl --user enable ssh-agent.service ssh-agent-mux.service`

#### `tmux/zprofile`

Replace the agent startup section. Remove:
- All ssh-agent startup logic (pid file checks, ssh-agent -a, per-PID socket creation)
- All ssh-agent-mux startup logic (pid file checks, comm validation, background start)
- PID file management (`local.pid`, `mux.pid`)

Keep:
- Forwarded agent symlink update (still needed per-login — each SSH connection has a
  different ephemeral socket in `/tmp/ssh-*/`)
- `flock` serialization for the forwarded symlink update (concurrent SSH logins)

Add:
- `systemctl --user start ssh-agent.service ssh-agent-mux.service` (idempotent — no-op
  if already running, starts if not)
- Wait loop for `~/.ssh/agent/mux.sock` to appear (up to ~2s, should be near-instant
  with linger since services are already running)
- `export SSH_AUTH_SOCK="$HOME/.ssh/agent/mux.sock"`

### Login Flow After Changes

```
SSH login
  |
  v
zprofile
  |-- Capture forwarded agent socket from $SSH_AUTH_SOCK
  |-- flock -> update ~/.ssh/agent/forwarded.sock symlink -> release flock
  |-- systemctl --user start ssh-agent ssh-agent-mux  (idempotent)
  |-- Wait for ~/.ssh/agent/mux.sock to exist (should already be there)
  |-- export SSH_AUTH_SOCK=~/.ssh/agent/mux.sock
  |-- Write env file for tmux
  `-- exec tmux
```

### Steady-State Behavior

- Both services run persistently via linger (survive SSH disconnects)
- On crash: systemd restarts automatically within 1 second
- ssh-agent-mux core dumps captured by `systemd-coredump`, viewable with `coredumpctl`
- Forwarded agent symlink updated on each SSH login to track the current connection
- ssh-agent-mux sees forwarded keys appear/disappear as SSH connections come and go

### Files Becoming Obsolete

These files in `~/.ssh/agent/` are no longer needed after migration:
- `local.pid` — systemd tracks the PID
- `mux.pid` — systemd tracks the PID
- `zprofile.*.log` — can keep debug logging or remove (separate decision)
