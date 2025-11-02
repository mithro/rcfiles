# Python Utility Libraries

This directory contains Python utility modules and libraries used by scripts in this repository.

## Modules

### `caller.py`
Utilities for inspecting the call stack and caller information in Python programs.

### `csv_bulletproof.py`
Robust CSV file handling that can deal with malformed CSV files. Includes error recovery and flexible parsing.

### `force_unicode.py`
Utilities for forcing proper Unicode handling in Python 2/3 compatible code. Handles encoding/decoding edge cases.

### `html_encoding.py`
Utilities for detecting and handling HTML character encodings, including meta tag parsing and charset detection.

### `http_headers.py`
HTTP header parsing and manipulation utilities.

### `text_alignment.py`
Text alignment and formatting utilities for console output.

## Subdirectories

### `firefox/`
Firefox-related utilities and configurations.

### `statfs/`
Filesystem statistics utilities.

## Usage

These modules are typically imported by scripts in the `bin/` directory. They are not standalone tools but provide reusable functionality.

Example:
```python
from python import force_unicode
from python import csv_bulletproof
```
