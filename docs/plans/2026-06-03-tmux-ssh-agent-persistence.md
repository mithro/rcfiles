# Plan: tmux + ssh-agent that survive a Wayland crash / X logout

**Status:** design locked, not yet implemented · **Living document** — update as you execute.
**Machine:** the laptop (x1c, Ubuntu 26.04, systemd 259, tmux 3.6, UID 1000, GNOME/Wayland).
**Scope chosen:** survive *compositor crash* + *logout/login*. **Not** reboot. From-now-on
(no in-place rescue of today's 3 running sessions).

---

## Why tmux dies today (verified, not assumed)

tmux servers have no link to X/Wayland. What kills them is **systemd-logind cgroup teardown**:

- Running tmux server (pid 7438) lives at:
  `0::/user.slice/user-1000.slice/user@1000.service/app.slice/`**`kitty-7229-0.scope`**
  → it is a *child of the kitty window's scope*.
- `Linger=no` → when the last session ends, systemd stops `user@1000.service`, killing
  everything under it (the compiled default `KillUserProcesses=yes` is in force; logind.conf
  only *comments* it).
- On GNOME **Wayland**, a `mutter`/`gnome-shell` crash ends the whole session — i.e. it
  collapses into the *same* teardown path as logout. **One fix covers both.**

`nohup`/`setsid`/`disown` do **not** help: logind kills by cgroup membership, not by
controlling terminal. The only lever is *which cgroup owns the process* → a systemd unit.

## ssh-agent angle (verified)

- Panes are **bash** (`default-command bash`) and `SSH_AUTH_SOCK` is **deliberately excluded
  from `update-environment`** → every pane inherits the **tmux server's birth value**.
  Control the server's birth env → control every pane.
- Today the server is born with `SSH_AUTH_SOCK=/run/user/1000/gcr/ssh` (GNOME's gcr agent,
  session-tied). The `ssh-agent-mux` is **not running on the laptop**; the mux is a
  **server-side** tool (it merges this laptop's *forwarded-out* keys with a remote's local
  keys, on the remote). On the laptop we want **one local agent**, persistent.
- Keys: `new_misc_key` (4096 RSA, the forwarded-out key) and `home_key` are
  **passphrase-protected**; `amazon-*`, `claude_ha_key` are not. **Decision: no preloading,
  no automated loading** — the agent is an empty vessel; you `ssh-add` on demand and the
  unlock persists (across crash/logout) until reboot.

---

## Decisions locked

| # | Decision | Choice |
|---|---|---|
| 1 | What survives | compositor crash + logout/login (NOT reboot) |
| 2 | Today's 3 sessions | from-now-on; no in-place rescue |
| 3 | mux on laptop | drop it (local agent only); mux stays a remote/server tool |
| 4 | agent provider | **dedicated `ssh-agent.service`** (lingering), not gcr |
| 5 | key loading | **none/manual** — empty agent, `ssh-add` on demand |

## Target architecture

```
loginctl enable-linger tim                     # user@1000.service never stops
 user@1000.service  (now boot-started, logout-proof)
 ├─ ssh-agent.service        → /run/user/1000/ssh-agent.socket   (empty until you ssh-add)
 ├─ tmux.service  (After/Requires ssh-agent)  → server born with SSH_AUTH_SOCK=that socket
 │     └─ session "default" (window h: tail -f ~/.tmux-help, remain-on-exit) keeps it alive
 ├─ ~/.config/environment.d/ssh-agent.conf     # everyone agrees on the socket path
 └─ ~/.config/ssh-agent-local-only             # marker: tells zprofile "skip the mux here"
rcfiles tmux/zprofile: agent block guarded by the marker (servers unchanged)
```

**Lifecycle proof:**

| Event | dies | survives (lingering) | ssh in tmux |
|---|---|---|---|
| compositor crash (mutter) | session, GUI apps | user@ + ssh-agent + tmux | ✅ key still loaded |
| logout / login | session scope | same | ✅ key still loaded |
| reboot | everything | agent+tmux restart **empty** (by design) | ⚠️ `ssh-add` once |

---

## Guiding principles

1. **One lever at a time, proven before the next.** Each piece is landed and verified in
   isolation; never stack an unverified change on another.
2. **Structural evidence now, empirical proof later.** Confirming cgroup placement + linger
   is *necessary* evidence but not *sufficient*; the acceptance gate is a real logout and a
   real reboot with the tmux server **PID unchanged** / services **active**.
3. **Backward-compatible for servers.** The shared `zprofile` change must be a no-op anywhere
   the marker is absent. The mux path stays exactly as-is on remotes.
4. **No surprise destruction.** Don't kill the current server; let cutover happen at reboot
   (or an explicit, opt-in switch). The plan never assumes today's sessions are expendable
   beyond what was agreed.
5. **Laptop-specifics stay laptop-local.** systemd units, `environment.d`, and the marker
   live in `~/.config` (not committed to shared rcfiles) unless we later choose to have
   `setup.sh` install them on `SERVER=0` hosts (see Open items).

---

## The build loop

This is a loop, not a one-shot checklist. For **each component** below, run the cycle:

> **PICK** the next unbuilt component →
> **PREDICT** the exact command output / state you expect to see →
> **APPLY** the smallest change →
> **VERIFY** actual vs. predicted (paste real output into this doc) →
> **RECORD** result + anything surprising, here, under that component →
> if mismatch: **DIAGNOSE before proceeding** (do not move on with a red check) →
> **EVOLVE** the plan if reality differed → next component.

Components are ordered by dependency: linger → agent → tmux → zprofile → cutover → acceptance.
Re-enter the loop any time a verify fails or a new wrinkle appears.

### Worked example of one loop pass (component: lingering)

- **PICK:** lingering.
- **PREDICT:** after `loginctl enable-linger tim`, `loginctl show-user tim -p Linger`
  prints `Linger=yes`, and `/var/lib/systemd/linger/tim` exists.
- **APPLY:** `loginctl enable-linger tim`
- **VERIFY:**
  ```
  $ loginctl show-user tim --property=Linger
  Linger=yes            # ← paste real output here on execution
  ```
- **RECORD:** _(fill in: e.g. "Linger=yes ✓ 2026-06-0x")_
- **DIAGNOSE (if needed):** if still `no`, check polkit / that you ran as tim.
- **EVOLVE:** none expected. → next: ssh-agent.service.

---

## Components (each run through the loop above)

### 1. Lingering — close the logout hole
- **APPLY:** `loginctl enable-linger tim`
- **VERIFY (predict in bold):** `loginctl show-user tim -p Linger` → **`Linger=yes`**.
- Nothing else changes yet; the current server is still terminal-parented. That's fine.

### 2. `ssh-agent.service` (+ environment.d) — the empty persistent agent
- **APPLY** `~/.config/systemd/user/ssh-agent.service`:
  ```ini
  [Unit]
  Description=SSH authentication agent (persistent, lingering)
  Documentation=man:ssh-agent(1)

  [Service]
  Type=simple
  ExecStartPre=-/usr/bin/rm -f %t/ssh-agent.socket
  ExecStart=/usr/bin/ssh-agent -D -a %t/ssh-agent.socket
  Restart=on-failure

  [Install]
  WantedBy=default.target
  ```
  `%t` = `/run/user/1000`. `-D` = foreground (systemd supervises). `ExecStartPre -rm` clears a
  stale socket so `-a` won't hit "Address already in use".
- **APPLY** `~/.config/environment.d/ssh-agent.conf`:
  ```
  SSH_AUTH_SOCK=${XDG_RUNTIME_DIR}/ssh-agent.socket
  ```
- **APPLY:** `systemctl --user daemon-reload && systemctl --user enable --now ssh-agent.service`
- **VERIFY (predict):**
  - `systemctl --user is-active ssh-agent.service` → **`active`**
  - `test -S /run/user/1000/ssh-agent.socket && echo ok` → **`ok`**
  - cgroup is under the manager, not a session/terminal scope:
    `systemctl --user show ssh-agent.service -p ControlGroup`
    → **`…/user@1000.service/app.slice/ssh-agent.service`**
  - env var resolves for *new* shells (environment.d only affects new sessions):
    open a fresh login → `echo $SSH_AUTH_SOCK` → **`/run/user/1000/ssh-agent.socket`**
    (if it's still `…/gcr/ssh`, environment.d didn't take — see DIAGNOSE).
- **DIAGNOSE if env wrong:** confirm `${XDG_RUNTIME_DIR}` expanded (some setups need a literal
  `/run/user/1000`); check no later file in `environment.d` overrides; `systemctl --user
  show-environment | grep SSH_AUTH_SOCK`.
- **Non-disruptive functional test (does not touch current session):**
  ```
  SSH_AUTH_SOCK=/run/user/1000/ssh-agent.socket ssh-add -l        # expect "no identities"
  SSH_AUTH_SOCK=/run/user/1000/ssh-agent.socket ssh-add ~/.ssh/keys/new_misc_key   # prompts once
  SSH_AUTH_SOCK=/run/user/1000/ssh-agent.socket ssh -T <a-host>   # expect auth via the key
  ```

### 3. `tmux.service` — the server in its own scope
- **Pre-check:** `test -f ~/.tmux-help && echo ok` (window `h` tails it; zprofile already
  relies on it). If missing, `: > ~/.tmux-help`.
- **APPLY** `~/.config/systemd/user/tmux.service`:
  ```ini
  [Unit]
  Description=tmux server (persistent across logout/compositor crash)
  Documentation=man:tmux(1)
  Requires=ssh-agent.service
  After=ssh-agent.service

  [Service]
  Type=forking
  ExecStart=/usr/bin/tmux new-session -d -s default -n h "tail -f %h/.tmux-help"
  ExecStartPost=/usr/bin/tmux set-window-option -t default:h remain-on-exit on
  ExecStop=/usr/bin/tmux kill-server
  Restart=on-failure

  [Install]
  WantedBy=default.target
  ```
  Mirrors zprofile's `default` session (help window kept alive by `remain-on-exit`), so when a
  login later runs zprofile, `tmux has-session -t default` is already true and it just
  attaches. Uses the **default socket** (`/tmp/tmux-1000/default`) — same one zprofile uses.
- **APPLY:** `systemctl --user enable tmux.service` — **do NOT `--now`** yet (the old server
  holds the default socket; see Component 5).
- **VERIFY (deferred to cutover):** predictions for *after* it actually runs:
  - `systemctl --user show tmux.service -p ControlGroup`
    → **`…/user@1000.service/app.slice/tmux.service`** (NOT a `kitty-*.scope`)
  - a pane's agent path: `tmux new-window 'echo $SSH_AUTH_SOCK; sleep 2'`
    → **`/run/user/1000/ssh-agent.socket`**

### 4. `zprofile` guard (rcfiles, shared) + marker (laptop-local)
- **APPLY** marker (laptop only, not committed): `touch ~/.config/ssh-agent-local-only`
- **APPLY** edit to `rcfiles/tmux/zprofile`: guard the agent-mux section (current lines
  ~54–182: the forwarded-capture + the whole `flock` block) so it is skipped when the marker
  is present and `SSH_AUTH_SOCK` is already a live managed socket. Cleanest mechanical form —
  extract that block verbatim into a function and call it conditionally:
  ```zsh
  _setup_ssh_agent_mux() {
      # >>> existing lines 54–182 moved here verbatim (forwarded capture + flock block) <<<
  }

  if [[ -f "$HOME/.config/ssh-agent-local-only" && -S "$SSH_AUTH_SOCK" ]]; then
      _zlog "agent: local-only marker present; using managed agent $SSH_AUTH_SOCK, skipping mux"
      # keep SSH_AUTH_SOCK as provided by environment.d / the user manager
  else
      _setup_ssh_agent_mux
  fi
  ```
  The `~/.update-env` writer (lines 184+) and the tmux launch (206+) are **unchanged** — they
  run in both branches and now record the managed `SSH_AUTH_SOCK` on the laptop.
- **VERIFY (predict):**
  - On laptop: a fresh login's `~/.ssh/agent/zprofile.*.log` contains
    **`local-only marker present … skipping mux`**, no `ssh-agent-mux` process spawns
    (`pgrep -x ssh-agent-mux` → empty), and `echo $SSH_AUTH_SOCK` →
    **`/run/user/1000/ssh-agent.socket`**.
  - Backward-compat (must hold): with the marker *absent* (simulate:
    `mv ~/.config/ssh-agent-local-only{,.off}` in a throwaway login, then restore) the old
    mux path runs exactly as before. Better: confirm on an actual server that behavior is
    unchanged before relying on it there.
- **Note:** commit the `zprofile` change to rcfiles as its **own** commit (the repo already
  has unrelated `M git/gitconfig`, `M tmux/tmux.conf` — do not sweep those in).

### 5. Cutover (from-now-on)
The old gcr-parented server still owns `/tmp/tmux-1000/default`, so `tmux.service` (Type=forking)
can't cleanly adopt the socket while it's occupied. Two paths:
- **Default — at next reboot:** `/tmp` is cleared, the old server is gone, and on boot
  `tmux.service` (lingering) starts the server *before* any login. Zero risk to today's work.
- **Immediate (opt-in only):** if you decide today's 3 sessions are expendable:
  `tmux kill-server` then `systemctl --user start tmux.service`. (Loses the live programs in
  the May-31 8-window session etc. — only if you say so.)

---

## Acceptance test — the real gate (not inference)

Run these once, when convenient. Done = all green.

1. **Structural (immediately after Components 1–3 active):**
   - `loginctl show-user tim -p Linger` → `Linger=yes`
   - both services `ControlGroup` under `…/user@1000.service/app.slice/…`
   - tmux server cgroup is `tmux.service` (NOT `kitty-*.scope`)
2. **Empirical — logout/login (the crash-equivalent on Wayland):**
   - note `systemctl --user show tmux.service -p MainPID` → `PID_before`
   - log out, log back in
   - `systemctl --user is-active tmux.service ssh-agent.service` → `active active`
   - `MainPID` == `PID_before` (server **did not restart**)
   - in a pane: `ssh-add -l` still lists the key you added; `ssh -T <host>` works
3. **Empirical — reboot (proves lingering boot-start; resets agent by design):**
   - reboot, **do not log in graphically yet** (or check from a TTY):
     `systemctl --user is-active tmux.service ssh-agent.service` → `active active`
   - `ssh-add -l` → `no identities` (expected — empty by design); `ssh-add <key>` re-arms it.

Record PID_before/after and outputs here on execution.

## Rollback
- `systemctl --user disable --now tmux.service ssh-agent.service`
- `rm ~/.config/systemd/user/{tmux,ssh-agent}.service ~/.config/environment.d/ssh-agent.conf ~/.config/ssh-agent-local-only`
- `git -C ~/github/mithro/rcfiles revert <zprofile commit>` (or restore the symlink form)
- `loginctl disable-linger tim` (optional — harmless to leave on)
- `systemctl --user daemon-reload`

## Open items / future (not in scope now)
- **Reproducibility:** have `setup.sh` install the two units + `environment.d` + marker on
  `SERVER=0` hosts, so other desktops inherit this. (Would move units into rcfiles.)
- **gcr coexistence:** gcr-ssh-agent stays enabled and harmless; we simply stop *pointing* at
  it. If GUI key-unlock is wanted later, decide gcr-vs-dedicated precedence explicitly.
- **Reboot persistence** of layouts (tmux-resurrect/continuum) — deliberately excluded.
