#!/bin/bash
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 noet sts=4 ai:

set -e
set -x

# Vim itself
sudo apt-get -y install \
	vim

if [ "$SERVER" -ne 1 ]; then
	sudo apt-get -y install \
		vim-gnome
fi

sudo apt-get -y install ctags

mkdir -p ~/.vim
mkdir -p ~/.vim/undodir
ln -sf $PWD/vimrc ~/.vimrc

# YouCompleteMe
# ---------------------------------
# Packages needed for YouCompleteMe
sudo apt-get -y install \
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
