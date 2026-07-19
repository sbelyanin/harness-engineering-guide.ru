#!/bin/bash
# Runner для всех quality gates (F1-F4).
# Запуск: bash site/scripts/run-quality-gates.sh
# Используется локально и в CI (см. .github/workflows/quality.yml).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Running quality gates (F1-F4)..."
echo ""

FAILED=0

for checker in check_frontmatter.py check_registry.py check_links.py check_style.py; do
    if python3 "$SCRIPT_DIR/$checker"; then
        echo ""
    else
        echo "FAIL: $checker"
        echo ""
        FAILED=1
    fi
done

if [ $FAILED -ne 0 ]; then
    echo "=============================================="
    echo "QUALITY GATES FAILED — см. ошибки выше"
    echo "=============================================="
    exit 1
fi

echo "=============================================="
echo "ALL QUALITY GATES PASSED ✓"
echo "=============================================="
