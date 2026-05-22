#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."
echo "=== Running doc-audit.py smoke tests ==="
python3 scripts/test_doc_audit.py
echo "=== Running template validation ==="
for t in prd interaction ui tech test; do
  echo "--- $t ---"
  python3 scripts/doc-audit.py "references/steps/${t}-step.md" --type "$t" > /dev/null
done
echo "=== All checks passed ==="
