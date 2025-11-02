# rcfiles - Personal Dotfiles Repository

A comprehensive dotfiles repository for setting up development environments across multiple machines with support for hostname-specific configuration overrides.

## Quick Start

```bash
# Clone the repository
mkdir -p ~/github/mithro
git clone git@github.com:mithro/rcfiles.git ~/github/mithro/rcfiles

# Run setup script
cd ~/github/mithro/rcfiles
./setup.sh
```

## Features

- **Hostname-aware configuration**: Override any configuration file per hostname, domain, or base domain
- **Git submodules**: Vim plugins and tools managed as submodules
- **Automatic SSH setup**: Downloads authorized_keys from GitHub, configures ControlMaster
- **Claude Code integration**: Automatically sets up `~/.claude` from separate repository
- **Server vs Desktop detection**: Different configurations for server and desktop installations
- **Modern configurations**: Updated for current versions of tmux, vim, bash, etc.

## Repository Structure

### Configuration Directories

- **`bash/`** - Bash configuration with aliases and environment setup
  - `bash_aliases` - Main alias file
  - `bash/include/` - Additional bash scripts sourced at startup
    - `commands-log` - Logs all bash commands with timestamps
    - `go` - Go language environment setup
    - `kicad-env.sh` - KiCad environment variables

- **`ssh/`** - SSH client configuration
  - `config` - SSH client configuration with ControlMaster, host definitions
  - `keys/` - SSH private keys (separate git repository, not tracked)
  - `authorized_keys` - Additional authorized keys for servers

- **`vim/`** - Vim editor configuration
  - `vimrc` - Main vim configuration
  - `bundle/` - Vim plugins via Pathogen (git submodules)
  - Additional vim configuration files for go, syntastic, statusline

- **`tmux/`** - Tmux terminal multiplexer configuration
  - `tmux.conf` - Main tmux configuration
  - Hostname-specific overrides (e.g., `tmux.conf-mithis.com`)

- **`git/`** - Git version control configuration
  - `gitconfig` - Git global configuration
  - `gitignore` - Global gitignore patterns

- **`bin/`** - Utility scripts and tools
  - Various helper scripts symlinked to `~/bin/`

### Additional Directories

- **`gdb/`** - GDB debugger configuration with gdb-dashboard
- **`awesome/`** - Awesome window manager configuration (desktop only)
- **`python/`** - Python utility libraries
- **`ack/`** - Ack search tool configuration
- **`other/`** - Miscellaneous configuration files
- **`package/`** - Package-related configurations
- **`kicad/`** - KiCad PCB design software configuration
- **`munin/`** - Munin monitoring configuration
- **`xorg/`** - X.org display server configuration
- **`backup/`** - Backup-related scripts
- **`cron/`** - Cron job configurations

## How It Works

### Hostname-Aware Configuration

The `linkit()` function in `setup.sh` implements intelligent configuration linking:

1. For each configuration file (e.g., `tmux/tmux.conf`):
   - Checks for hostname-specific versions:
     - `tmux.conf-$BASE_DOMAIN` (e.g., `tmux.conf-mithis.com`)
     - `tmux.conf-$DOMAIN`
     - `tmux.conf-$HOSTNAME`

2. If overrides exist:
   - Concatenates base file + override files
   - Writes to `~/.tmux.conf`

3. If no overrides:
   - Creates symlink: `~/.tmux.conf` → `~/rcfiles/tmux/tmux.conf`

This allows machine-specific customization while keeping a shared base configuration.

### Setup Process

When you run `./setup.sh`, it:

1. Detects repository location and creates `~/rcfiles` symlink
2. Converts git remote origin from HTTPS to SSH format
3. Initializes all git submodules recursively
4. Creates configuration symlinks to `~/.*` files
5. Installs required packages (ascii, bpython, curl, git, htop, ipython3, mosh, tmux, zsh, gitk)
6. Sets up SSH keys (from private repository or generates local keys)
7. Downloads `authorized_keys` from `github.com/mithro.keys` (servers only)
8. Clones and links `~/.claude` configuration
9. Links utility scripts to `~/bin/`

## Key Features by Component

### Bash

- Command logging to `~/.shell_logs/${HOSTNAME}` with timestamps
- Go environment (`GOPATH=~/gocode`, `GOROOT=~/go`)
- Safety aliases (`rm -i`, `ps fax`)
- Colorized output (ls, grep, ip)
- Directory navigation shortcuts (`..`, `...`, `p` for pushd/popd)

### SSH

- ControlMaster for connection multiplexing (sockets in `~/.ssh/tmp/`)
- Support for older ssh-rsa algorithms (compatibility)
- Pre-configured hosts for GitHub, GitLab, AWS, personal servers
- SOCKS proxy support
- Port forwarding for common services

### Tmux

- Ctrl-A prefix (instead of Ctrl-B)
- Shift-PageUp/PageDown for scrolling
- 10,000 line scrollback history
- Aggressive window resizing
- Custom status bar with hostname and time

### Vim

- Pathogen plugin manager
- Plugins: YouCompleteMe, vim-go, syntastic, tagbar, vim-fugitive, ack.vim, vim-gitgutter
- Language-specific settings (Python, Go, C/C++, RST)
- Persistent undo history
- Spell checking enabled
- Line numbers and syntax highlighting

## Requirements

- Ubuntu/Debian-based Linux system
- Git
- Bash
- Internet connection (for downloading packages and GitHub keys)

## Platform Support

- **Servers**: Detected by absence of `ubuntu-desktop` package
- **Desktops**: Detected by presence of `ubuntu-desktop` package

Desktop installations additionally install:
- gitk (GUI for git)
- Awesome window manager configuration

## License

Most code is licensed under Apache 2.0 or GPL. See individual files for specific license information.

## Private Repositories

This setup integrates with two private repositories:

- **rcfiles-sshkeys**: SSH private keys (`git@github.com:mithro/rcfiles-sshkeys.git`)
- **dot-claude**: Claude Code configuration (`git@github.com:mithro/dot-claude.git`)

These are cloned automatically during setup if you have access.

## Maintenance

To update configurations on an already-set-up machine:

```bash
cd ~/github/mithro/rcfiles
git pull
git submodule update --init --recursive
./setup.sh
```

## Contributing

This is a personal dotfiles repository. Feel free to fork and adapt for your own use.
