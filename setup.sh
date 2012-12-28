#!/bin/bash
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 noet sts=4 ai:

# Set Up my RC files.

RCFILES=~/rcfiles

HOSTNAME=$(hostname -f)
DOMAIN=$(hostname -d)
# Like mithis.com or google.com
BASE_DOMAIN=$(hostname -f | sed -e's/.*\.\(.*\..*\)/\1/')

function linkit {
	if [ ! -d $RCFILES/$1 ]; then
		echo "Must be called with a directory to link up."
		exit 1
	fi

	for FP in $(ls $RCFILES/$1/* | grep -v "-"); do
		F=`basename $FP`

		rm ~/.$F 2> /dev/null

		if [ -f $FP ]; then
			echo $FP "->" ~/.$F
			cat $FP > ~/.$F
		fi

		# Base domain specific settings
		FT=$FP-$DOMAIN
		if [ -f $FT ]; then
			echo $FT "->" ~/.$F
			cat $FT >> ~/.$F
		fi

		# Domain specific settings
		FD=$FP-$DOMAIN
		if [ -f $FD ]; then
			echo $FD "->" ~/.$F
			cat $FD >> ~/.$F
		fi

		# Host specific settings
		FH=$FP-$HOSTNAME
		if [ -f $FH ]; then
			echo $FH "->" ~/.$F
			cat $FH >> ~/.$F
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
	ln -sf $RCFILES/ssh/config ~/.ssh/config

	# Update the keys directory with something.
	while true; do
	    read -p "Get git ssh keys? " yn
	    case $yn in
		[Yy]* )
			(
				cd $RCFILES
				# Clear out any old keys
				if [ ! -d ssh/keys/.git ]; then
					rm -rf ssh/keys
					git submodule init ssh/keys
				fi
				# Update the keys if needed
				git submodule update ssh/keys
			)
			break;;
		[Nn]* ) 
			# Clear out any old keys
			rm -rf ssh/keys
			mkdir -p $RCFILES/ssh/keys

			# Generate a local key if it doesn't exist
			if [ ! -f ~/.ssh/id_rsa ]; then
				ssh-keygen -t rsa -f ~/.ssh/id_rsa
			fi
			# Link up the misc_key
			ln -sf ~/.ssh/id_rsa $RCFILES/ssh/keys/misc_key
			break;;
		* ) echo "Please answer yes or no.";;
	    esac
	done

	# Copy the keys accross
	rm -rf ~/.ssh/keys
	mkdir -p ~/.ssh/keys
	chmod 700 ~/.ssh/keys
	cp $RCFILES/ssh/keys/* ~/.ssh/keys/
	chmod 600 ~/.ssh/keys/*
}

function ppa {
	if [ ! -e /etc/apt/sources.list.d/mithro-personal-lucid.list ]; then
		while true; do
			read -p "Install personal PPA? " yn
			case $yn in
			[Yy]* )
				(
					# Needed for add-apt-repository
					sudo apt-get install python-software-properties
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
	sudo apt-get install \
		tmux \
		vim \
		zsh
}

function crontab {
	echo "Setting up crontab"
}

function precise {
	# Make gtk2.0 apps look less ugly
	# Ubuntu repository apparently has two tools to set GTK-2.0 themes:
	sudo apt-get install \
		gtk-chtheme \
		gtk-theme-switch

	sudo cp -Rv precise/usr /
}

# Fix permissions
umask 022

linkit bash
linkit git
linkit tmux
linkit other
linkit vim

ssh
bin
ppa
pkgs

# Run the Ubuntu version specific setup.
(
	. /etc/lsb-release
	$DISTRIB_CODENAME
)

