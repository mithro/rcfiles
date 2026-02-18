# mithis.com hosts are blue
set -g status-fg black
set -g status-bg blue

# Show hostname with location (e.g. ten64.monarto) instead of just short hostname
set -g status-right '#(hostname -f | sed "s/\.mithis\.com$//") #(TZ="Australia/Adelaide" date +"%I:%M%p") '
