PYTHON ?= .venv/bin/python
.PHONY: local-init local-up local-status local-check
local-init:
	$(PYTHON) -m localdev init
local-up:
	$(PYTHON) -m localdev up
local-status:
	$(PYTHON) -m localdev status
local-check:
	$(PYTHON) -m localdev.checks
