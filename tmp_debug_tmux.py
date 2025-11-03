#!/usr/bin/env python3
"""
Diagnostic script to investigate tmux Shift-PgUp/PgDn issue.
Gathers evidence about terminal and tmux configuration.
"""

import subprocess
import os
import sys

def run_cmd(cmd, shell=False):
    """Run command and return output."""
    try:
        if shell:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        else:
            result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=5)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", f"Error: {e}", 1

def main():
    hostname = subprocess.run(['hostname', '-f'], capture_output=True, text=True).stdout.strip()
    print(f"=== Diagnostics for {hostname} ===\n")

    # 1. Environment variables
    print("--- Environment Variables ---")
    for var in ['TERM', 'COLORTERM', 'TMUX', 'TMUX_PANE', 'SHELL']:
        print(f"{var}: {os.environ.get(var, 'NOT SET')}")
    print()

    # 2. Tmux version
    print("--- Tmux Version ---")
    stdout, stderr, rc = run_cmd("tmux -V")
    print(stdout if rc == 0 else f"Error: {stderr}")
    print()

    # 3. Tmux configuration file location and contents
    print("--- Tmux Config File ---")
    tmux_conf = os.path.expanduser("~/.tmux.conf")
    if os.path.exists(tmux_conf):
        if os.path.islink(tmux_conf):
            print(f"~/.tmux.conf -> {os.readlink(tmux_conf)}")
        else:
            print(f"~/.tmux.conf is a regular file ({os.path.getsize(tmux_conf)} bytes)")

        # Show Shift-PgUp/PgDn related lines
        print("\n--- Shift-PgUp/PgDn bindings in ~/.tmux.conf ---")
        with open(tmux_conf, 'r') as f:
            for i, line in enumerate(f, 1):
                if 'S-Pg' in line or 'PgUp' in line or 'PgDn' in line or 'pageup' in line.lower():
                    print(f"  {i}: {line.rstrip()}")
    else:
        print("~/.tmux.conf does NOT exist")
    print()

    # 4. Check if running inside tmux
    if 'TMUX' in os.environ:
        print("--- Current Tmux Session Info ---")
        stdout, stderr, rc = run_cmd("tmux display-message -p '#{client_termtype}'", shell=True)
        print(f"Client terminal type: {stdout}")

        # List key bindings for Shift-PgUp
        print("\n--- Tmux Key Bindings (Shift-PgUp/PgDn) ---")
        stdout, stderr, rc = run_cmd("tmux list-keys | grep -i 'S-Pg'", shell=True)
        if stdout:
            print(stdout)
        else:
            print("No S-PgUp/S-PgDn bindings found")
        print()
    else:
        print("NOT running inside tmux session")
        print()

    # 5. Terminal capabilities for page up/down
    print("--- Terminal Capabilities ---")
    for cap in ['kpp', 'knp', 'kcuu1', 'kcud1']:
        stdout, stderr, rc = run_cmd(f"tput {cap}", shell=True)
        if rc == 0:
            # Show escape sequence in visible form
            visible = repr(stdout)
            print(f"{cap}: {visible}")
    print()

    # 6. What escape sequence does Shift-PgUp send?
    print("--- Testing Key Sequences ---")
    print("To test what escape sequence Shift-PgUp sends:")
    print("1. Run: cat -v")
    print("2. Press Shift-PgUp")
    print("3. Look for output like: ^[[5;2~ (working) or 2~2~ (broken)")
    print("4. Press Ctrl-C to exit cat")
    print()

if __name__ == '__main__':
    main()
