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
		for FILE_PART in "$FP-$BASE_DOMAIN" "$FP-$DOMAIN" "$FP-$HOSTNAME"; do
			if [ -f $FILE_PART ]; then
				echo $FILE_PART "->" ~/.$F
				cat $FILE_PART >> $TMP
			fi
		done
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

	# --- Systemd user services for ssh-agent and ssh-agent-mux ---

	# Enable linger so services survive between login sessions
	# May fail if polkit denies the request; non-fatal since services
	# still work within active sessions.
	loginctl enable-linger "$USER" || echo "Warning: loginctl enable-linger failed (may need sudo)" >&2

	# Install ssh-agent wrapper script (symlink so updates come from repo)
	ln -sf "$RCFILES/ssh/systemd/ssh-agent-start.sh" ~/bin/ssh-agent-start.sh

	# Install ssh-agent service unit (symlink so updates come from repo)
	mkdir -p ~/.config/systemd/user
	ln -sf "$RCFILES/ssh/systemd/ssh-agent.service" ~/.config/systemd/user/ssh-agent.service

	# Install ssh-agent-mux service via its built-in installer
	# Requires XDG_RUNTIME_DIR for dbus access
	XDG_RUNTIME_DIR="/run/user/$(id -u)" ~/bin/ssh-agent-mux --install-service \
		|| echo "Warning: ssh-agent-mux --install-service failed" >&2

	# Install drop-in override (symlink directory so updates come from repo)
	ln -sf "$RCFILES/ssh/systemd/ross-williams-ssh-agent-mux.service.d" \
		~/.config/systemd/user/ross-williams-ssh-agent-mux.service.d

	# Reload and enable
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user daemon-reload \
		|| echo "Warning: systemctl daemon-reload failed" >&2
	XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user enable \
		ssh-agent.service ross-williams-ssh-agent-mux.service \
		|| echo "Warning: systemctl enable failed" >&2
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

bash_completions
ack
gh
uv_install
ssh_agent_mux
ssh
claude

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
