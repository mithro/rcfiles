# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a personal dotfiles repository (rcfiles) containing configuration files and utilities for setting up a development environment across multiple machines. The repository uses a hostname-aware linking system to support machine-specific configuration overrides.

## Repository Location

The repository is expected to be cloned at `~/github/mithro/rcfiles` with a symlink at `~/rcfiles` pointing to it. This structure allows:
- The repository to be organized within the `~/github/mithro/` directory structure
- Backward compatibility with scripts that reference `~/rcfiles`
- The `setup.sh` script automatically creates the `~/rcfiles` symlink if it doesn't exist

To clone the repository:

```bash
mkdir -p ~/github/mithro
git clone <repository-url> ~/github/mithro/rcfiles
```

## Setup and Installation

The primary setup script is `setup.sh` at the repository root. To set up the environment:

```bash
cd ~/github/mithro/rcfiles
./setup.sh
```

This script:
1. Detects the repository location and creates `~/rcfiles` symlink if needed
2. Converts git remote origin from HTTPS to SSH format (github.com)
3. Initializes all git submodules recursively
4. Creates symlinks for configuration files from various directories (bash, git, vim, tmux, ssh, etc.) to `~/.{filename}`
5. Supports hostname-specific configuration overrides using suffixes like `-$HOSTNAME`, `-$DOMAIN`, or `-$BASE_DOMAIN`
6. Installs required packages (ascii, bpython, curl, git, htop, ipython3, mosh, tmux, zsh, and gitk for desktop systems)
7. Sets up SSH keys (either from a private git repository or generates local keys)
8. Clones and links `~/.claude` to `~/github/mithro/dot-claude` repository
9. Links utilities from `bin/` to `~/bin/`

## Architecture

### Configuration Linking System

The `linkit()` function in `setup.sh` implements a hostname-aware configuration system:
- Base configuration files are in directories like `bash/`, `git/`, `tmux/`, `vim/`
- Files can have hostname-specific overrides with suffixes: `-$BASE_DOMAIN`, `-$DOMAIN`, or `-$HOSTNAME`
- If override files exist, they are appended to the base configuration
- Otherwise, the base file is symlinked directly to `~/.$FILENAME`
- An optional `<base>-postfix` file is appended **last**, after all host-specific parts (generated order: base → host parts → postfix). Used e.g. for the tmux plugin loader, which must load after host `status-right` overrides.

### Directory Structure

- `bash/`: Bash configuration with main `bash_aliases` file and additional scripts in `bash/include/`
- `git/`: Git configuration (`gitconfig`, `gitignore`)
- `vim/`: Vim configuration with Pathogen plugin manager and multiple plugins as git submodules in `vim/bundle/`
- `tmux/`: Tmux configuration with hostname-specific overrides; TPM vendored at `tmux/plugins/tpm` (plugins clone to `~/.tmux/plugins/`); plugin block in `tmux/tmux.conf-postfix` (appended by linkit after host parts)
- `ssh/`: SSH configuration with control socket persistence and hostname-specific settings
- `kitty/`: kitty terminal config; `ssh.conf` (symlinked to `~/.config/kitty/ssh.conf` by `kitty_conf()`) sets `share_connections no` so the ssh kitten doesn't override the `~/.ssh/config` ControlPath with its own `-o ControlPath=$XDG_RUNTIME_DIR/kssh-*` command-line injection
- `bin/`: Utility scripts symlinked to `~/bin/`
- `gdb/`: GDB configuration including gdb-dashboard submodule
- `awesome/`: Awesome window manager configuration (for desktop systems)
- `python/`: Python utility libraries
- `other/`, `package/`, `ack/`, `kicad/`, `munin/`, `xorg/`: Additional configuration directories

### Key Features

**Bash Environment:**
- Command logging: All bash commands are logged to `~/.shell_logs/${HOSTNAME}` with timestamps (see `bash/include/commands-log`)
- Go environment setup in `bash/include/go` with `GOPATH=~/gocode` and `GOROOT=~/go`
- Extensive aliases in `bash/bash_aliases` including safer rm, better ls/ps, git, and Google-specific workflows

