#!/bin/bash
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 noet sts=4 ai:

set -e
set -x

# Vim itself
sudo apt-get -y install \
	vim

if [ z"$SERVER" != z1 ]; then
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
	cargo \
	cmake \
	libclang-*-dev \
	ninja-build \
	python-dev \
	python3-dev \

# Compile YouCompleteMe
(
	cd bundle/YouCompleteMe/
	python3 ./install.py \
		--clang-completer \
		--gocode-completer \

#		--racer-completer \
)
