.PHONY: test audit

test:
	bash scripts/run-tests.sh

audit:
	@for t in prd interaction ui tech test; do \
		echo "=== $$t ==="; \
		python3 scripts/doc-audit.py references/steps/$${t}-step.md --type $$t 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print('blocking:', d['summary']['blocking'], 'warning:', d['summary']['warning'])"; \
	done