**SSH Configuration:**
- Uses ControlMaster for connection multiplexing with sockets in `~/.ssh/tmp/`
- Inside kitty, `bash/include/kitty` aliases ssh to `kitten ssh`; `kitty/ssh.conf` disables the kitten's own connection sharing so the same `~/.ssh/tmp/` ControlPath applies there too
- Enables older ssh-rsa algorithms for compatibility
- Defines many host-specific configurations for personal servers, GitHub, GitLab, AWS, and TimVideos infrastructure
- SSH keys stored in `ssh/keys/` (not tracked in main repository)
- On server installations, authorized_keys are downloaded from `github.com/mithro.keys` with local `ssh/authorized_keys` appended if present
- **Agent multiplexing**: `ssh-agent-mux` provides a stable `SSH_AUTH_SOCK` (`~/.ssh/agent/mux.sock`) that multiplexes a local ssh-agent with the SSH-forwarded agent, surviving tmux reattach and SSH reconnect. Config in `ssh/ssh-agent-mux.toml`, startup logic in `tmux/zprofile`, ssh-add wrapper in `bin/ssh-add`. See `ssh/README.md` for architecture details.

**Tmux Session Persistence:**
- TPM (tmux plugin manager) is a pinned git submodule at `tmux/plugins/tpm`; managed plugins live outside the repo in `~/.tmux/plugins/` via `TMUX_PLUGIN_MANAGER_PATH`
- go-tmux-saver (Go, installed from the welland apt repo) owns persistence: periodic saves via its user timer, restore on server start via `tmux-server.service` ExecStartPost, `prefix+M-s` save / `prefix+M-r` restore from its setup-managed `~/.config/go-tmux-saver/tmux.conf` (sourced last from the postfix)
- tmux-resurrect stays as the manual-only fallback (`prefix+M-S` save / `prefix+M-R` restore); tmux-continuum was removed 2026-08-29 (redundant autosave, and its restore re-created dead per-login grouped clones)
- Saves capture pane scrollback and relaunch whitelisted programs (resurrect defaults plus ssh, mosh-client, claude)
- The plugin block ships in `tmux/tmux.conf-postfix`, which `linkit` appends after the base config and all host-specific parts, so the plugin loader and the go-tmux-saver bindings run last
- `setup.sh` installs plugins headlessly via `tmux_plugins()`
- `setup.sh` installs go-tmux-saver from its signed apt repo and runs `go-tmux-saver setup install`/`update` via `tmux_saver()` (after `tmux_persistence()`, which owns `tmux-server.service`)

**Vim Configuration:**
- Uses Pathogen for plugin management (`vim/bundle/vim-pathogen`)
- Includes plugins: YouCompleteMe, vim-go, syntastic, tagbar, vim-fugitive, ack.vim, vim-gitgutter
- Language-specific settings for Python, Go, C/C++, and RST
- Persistent undo in `~/.vim/undodir`
- Custom statusline, go configuration, and syntastic settings

**Claude Code Configuration:**
- `~/.claude` is symlinked to `~/github/mithro/dot-claude` repository
- Contains Claude Code settings, hooks, and custom configurations
- Automatically cloned and symlinked during setup

