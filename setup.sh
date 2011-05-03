#!/bin/bash
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 noet sts=4 ai:

# Set Up my RC files.

RCFILES=~/rcfiles

function linkit {
	if [ ! -d $RCFILES/$1 ]; then
		echo "Must be called with a directory to link up."
		exit 1
	fi

	for FP in $RCFILES/$1/*; do
		F=`basename $FP`
		if [ -f $FP ]; then
			echo $FP "->" ~/.$F
			ln -sf $FP ~/.$F
		fi
	done
}

function bin {
	mkdir -p ~/bin
	for FP in $RCFILES/bin/*; do
		F=`basename $FP`
		echo $FP "->" ~/.$F
		ln -sf $FP ~/bin/$F
	done
}

function ssh {
	mkdir -p ~/.ssh
	ln -sf $RCFILES/ssh/config ~/.ssh/config

	# Clear out the keys directory
	rm -rf $RCFILES/ssh/keys
	mkdir $RCFILES/ssh/keys
	# Update the keys directory with something.
	while true; do
	    read -p "Get git ssh keys? " yn
	    case $yn in
		[Yy]* )
			(
				cd $RCFILES
				git submodule init ssh/keys
				git submodule update ssh/keys
				# Fix permissions
				chmod 600 ~/.ssh/keys/*
			)
			break;;
		[Nn]* ) 
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

linkit bash
linkit git
linkit tmux

ssh
bin
