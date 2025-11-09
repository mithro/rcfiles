.PHONY: help check shellcheck python-lint python-format yaml-lint file-checks clean

# Default target - show help
help:
	@echo "Available targets:"
	@echo "  make check          - Run all quality checks"
	@echo "  make shellcheck     - Run ShellCheck on shell scripts"
	@echo "  make python-lint    - Run ruff linter on Python files"
	@echo "  make python-format  - Check Python file formatting with ruff"
	@echo "  make python-fix     - Auto-format Python files with ruff"
	@echo "  make yaml-lint      - Run yamllint on YAML files"
	@echo "  make file-checks    - Check for trailing whitespace and tabs"
	@echo "  make clean          - Remove temporary files"

# Run all checks
check: shellcheck python-lint python-format yaml-lint file-checks
	@echo ""
	@echo "✓ All quality checks passed!"

# ShellCheck - shell script linting
shellcheck:
	@echo "Running ShellCheck..."
	@find . -type f \
		! -path '*/.git/*' \
		! -path '*/vim/bundle/*' \
		! -path '*/vim/bundle-disable/*' \
		! -path '*/gdb/gdb-dashboard/*' \
		! -name 'zprofile' \
		\( -name '*.sh' -o -name '*.bash' \) \
		-exec shellcheck --severity=warning {} +
	@echo "✓ ShellCheck passed"

# Python linting with ruff
python-lint:
	@echo "Running ruff linter..."
	@ruff check python/ bin/*.py backup/*.py --exclude vim/ --exclude gdb/
	@echo "✓ Python linting passed"

# Python formatting check with ruff
python-format:
	@echo "Checking Python formatting..."
	@ruff format --check python/ bin/*.py backup/*.py --exclude vim/ --exclude gdb/
	@echo "✓ Python formatting check passed"

# Auto-format Python files with ruff
python-fix:
	@echo "Auto-formatting Python files..."
	@ruff format python/ bin/*.py backup/*.py --exclude vim/ --exclude gdb/
	@echo "✓ Python files formatted"

# YAML linting with yamllint
yaml-lint:
	@echo "Running yamllint..."
	@yamllint -d "{extends: default, rules: {line-length: {max: 120}, truthy: {check-keys: false}, comments: {require-starting-space: true, min-spaces-from-content: 1}}}" .github/
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
