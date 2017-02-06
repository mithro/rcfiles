#!/bin/bash
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 noet sts=4 ai:

set -e
set -x

# Vim itself
sudo apt-get install \
	vim

if [ '$SERVER' -ne 1 ]; then
	sudo apt-get install \
		vim-gnome
fi

sudo apt-get install ctags

# YouCompleteMe
# ---------------------------------
# Packages needed for YouCompleteMe
sudo apt-get install \
	cmake \
	libclang-dev \
	libclang-3.8-dev \
	ninja-build \
	python-dev \

# Compile YouCompleteMe
(
	cd bundle/YouCompleteMe/
	./install.py
)
