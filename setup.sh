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

# Set Up my RC files.
SERVER=$(dpkg -l ubuntu-desktop > /dev/null 2>&1; echo $?)

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

	for FP in $(ls $RCFILES/$1/* | grep -v "-"); do
		if [ ! -f $FP ]; then
			continue
		fi

		F=`basename $FP`

		# Remove the old file
		rm -f ~/.$F 2> /dev/null

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
			# Link up the misc_key
			mkdir -p $RCFILES/ssh/keys
			ln -sf ~/.ssh/id_rsa $RCFILES/ssh/keys/misc_key
			break;;
		* ) echo "Please answer yes or no.";;
		esac
	done

	# Fix key permissions
	chmod 600 $RCFILES/ssh/keys/* 2>/dev/null || true

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
		bpython \
		curl \
		git \
		htop \
		ipython3 \
		tmux \
		zsh

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

ack
ssh

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
