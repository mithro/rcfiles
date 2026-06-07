# ten64.monarto gets a distinct navy blue (vs the generic mithis.com blue,
# and distinct from ten64.welland's midnight).
# Concatenated after tmux.conf-mithis.com by setup.sh's linkit(), so these win.
# Dark background -> white foreground for legible status text.
set -g status-fg white
set -g status-bg "#00005f"

# Activity/bell window flags default to `reverse`, which flips against the
# white fg above and turns the highlight bright white. Pin them to a black
# background so the highlight stays dark (white text on black).
set -gw window-status-activity-style "fg=white,bg=black"
set -gw window-status-bell-style "fg=white,bg=black"
