#!/bin/bash
# -*- coding: utf-8 -*-
# vim: set ts=4 sw=4 noet sts=4 ai:

set -e
set -x

# Install awesome
sudo apt-get install \
	awesome \
	awesome-extra

# Copy rcfiles
(
	cp -rf config ~/.config/awesome
	# Fix $HOME references
	for FILE in $(find ~/.config/awesome -type f); do
		sed -i -e "s^~/^$HOME/^g" $FILE
	done
)

# Copy files over to set up a "awesome" session selectable from login screen
(
	# Create a temporary directory so we can set the permissions correctly.
	TEMPDIR=$(mktemp -d)
	cp -Rv session/* $TEMPDIR

	# Fix $HOME references
	for FILE in $(find $TEMPDIR -type f); do
		sed -i -e "s^~/^$HOME/^g" $FILE
	done

	# Fix all the permissions / ownership
	find $TEMPDIR -type f -exec chmod 644 \{\} \+
	find $TEMPDIR -type d -exec chmod 755 \{\} \+
	find $TEMPDIR/usr/bin -type f -exec chmod 755 \{\} \+
	sudo chown -R root:root $TEMPDIR

	# Copy config files into /
	sudo cp -Rvaf $TEMPDIR/* /
	# Clean up temporary files
	sudo rm -rf $TEMPDIR
)

# Stop nautilus trying to handle the desktop
gconftool-2 -s -t bool /apps/nautilus/preferences/show_desktop false    # Gnome 2 way
gsettings set org.gnome.desktop.background show-desktop-icons false     # Gnome 3 way

gconftool-2 -s -t bool /desktop/gnome/background/draw_background false  # Gnome 2 way
gsettings set org.gnome.desktop.background draw_background false        # Gnome 3 way

# Make gtk2.0 apps look less ugly
# Ubuntu repository apparently has two tools to set GTK-2.0 themes:
sudo apt-get install \
	gtk-chtheme \
	gtk-theme-switch

# Set up the Canonical indicators
dconf write /com/canonical/indicator/datetime/show-calendar true
dconf write /com/canonical/indicator/datetime/show-clock true
dconf write /com/canonical/indicator/datetime/show-date true
dconf write /com/canonical/indicator/datetime/show-day true
dconf write /com/canonical/indicator/datetime/show-events false
dconf write /com/canonical/indicator/datetime/show-locations true
dconf write /com/canonical/indicator/datetime/locations "['Australia/Sydney', 'UTC', 'Europe/London', 'America/Chicago', 'US/Pacific']"
dconf write /com/canonical/indicator/keyboard/visible false
dconf write /com/ubuntu/sound/allow-amplified-volume true