**Shared Playwright MCP server (`playwright_mcp()`):**
- One sandboxed Playwright MCP server per host instead of the official plugin's per-session `npx @playwright/mcp@latest` (which left 13 idle copies on ten64)
- `systemd/user/playwright-mcp.socket` listens on `127.0.0.1:26271`; the first connection starts `playwright-mcp-proxy.service` (systemd-socket-proxyd), which pulls in `playwright-mcp.service` on `:26371`; both stop after 30 min idle (`StopWhenUnneeded=`)
- Pinned version (`PLAYWRIGHT_MCP_VERSION` in `setup.sh`) installed with npm into `~/.local/share/playwright-mcp`, with its own Chromium in `~/.cache/playwright-mcp/browsers`; bumping the version restarts a running server
- The server is sandboxed: cgroup limits (MemoryMax 2G, CPUQuota 200%, TasksMax 1024), a read-only system and home with only `~/.cache/playwright-mcp`, `~/local` and `~/github` writable, and NoNewPrivileges
- `setup.sh` registers it as user-scope HTTP server `playwright` (`claude mcp add`) and disables `playwright@claude-plugins-official`
- Traps: `--allowed-hosts` must name the front-door port (`:26271`, the proxy passes the Host header through), and `XDG_CACHE_HOME` must point into the writable cache (Playwright writes `ms-playwright/b` there, not under `PLAYWRIGHT_BROWSERS_PATH`)
- `bin/wait-listen.py` is the shared `ExecStartPost=` helper that holds the unit in "starting" until its port accepts connections
- Port plan, identical on every host: front doors `2627x` (M-C-P on a phone keypad), backends front + 100 — playwright 26271/26371, playwright-stealth 26272/26372, netgear 26273/26373 (below the Linux ephemeral range and clear of 8xxx dev servers)
- `mcp_socket_units NAME [EXTRA]` installs any socket → proxy → server stack and, when the unit text (or EXTRA, the pinned version) changed since the last run (`~/.local/state/rcfiles/NAME.fingerprint`), restarts the socket and stops the proxy + server — a running socket/server otherwise keeps its OLD ports. `claude_mcp_http NAME URL` registers or re-points a user-scope HTTP MCP server
- Not truly on-demand: every open Claude session holds a standalone MCP GET (SSE) stream, so `--exit-idle-time` only fires once no session is open at all

**Shared headed ("stealth") Playwright MCP server (`playwright_stealth_mcp()`):**
- Only on hosts with `/usr/bin/google-chrome` plus Chrome Remote Desktop and/or TigerVNC (desktop). Same pattern on `127.0.0.1:26272` → `:26372`, same pinned install, drives the real headed google-chrome, `--isolated` (one Chrome, one context per session)
- `bin/playwright-mcp-pick-display.py` (the `ExecStart=` wrapper) picks CRD display `:20` unless another Claude session already has something on `:20`, else TigerVNC `:99`; a human connected over CRD is deliberately not a reason to fall back
- Contexts are seeded from `~/.config/playwright-mcp/stealth-storage-state.json` (created empty, 0600, never committed); `bin/playwright-mcp-export-storage-state.js` fills it from on-disk Chrome profiles

**Netgear switch MCP server (`ngsw_mcp()`):**
- Runs only on hosts with `/usr/bin/ngsw-mcp` (python3-netgear-switch-library; in practice ten64). Uses the same socket → proxy → server pattern: `ngsw-mcp.socket` on `127.0.0.1:26273`, the server on `:26373`, used by dot-claude's `netgear-switch` plugin
- The site config (`~/.config/ngsw/inventory.toml`, `get-cred.sh`) is deliberately **not** in this public repo
- Not sandboxed like Playwright: `get-cred.sh` resolves switch passwords through `sudo` (gdoc2netcfg), which `NoNewPrivileges=` would break

## Git Submodules

The repository heavily uses git submodules for vim plugins and other tools. All submodules are defined in `.gitmodules`. After cloning, always run:

```bash
git submodule sync --recursive
git submodule update --recursive --init
```

## Testing Changes

When modifying configuration files:
1. Test the configuration file syntax if applicable (e.g., `bash -n` for bash scripts, `vim -u NONE -c 'source vimrc'` for vimrc)
2. For the linking system, verify that hostname-specific overrides work by checking if files with suffixes are properly concatenated
3. The setup script uses `set -e` and `set -x`, so any errors will cause it to exit

## Important Notes

- The repository is designed to be located at `~/github/mithro/rcfiles` with `~/rcfiles` as a symlink for backward compatibility
- The repository supports both server and desktop installations (detected via presence of `ubuntu-desktop` package)
- SSH keys are managed separately in a private repository (`rcfiles-sshkeys`) that must be cloned to `ssh/keys/`
- Configuration files may contain personal server hostnames and network topology
- The repository was designed for Ubuntu/Debian systems (uses apt-get, dpkg)
- If running from the correct location, `setup.sh` will automatically create the `~/rcfiles` symlink
