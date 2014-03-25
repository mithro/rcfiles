
# Stop nautalis trying to handle the desktop
gconftool-2 -s -t bool /apps/nautilus/preferences/show_desktop false    # Gnome 2 way
gsettings set org.gnome.desktop.background show-desktop-icons false     # Gnome 3 way

#gconftool-2 -s -t bool /desktop/gnome/background/draw_background false  # Gnome 2 way
#gsettings set org.gnome.desktop.background draw_background false        # Gnome 3 way


