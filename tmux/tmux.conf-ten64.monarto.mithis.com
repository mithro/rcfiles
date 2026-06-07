# ten64.monarto gets a distinct navy blue (vs the generic mithis.com blue,
# and distinct from ten64.welland's midnight).
# Concatenated after tmux.conf-mithis.com by setup.sh's linkit(), so these win.
# Dark background -> white foreground for legible status text.
set -g status-fg white
set -g status-bg "#00005f"
