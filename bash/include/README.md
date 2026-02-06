# Bash Include Scripts

This directory contains bash scripts that are automatically sourced when bash starts (via `bash_aliases`).

## Files

### `commands-log`

Logs every bash command executed to `~/.shell_logs/${HOSTNAME}` with timestamps.

**Format**: `YYYY-MM-DD HH:MM:SS [PID%USER@HOST:PWD]'command' -> exit_code`

**Helper function**: `f()` - Search command history across all log files

**Example**:
```bash
f "git commit"  # Shows last 15 git commit commands from history
```

### `go`

Sets up the Go programming language environment.

**Variables**:
- `GOPATH=$HOME/gocode` - Where Go packages are downloaded
- `GOROOT=$HOME/go` - Go runtime installation location

**PATH additions**: Adds `$GOPATH/bin` and `$GOROOT/bin` to PATH

### `path`

Ensures user bin directories are in PATH.

**PATH additions**: Adds `~/.local/bin` and `~/bin` to PATH (if they exist)

**Note**: Uses case statement to avoid duplicate PATH entries if already present

### `kicad-env.sh`

Environment variables for KiCad PCB design software (when installed).

### `shell`

Ensures the SHELL environment variable is set to bash.

**Behavior**: Checks if `$SHELL` is unset or not pointing to bash, and sets it to the detected bash path

**Note**: Tries common locations (`/bin/bash`, `/usr/bin/bash`, `/usr/local/bin/bash`) and falls back to `command -v bash`

### `terminal-title`

Manages terminal window/tab title with override support.

**Problem**: Ubuntu's `~/.bashrc` hardcodes the title in PS1, overwriting any manual changes on every prompt.

**Solution**: Replaces the hardcoded title with a conditional `${TERMINAL_TITLE:-default}` expansion in PS1. Zero fork overhead.

**Function**: `set-title`
- `set-title "My Title"` - Set persistent title override
- `set-title` - Clear override, return to automatic `user@host: ~/dir`

**Variable**: `TERMINAL_TITLE` - When set, used as terminal title instead of default

**Example**:
```bash
set-title "Build Server"  # Title persists across prompts
# ... do work ...
set-title                 # Return to default title
```

## Adding New Scripts

To add a new script:
1. Create the file in this directory
2. Make it executable: `chmod +x filename`
3. It will be automatically sourced on next bash session

Note: Scripts are sourced in alphabetical order.
