.PHONY: help check venv venv-upgrade venv-clean test shellcheck python-lint \
	python-format python-fix yaml-lint file-checks clean

# --- Development virtualenv -------------------------------------------------
#
# All quality tools live in a repo-local venv built by uv, so `make check`
# needs nothing preinstalled beyond uv itself -- and CI runs the very same
# targets against the very same venv (.github/workflows/quality-check.yml),
# which keeps local and CI results honest about each other.
#
# shellcheck comes from the shellcheck-py wheel, which ships the real static
# shellcheck binary, so no apt install is required either.
#
# Versions deliberately float: the venv captures whatever is current when it
# is first created, and `make venv-upgrade` is the explicit way to move to
# newer tools. A new tool release can therefore add rules and turn the build
# red with no change to this repo; that is the accepted trade for staying
# current without a lockfile to maintain.
VENV := .venv
VENV_STAMP := $(VENV)/.stamp
VENV_TOOLS := ruff yamllint shellcheck-py

RUFF := $(VENV)/bin/ruff
YAMLLINT := $(VENV)/bin/yamllint
SHELLCHECK := $(VENV)/bin/shellcheck
PYTHON := $(VENV)/bin/python

# Default target - show help
help:
	@echo "Available targets:"
	@echo "  make check          - Run all quality checks (and tests)"
	@echo "  make venv           - Create the development virtualenv"
	@echo "  make venv-upgrade   - Upgrade the venv tools to their latest releases"
	@echo "  make venv-clean     - Remove the development virtualenv"
	@echo "  make test           - Run the repository test scripts"
	@echo "  make shellcheck     - Run ShellCheck on shell scripts"
	@echo "  make python-lint    - Run ruff linter on Python files"
	@echo "  make python-format  - Check Python file formatting with ruff"
	@echo "  make python-fix     - Auto-format Python files with ruff"
	@echo "  make yaml-lint      - Run yamllint on YAML files"
	@echo "  make file-checks    - Check for trailing whitespace and tabs"
	@echo "  make clean          - Remove temporary files"

# Run all checks
check: shellcheck python-lint python-format yaml-lint file-checks test
	@echo ""
	@echo "✓ All quality checks passed!"

# Create the development virtualenv (idempotent: the stamp makes this run once)
venv: $(VENV_STAMP)

$(VENV_STAMP):
	@command -v uv >/dev/null 2>&1 || { \
		echo "Error: uv not found. Install it from https://docs.astral.sh/uv/"; \
		exit 1; \
	}
	@echo "Creating development virtualenv in $(VENV)..."
	@uv venv $(VENV)
	@uv pip install --quiet --python $(PYTHON) $(VENV_TOOLS)
	@touch $@
	@echo "✓ Virtualenv ready ($(VENV_TOOLS))"

# Move the floating tool versions forward on purpose
venv-upgrade: $(VENV_STAMP)
	@echo "Upgrading venv tools..."
	@uv pip install --quiet --python $(PYTHON) --upgrade $(VENV_TOOLS)
	@echo "✓ Virtualenv tools upgraded"

venv-clean:
	@echo "Removing $(VENV)..."
	@rm -rf $(VENV)
	@echo "✓ Virtualenv removed"

# Run the repository's test scripts
#
# Discovered by glob rather than listed, so a new test file is picked up with no
# Makefile change. Each runs as its own process: these are plain scripts with a
# __main__ block and an exit status, not a pytest suite.
test: $(VENV_STAMP)
	@echo "Running tests..."
	@failed=0; found=0; \
	for t in bin/test_*.py ssh/tests/test_*.py; do \
		[ -f "$$t" ] || continue; \
		found=$$((found + 1)); \
		echo "  → $$t"; \
		$(PYTHON) "$$t" || failed=$$((failed + 1)); \
	done; \
	if [ "$$found" -eq 0 ]; then \
		echo "Error: no test files found"; \
		exit 1; \
	fi; \
	if [ "$$failed" -ne 0 ]; then \
		echo "Error: $$failed of $$found test file(s) failed"; \
		exit 1; \
	fi; \
	echo "✓ All $$found test file(s) passed"

# ShellCheck - shell script linting
shellcheck: | $(VENV_STAMP)
	@echo "Running ShellCheck..."
	@find . -type f \
		! -path '*/.git/*' \
		! -path '*/vim/bundle/*' \
		! -path '*/vim/bundle-disable/*' \
		! -path '*/gdb/gdb-dashboard/*' \
		! -path '*/tmux/plugins/tpm/*' \
		! -path '*/.venv/*' \
		! -name 'zprofile' \
		\( -name '*.sh' -o -name '*.bash' \) \
		-exec $(SHELLCHECK) --severity=warning {} +
	@echo "✓ ShellCheck passed"

# Python linting with ruff
python-lint: | $(VENV_STAMP)
	@echo "Running ruff linter..."
	@$(RUFF) check python/ bin/*.py backup/*.py --exclude vim/ --exclude gdb/
	@echo "✓ Python linting passed"

# Python formatting check with ruff
python-format: | $(VENV_STAMP)
	@echo "Checking Python formatting..."
	@$(RUFF) format --check python/ bin/*.py backup/*.py --exclude vim/ --exclude gdb/
	@echo "✓ Python formatting check passed"

# Auto-format Python files with ruff
python-fix: | $(VENV_STAMP)
	@echo "Auto-formatting Python files..."
	@$(RUFF) format python/ bin/*.py backup/*.py --exclude vim/ --exclude gdb/
	@echo "✓ Python files formatted"

# YAML linting with yamllint
yaml-lint: | $(VENV_STAMP)
	@echo "Running yamllint..."
	@$(YAMLLINT) -c .yamllint .github/
	@echo "✓ YAML linting passed"

# File quality checks
file-checks:
	@echo "Checking for trailing whitespace..."
	@if git grep -n '[[:space:]]$$' -- \
		'*.sh' '*.py' '*.bash' \
		':!vim/bundle*' \
		':!gdb/gdb-dashboard' \
		':!.git*'; then \
		echo "Error: Trailing whitespace found"; \
		exit 1; \
	fi
	@echo "✓ No trailing whitespace found"
	@echo "Checking for tabs in Python files..."
	@if git grep -n $$'\t' -- '*.py' \
		':!vim/bundle*' \
		':!gdb/gdb-dashboard'; then \
		echo "Error: Tabs found in Python files (use spaces)"; \
		exit 1; \
	fi
	@echo "✓ No tabs in Python files"

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	@find . -type f -name '*.pyc' -delete
	@find . -type d -name '__pycache__' -delete
	@find . -type d -name '.pytest_cache' -delete
	@find . -type d -name '.ruff_cache' -delete
	@echo "✓ Cleaned"
