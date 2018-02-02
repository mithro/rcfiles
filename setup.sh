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

RCFILES=~/rcfiles

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
	chmod 600 $RCFILES/ssh/keys/*

	# Set up authorized keys if a server
	if [ $SERVER -eq 1 ]; then
		cat ssh/authorized_keys >> ~/.ssh/authorized_keys
		chmod 600 ~/.ssh/authorized_keys
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
		iprint \
		ipython \
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
