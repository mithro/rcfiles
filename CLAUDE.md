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
2. Initializes all git submodules recursively
3. Creates symlinks for configuration files from various directories (bash, git, vim, tmux, ssh, etc.) to `~/.{filename}`
4. Supports hostname-specific configuration overrides using suffixes like `-$HOSTNAME`, `-$DOMAIN`, or `-$BASE_DOMAIN`
5. Installs required packages (ascii, bpython, curl, git, htop, ipython3, tmux, zsh, and gitk for desktop systems)
6. Sets up SSH keys (either from a private git repository or generates local keys)
7. Links utilities from `bin/` to `~/bin/`

## Architecture

### Configuration Linking System

The `linkit()` function in `setup.sh:24-60` implements a hostname-aware configuration system:
- Base configuration files are in directories like `bash/`, `git/`, `tmux/`, `vim/`
- Files can have hostname-specific overrides with suffixes: `-$BASE_DOMAIN`, `-$DOMAIN`, or `-$HOSTNAME`
- If override files exist, they are appended to the base configuration
- Otherwise, the base file is symlinked directly to `~/.$FILENAME`

### Directory Structure

- `bash/`: Bash configuration with main `bash_aliases` file and additional scripts in `bash/include/`
- `git/`: Git configuration (`gitconfig`, `gitignore`)
- `vim/`: Vim configuration with Pathogen plugin manager and multiple plugins as git submodules in `vim/bundle/`
- `tmux/`: Tmux configuration with hostname-specific overrides
- `ssh/`: SSH configuration with control socket persistence and hostname-specific settings
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
- Enables older ssh-rsa algorithms for compatibility
- Defines many host-specific configurations for personal servers, GitHub, GitLab, AWS, and TimVideos infrastructure
- SSH keys stored in `ssh/keys/` (not tracked in main repository)
- On server installations, authorized_keys are downloaded from `github.com/mithro.keys` with local `ssh/authorized_keys` appended if present

**Vim Configuration:**
- Uses Pathogen for plugin management (`vim/bundle/vim-pathogen`)
- Includes plugins: YouCompleteMe, vim-go, syntastic, tagbar, vim-fugitive, ack.vim, vim-gitgutter
- Language-specific settings for Python, Go, C/C++, and RST
- Persistent undo in `~/.vim/undodir`
- Custom statusline, go configuration, and syntastic settings

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
