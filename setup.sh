#!/bin/bash
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 noet sts=4 ai:

set -e
set -x

# Setup git submodules.
git submodule sync --recursive
git submodule update --recursive --init
git submodule foreach \
	git submodule update --recursive --init

# Convert git remote origin to SSH if it's using HTTPS
CURRENT_ORIGIN=$(git remote get-url origin)
if [[ "$CURRENT_ORIGIN" =~ ^https://github.com/(.*)$ ]]; then
	NEW_ORIGIN="git@github.com:${BASH_REMATCH[1]}"
	echo "Converting remote origin from HTTPS to SSH: $NEW_ORIGIN"
	git remote set-url origin "$NEW_ORIGIN"
fi

# Set Up my RC files.
if dpkg -l ubuntu-desktop > /dev/null; then
	SERVER=0
else
	SERVER=1
fi

# Detect repository location and ensure ~/rcfiles symlink exists
# The repository can be at ~/github/mithro/rcfiles with ~/rcfiles as a symlink
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RCFILES_TARGET=~/github/mithro/rcfiles
RCFILES=~/rcfiles

# If we're running from ~/github/mithro/rcfiles and ~/rcfiles doesn't exist or isn't a symlink to the right place
if [ "$SCRIPT_DIR" = "$HOME/github/mithro/rcfiles" ]; then
	if [ ! -e "$RCFILES" ]; then
		echo "Creating symlink: $RCFILES -> $RCFILES_TARGET"
		ln -s "$RCFILES_TARGET" "$RCFILES"
	elif [ ! -L "$RCFILES" ] || [ "$(readlink -f "$RCFILES")" != "$RCFILES_TARGET" ]; then
		echo "Warning: $RCFILES exists but is not a symlink to $RCFILES_TARGET"
		echo "Please manually fix this before continuing."
		exit 1
	fi
fi

# Verify RCFILES directory exists and is accessible
if [ ! -d "$RCFILES" ]; then
	echo "Error: $RCFILES directory not found!"
	exit 1
fi

HOSTNAME=$(hostname -f)
DOMAIN=$(hostname -d)
# Like mithis.com or google.com
BASE_DOMAIN=$(hostname -f | sed -e's/.*\.\(.*\..*\)/\1/')

# linkit(DIRECTORY)
function linkit {
	if [ ! -d $RCFILES/$1 ]; then
		echo "Must be called with a directory to link up."
		exit 1
	fi

	for FP in "$RCFILES/$1"/*; do
		if [ ! -f "$FP" ]; then
			continue
		fi
		# Skip files with hyphens in the name
		if [[ "$(basename "$FP")" == *"-"* ]]; then
			continue
		fi

		F=`basename $FP`

		# Remove the old file
		rm -f ~/.$F

		# Generate a new file
		# FIXME: Check we are not overriding any local changes!
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
		# Optional postfix: appended LAST, after host-specific parts (e.g.
		# config that must come after host overrides, like a plugin loader
		# that reads the final status-right). See docs spec section 4.
		if [ -f "$FP-postfix" ]; then
			echo "$FP-postfix" "->" ~/.$F
			cat "$FP-postfix" >> $TMP
		fi
		echo -n $FP "->" ~/.$F
		if [ -f $TMP ]; then
			echo " (generated)"
			cat $FP $TMP > ~/.$F
			rm $TMP || true
		else
			echo " (linked)"
			ln -s $FP ~/.$F
		fi
	done
}

function bin {
	mkdir -p ~/bin
	for FP in $RCFILES/bin/*; do
		F=`basename $FP`
		echo $FP "->" ~/bin/$F
		ln -sf $FP ~/bin/$F
	done
}

function bash_completions {
	# Symlink vendored completions into the XDG location bash-completion's
	# lazy loader (_completion_loader) checks first.
	# Yields gracefully if the system package later ships the same file.
	local DEST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/bash-completion/completions"
	mkdir -p "$DEST_DIR"

	for FP in "$RCFILES"/bash/completion/*; do
		[ -f "$FP" ] || continue
		local NAME
		NAME=$(basename "$FP")

		# Skip helper scripts and docs — only command-named files are completions.
		case "$NAME" in
			update-*|README*|*.md) continue;;
		esac

		local DEST="$DEST_DIR/$NAME"
		local SYS="/usr/share/bash-completion/completions/$NAME"

		if [ -f "$SYS" ]; then
			echo "$SYS exists; removing local override $DEST"
			rm -f "$DEST"
			continue
		fi

		echo "$FP -> $DEST"
		ln -sf "$FP" "$DEST"
	done
}

function ssh {
	mkdir -p ~/.ssh
	mkdir -p ~/.ssh/tmp
	if [ ! -e ~/.ssh/config ]; then
		ln -sf $RCFILES/ssh/config ~/.ssh/config
	fi
	if [ ! -e ~/.ssh/keys ]; then
		ln -sf $RCFILES/ssh/keys ~/.ssh/keys
	fi

	# Update the keys directory with something.
	while true; do
		read -p "Get git ssh keys? " yn
		case $yn in
		[Yy]* )
			(
				cd $RCFILES
				# Clear out any old keys
				if [ ! -d ssh/keys/.git ]; then
					rm -rf ssh/keys || true
					git clone git+ssh://github.com/mithro/rcfiles-sshkeys.git ssh/keys
				fi
			)
			break;;
		[Nn]* )
			# Generate a local key if it doesn't exist
			if [ ! -f ~/.ssh/id_rsa ]; then
				ssh-keygen -t rsa -f ~/.ssh/id_rsa
			fi
			# Link up the misc_key and new_misc_key
			mkdir -p $RCFILES/ssh/keys
			ln -sf ~/.ssh/id_rsa $RCFILES/ssh/keys/misc_key
			ln -sf ~/.ssh/id_rsa $RCFILES/ssh/keys/new_misc_key
			break;;
		* ) echo "Please answer yes or no.";;
		esac
	done

	# Fix key permissions
	if ls "$RCFILES"/ssh/keys/* > /dev/null; then
		chmod 600 "$RCFILES"/ssh/keys/*
	fi

	# Set up authorized keys if a server
	if [ $SERVER -eq 1 ]; then
		echo "Setting up authorized_keys for server..."

		# Download authorized keys from GitHub
		if curl -fsSL https://github.com/mithro.keys -o ~/.ssh/authorized_keys.tmp; then
			echo "Downloaded authorized_keys from github.com/mithro.keys"

			# Append local authorized_keys if it exists
			if [ -f $RCFILES/ssh/authorized_keys ]; then
				echo "Appending local authorized_keys"
				cat $RCFILES/ssh/authorized_keys >> ~/.ssh/authorized_keys.tmp
			fi

			# Move to final location
			mv ~/.ssh/authorized_keys.tmp ~/.ssh/authorized_keys
			chmod 600 ~/.ssh/authorized_keys
			echo "authorized_keys setup complete"
		else
			echo "Warning: Failed to download from github.com/mithro.keys"
			# Fallback to local file if download fails
			if [ -f $RCFILES/ssh/authorized_keys ]; then
				echo "Using local authorized_keys as fallback"
				cat $RCFILES/ssh/authorized_keys >> ~/.ssh/authorized_keys
				chmod 600 ~/.ssh/authorized_keys
			else
				echo "Error: No authorized_keys available"
			fi
		fi
	fi
}

function ppa {
	if [ ! -e /etc/apt/sources.list.d/mithro-personal-lucid.list ]; then
		while true; do
			read -p "Install personal PPA? " yn
			case $yn in
			[Yy]* )
				(
					# Needed for add-apt-repository
					sudo apt-get -y install python-software-properties
					sudo add-apt-repository ppa:mithro/personal
					sudo bash -c "cat >> /etc/apt/preferences" <<EOF
Explanation: Give the my personal PPA a higher priority than anything else
Package: *
Pin: release o=LP-PPA-mithro-personal
Pin-Priority: 2000
EOF
					sudo apt-get update
					sudo apt-get upgrade
				)
				break;;
			[Nn]* )
				break;;
			* ) echo "Please answer yes or no.";;
			esac
		done
	fi
}

function pkgs {
	sudo apt-get -y install \
		ascii \
		bash-completion \
		bpython \
		curl \
		git \
		htop \
		ipython3 \
		jq \
		kitty-terminfo \
		mosh \
		python3-dbus \
		python3-gi \
		shellcheck \
		tmux \
		zsh

	# Core dump capture for debugging ssh-agent-mux crashes (soft dependency)
	sudo apt-get -y install systemd-coredump || true

#		iprint \

	if [ $SERVER -ne 1 ]; then
		sudo apt-get -y install \
			gitk
	fi
}

function tmux_plugins {
	local TPM_INSTALL="$RCFILES/tmux/plugins/tpm/bin/install_plugins"
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

function crontab {
	echo "Setting up crontab"
}

function ack {
    curl https://beyondgrep.com/ack-2.22-single-file > ~/bin/ack && chmod 0755 ~/bin/ack
}

function gh {
	# Install GitHub CLI (gh) from official repository
	# Check if gh is already installed
	if command -v gh > /dev/null; then
		echo "gh is already installed, skipping..."
		return 0
	fi

	echo "Installing GitHub CLI (gh)..."

	# Add GitHub CLI repository
	sudo mkdir -p -m 755 /etc/apt/keyrings
	curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
	sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null

	# Update and install
	sudo apt-get update
	sudo apt-get -y install gh
}

function uv_install {
	# Install uv Python package manager from astral.sh
	# Check if uv is already installed
	if command -v uv > /dev/null; then
		echo "uv is already installed, skipping..."
		return 0
	fi

	echo "Installing uv..."
	curl -LsSf https://astral.sh/uv/install.sh | sh
}

function ssh_agent {
	# The local ssh-agent, as a lingering systemd --user service, on ALL hosts.
	# This is "the ssh-agent": on servers it sits behind ssh-agent-mux; on
	# laptops/desktops it is fronted by the tmux server (see tmux_persistence).
	# ssh-agent-start.sh binds ~/.ssh/agent/local.<pid>.sock and maintains the
	# stable ~/.ssh/agent/local.sock symlink that ssh/bin/ssh-add targets.
	mkdir -p ~/bin ~/.config/systemd/user ~/.ssh/agent

	# Linger so the agent (and the tmux server) survive between login sessions.
	loginctl enable-linger "$USER" || echo "Warning: loginctl enable-linger failed (may need sudo)" >&2

	ln -sf "$RCFILES/ssh/systemd/ssh-agent-start.sh" ~/bin/ssh-agent-start.sh
	ln -sf "$RCFILES/ssh/systemd/ssh-agent.service" ~/.config/systemd/user/ssh-agent.service
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user daemon-reload \
		|| echo "Warning: systemctl daemon-reload failed" >&2
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user enable ssh-agent.service \
		|| echo "Warning: systemctl enable ssh-agent.service failed" >&2
}

function ssh_agent_mux {
	# Install ssh-agent-mux from cached binary in repo
	local ARCH
	ARCH=$(dpkg --print-architecture)
	local CACHED_BIN="$RCFILES/ssh/bin/ssh-agent-mux-linux-${ARCH}"

	if [ ! -f "$CACHED_BIN" ]; then
		echo "Warning: No cached ssh-agent-mux binary for ${ARCH}, skipping"
		echo "To add support: $RCFILES/ssh/bin/update-ssh-agent-mux"
		return 0
	fi

	echo "Installing ssh-agent-mux from repo cache..."
	cp "$CACHED_BIN" ~/bin/ssh-agent-mux
	chmod 755 ~/bin/ssh-agent-mux

	# Set up config symlink
	mkdir -p ~/.config/ssh-agent-mux
	ln -sf "$RCFILES/ssh/ssh-agent-mux.toml" ~/.config/ssh-agent-mux/ssh-agent-mux.toml

	# Create agent socket directory
	mkdir -p ~/.ssh/agent

	# --- ssh-agent-mux SERVICE (servers only) ---
	# The mux aggregates the local agent + a forwarded agent into one socket.
	# On a laptop/desktop the local agent is fronted by the persistent tmux
	# server (tmux_persistence) and needs no mux. The local ssh-agent.service
	# itself is installed for ALL hosts by ssh_agent(), called before this.
	if [ $SERVER -eq 0 ]; then
		echo "Desktop host: skipping ssh-agent-mux service (tmux fronts the agent)"
		return 0
	fi

	# Install ssh-agent-mux service via its built-in installer
	# Requires XDG_RUNTIME_DIR for dbus access
	XDG_RUNTIME_DIR="/run/user/$(id -u)" ~/bin/ssh-agent-mux --install-service \
		|| echo "Warning: ssh-agent-mux --install-service failed" >&2

	# Install drop-in override (symlink directory so updates come from repo)
	ln -sf "$RCFILES/ssh/systemd/ross-williams-ssh-agent-mux.service.d" \
		~/.config/systemd/user/ross-williams-ssh-agent-mux.service.d

	# Reload and enable the mux service (ssh-agent.service is enabled by ssh_agent).
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user daemon-reload \
		|| echo "Warning: systemctl daemon-reload failed" >&2
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user enable \
		ross-williams-ssh-agent-mux.service \
		|| echo "Warning: systemctl enable failed" >&2
}

function clipboard_over_ssh {
	# Install clipboard-over-ssh from cached binary in repo
	local ARCH
	ARCH=$(dpkg --print-architecture)
	local CACHED_BIN="$RCFILES/ssh/bin/clipboard-over-ssh-linux-${ARCH}"

	if [ ! -f "$CACHED_BIN" ]; then
		echo "Warning: No cached clipboard-over-ssh binary for ${ARCH}, skipping"
		echo "To add support: $RCFILES/ssh/bin/update-clipboard-over-ssh"
		return 0
	fi

	cp "$CACHED_BIN" ~/bin/clipboard-over-ssh
	chmod 755 ~/bin/clipboard-over-ssh

	if [ $SERVER -eq 1 ]; then
		# Remote/server: install xclip/wl-paste symlinks
		~/bin/clipboard-over-ssh install-remote
	else
		# Desktop/local: install systemd socket-activated server
		~/bin/clipboard-over-ssh install-local
	fi
}

function claude {
	DOT_CLAUDE_DIR=~/github/mithro/dot-claude

	# Clone dot-claude repository if it doesn't exist
	if [ ! -d "$DOT_CLAUDE_DIR" ]; then
		echo "Cloning dot-claude repository..."
		mkdir -p ~/github/mithro
		git clone git@github.com:mithro/dot-claude.git "$DOT_CLAUDE_DIR"
	fi

	# Create ~/.claude symlink if it doesn't exist
	if [ ! -e ~/.claude ]; then
		echo "Creating ~/.claude symlink to $DOT_CLAUDE_DIR"
		ln -s "$DOT_CLAUDE_DIR" ~/.claude
	elif [ ! -L ~/.claude ]; then
		echo "Warning: ~/.claude exists but is not a symlink"
		echo "Please manually fix this before continuing."
	fi

	# claude-notify-gnome provides the desktop notification hook referenced
	# by dot-claude's settings.json. Clone it so the hooks resolve, and (on
	# desktops) install its GNOME focus systemd user service.
	NOTIFY_DIR=~/github/mithro/claude-notify-gnome
	if [ ! -d "$NOTIFY_DIR" ]; then
		echo "Cloning claude-notify-gnome repository..."
		mkdir -p ~/github/mithro
		git clone git@github.com:mithro/claude-notify-gnome.git "$NOTIFY_DIR"
	fi
	if [ $SERVER -ne 1 ] && [ -x "$NOTIFY_DIR/install_service.sh" ]; then
		( cd "$NOTIFY_DIR" && ./install_service.sh ) || echo "Warning: claude-notify-gnome focus service not installed"
	fi
}

function tmux_persistence {
	# All hosts. Run the tmux server (and the ssh-agent it fronts) as lingering
	# systemd --user units so they survive any login/logout, SSH disconnect, or
	# Wayland/compositor crash — instead of as children of the terminal/SSH
	# session that launched them. (A session-scoped tmux server is killed when
	# that login session's scope is torn down on logout, regardless of linger.)
	# See docs/plans/2026-06-03-tmux-ssh-agent-persistence.md

	# Window 0 of the default tmux session tails this. linkit skips it (the
	# hyphen in the name collides with the host-variant convention), so link it
	# explicitly here.
	ln -sf "$RCFILES/tmux/tmux-help" ~/.tmux-help

	# tmux.service pins SSH_AUTH_SOCK at a stable per-host "front" socket, so every
	# pane inherits the right agent regardless of bash/zsh login shell. The unit is
	# identical on every host; only this symlink's target is host-specific, keyed
	# on the SAME mux-or-not condition that gates ssh_agent_mux:
	#   - servers (ssh-agent-mux present): front -> mux.sock   (local + forwarded)
	#   - laptops/desktops (no mux):       front -> local.sock (local agent only)
	mkdir -p ~/.ssh/agent
	if [ $SERVER -eq 1 ]; then
		ln -sf mux.sock ~/.ssh/agent/front.sock
	else
		ln -sf local.sock ~/.ssh/agent/front.sock
	fi

	mkdir -p ~/.config/systemd/user
	ln -sf "$RCFILES/systemd/user/tmux.service" ~/.config/systemd/user/tmux.service
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user daemon-reload || true

	# Ubuntu's stock ssh-agent.socket (openssh_agent) is redundant and would set a
	# competing SSH_AUTH_SOCK; mask it so our agent stack (local agent, plus the
	# mux on servers) is the only ssh-agent. It is enabled at global scope, so mask
	# (not just disable) is required to keep it from starting at boot.
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user mask ssh-agent.socket || true

	# Enable tmux.service but do NOT start it now: an existing tmux server may
	# hold the default socket. It activates cleanly at the next boot/login.
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user enable tmux.service || true
}

# Fix permissions
umask 022

bin

linkit ack
linkit bash
if [ ! -d ~/.shell_logs ]; then
	mkdir ~/.shell_logs
fi

linkit git
linkit other
linkit package
linkit tmux
linkit vim

pkgs

tmux_plugins

bash_completions
ack
gh
uv_install
ssh_agent
ssh_agent_mux
clipboard_over_ssh
ssh
claude
tmux_persistence

if [ $SERVER -ne 1 ]; then
	(
		cd awesome
		./setup.sh
	)
fi

# Run the Ubuntu version specific setup.
#(
#	. /etc/lsb-release
#	$DISTRIB_CODENAME
#)
