# Utility Scripts

This directory contains utility scripts that are symlinked to `~/bin/` during setup.

## Scripts

### Git Utilities

- **`git-branch-squash`** - Squash commits in a git branch
- **`git-fetch-all`** - Fetch from all git remotes
- **`git-credential-stop`** - Stop git credential helper

### Chrome/Browser

- **`chrome-personal.sh`** - Launch Chrome with personal profile
- **`chrome-work.sh`** - Launch Chrome with work profile

### Development Tools

- **`findpython.py`** - Find Python interpreters on the system
- **`json_pp`** - Pretty-print JSON files
- **`xmlsort`** - Sort XML files

### Display/Monitor

- **`external-monitor.sh`** - Configure external monitor setup
- **`mirror-monitor.sh`** - Mirror display to external monitor
- **`xcursorclamp`** - Clamp cursor to specific display

### System Utilities

- **`eog`** - Eye of GNOME image viewer wrapper
- **`fastcomplete`** - Fast bash completion helper
- **`out`** - Output helper utility

### Specialized Tools

- **`recover-sqlite.py`** - Recover corrupted SQLite databases
- **`fix-chrome-sqlite.sh`** - Fix Chrome's SQLite databases
- **`ppa-upload.sh`** - Upload packages to Ubuntu PPA
- **`setup-xilinx.sh`** - Setup Xilinx FPGA tools
- **`setup-conda.sh`** - Setup Conda Python environment
- **`triplej`** - Triple J radio utility

### Data Processing

- **`csv_bulletproof.py`** - Robust CSV file processing

## Usage

After running `setup.sh`, all scripts are available in your PATH via symlinks in `~/bin/`.

Example:
```bash
git-fetch-all        # Fetch from all remotes in current git repo
json_pp file.json    # Pretty-print JSON file
```
