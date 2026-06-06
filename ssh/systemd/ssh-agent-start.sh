#!/bin/sh
# Wrapper for ssh-agent that implements per-PID socket + atomic symlink.
# Used by ssh-agent.service (systemd user unit).
#
# Each instance gets a unique local.<pid>.sock, with local.sock as an
# atomic symlink to the current one. This survives restarts cleanly:
# the new instance creates a new socket and atomically replaces the symlink.

set -e

AGENT_DIR="$HOME/.ssh/agent"

# Ensure the directory exists
mkdir -p "$AGENT_DIR"

# Clean up stale per-PID sockets from prior crashes
rm -f "$AGENT_DIR"/local.*.sock

# Create per-PID socket path ($$=PID of this shell, which becomes ssh-agent via exec)
SOCK="$AGENT_DIR/local.$$.sock"

# Atomic symlink: local.sock -> local.<pid>.sock
# Use temp + mv for atomicity (rename is atomic on same filesystem)
ln -sf "$SOCK" "$AGENT_DIR/local.sock.tmp.$$"
mv -f "$AGENT_DIR/local.sock.tmp.$$" "$AGENT_DIR/local.sock"

# Run ssh-agent in foreground (-D), binding to the per-PID socket.
# exec replaces this shell, so ssh-agent inherits the same PID that
# we used in the socket filename.
exec /usr/bin/ssh-agent -D -a "$SOCK"
