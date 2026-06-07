# ten64.welland gets a distinct midnight blue (vs the generic mithis.com blue).
# Concatenated after tmux.conf-mithis.com by setup.sh's linkit(), so these win.
# Dark background -> white foreground for legible status text.
set -g status-fg white
set -g status-bg "#000033"
