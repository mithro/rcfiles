# SSH Configuration

## Files

| File | Deployed to | Purpose |
|------|-------------|---------|
| `config` | `~/.ssh/config` | SSH client config (ControlMaster, host-specific settings) |
| `authorized_keys` | Appended to `~/.ssh/authorized_keys` | Public keys for server installs |
| `keys/` | `~/.ssh/keys/` | Private keys (separate repo: `rcfiles-sshkeys`) |
| `ssh-agent-mux.toml` | `~/.config/ssh-agent-mux/ssh-agent-mux.toml` | Mux daemon config |
| `bin/ssh-add` | `~/bin/ssh-add` | ssh-add wrapper for mux compatibility |

## Agent Multiplexing (ssh-agent-mux)

### Problem

SSH agent forwarding (`ssh -A`) creates an ephemeral socket per connection. Inside tmux, existing panes cache the old `SSH_AUTH_SOCK` path, breaking SSH operations after reconnecting.

### Architecture

```
SSH_AUTH_SOCK = ~/.ssh/agent/mux.sock
                        |
                  ssh-agent-mux
                   /            \
          local.sock      forwarded-agent.sock
              |                    |
        local ssh-agent      symlink -> sshd socket
        (persistent)         (updated each login)
```

ssh-agent-mux is a read-only multiplexer: it forwards `list-keys` and `sign` requests to all backends, returning the union of available keys. It does not support `add`/`remove`/`lock` — those go directly to the local agent.

### Key Files

**`ssh-agent-mux.toml`** — Mux daemon configuration:
- Listens on `~/.ssh/agent/mux.sock`
- Backends: `~/.ssh/agent/local.sock` and `~/.ssh/forwarded-agent.sock`
- Missing backends are silently skipped (forwarded agent may not exist)

**`bin/ssh-add`** — Wrapper around `/usr/bin/ssh-add`:
- Read-only flags (`-l`, `-L`, `-E`): Pass through to `SSH_AUTH_SOCK` (the mux)
- Mutating operations (add key, `-d`, `-D`, `-x`, `-X`): Redirected to `~/.ssh/agent/local.sock`

**`../tmux/zprofile`** — Login hook (runs on SSH login, before tmux):
- Updates forwarded agent symlink to current sshd socket
- Ensures systemd user services are started (`systemctl --user start`)
- Waits for mux socket to appear
- Serialized with `flock` to prevent races from concurrent SSH logins
- Writes debug logs to `~/.ssh/agent/zprofile.<pid>.log`

### Systemd Services

Agent processes run as systemd user services (with linger enabled so they
persist between SSH sessions):

- `ssh-agent.service` — Local ssh-agent with per-PID socket indirection.
  Uses `~/bin/ssh-agent-start.sh` wrapper for atomic `local.sock` symlink.
- `ross-williams-ssh-agent-mux.service` — Installed by `ssh-agent-mux --install-service`.
  Drop-in override adds `Restart=always`, `LimitCORE=infinity`, and ssh-agent ordering.

Core dumps from ssh-agent-mux are captured by `systemd-coredump` (viewable with `coredumpctl`).

Useful commands:
```bash
systemctl --user status ssh-agent ross-williams-ssh-agent-mux
journalctl --user -u ssh-agent -u ross-williams-ssh-agent-mux
coredumpctl list ssh-agent-mux
```

### Installation

The `ssh-agent-mux` binary is installed by `setup.sh`:
```bash
# In setup.sh — downloads ARM64/AMD64 binary to ~/bin/
ssh_agent_mux
```

Config symlink is also created by `setup.sh`:
```bash
mkdir -p ~/.config/ssh-agent-mux
ln -sf "$RCFILES/ssh/ssh-agent-mux.toml" ~/.config/ssh-agent-mux/ssh-agent-mux.toml
```

`setup.sh` also installs the systemd unit files (`ssh-agent.service` and the
`ross-williams-ssh-agent-mux.service` drop-in override) and enables linger for
the current user (`loginctl enable-linger`) so the services persist across
SSH sessions.

### Design Decisions

- **Per-PID sockets** (`local.<pid>.sock` with `local.sock` symlink): Prevents killing an orphan agent from deleting the active agent's socket (ssh-agent unlinks its `-a` path on SIGTERM).
- **Atomic symlinks** (`ln -s tmp.$$ && mv -f`): Prevents races when multiple SSH sessions update the forwarded agent symlink simultaneously.
- **`9>&-` on daemon launches**: The flock block uses fd 9; without closing it, child daemons inherit the lock and hold it forever, hanging subsequent logins.
- **`/proc/PID/comm` validation**: A plain `ssh-agent` accidentally bound to `mux.sock` satisfies "PID alive + socket exists" but doesn't multiplex. Checking the process name catches this.
