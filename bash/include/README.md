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

### `kicad-env.sh`

Environment variables for KiCad PCB design software (when installed).

### `shell`

Ensures the SHELL environment variable is set to bash.

**Behavior**: Checks if `$SHELL` is unset or not pointing to bash, and sets it to the detected bash path

**Note**: Tries common locations (`/bin/bash`, `/usr/bin/bash`, `/usr/local/bin/bash`) and falls back to `command -v bash`

## Adding New Scripts

To add a new script:
1. Create the file in this directory
2. Make it executable: `chmod +x filename`
3. It will be automatically sourced on next bash session

Note: Scripts are sourced in alphabetical order.
