#! /bin/sh
xrandr --newmode "big"  193.25  1920 2056 2256 2592  1200 1203 1209 1245 -hsync +vsync
xrandr --addmode VGA1 big
xrandr --output VGA1 --mode big
xrandr --output VGA1 --right-of LVDS1
xrandr --output LVDS1 --mode 1280x800 --panning 1280x800
pkill xcursorclamp
~/bin/xcursorclamp &
