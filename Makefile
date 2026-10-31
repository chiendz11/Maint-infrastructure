PYTHON ?= .venv/bin/python

.PHONY: local-init local-up local-status local-check tf-init tf-plan tf-apply tf-destroy

local-init:
	$(PYTHON) -m localdev init

local-up:
	$(PYTHON) -m localdev up

local-status:
	$(PYTHON) -m localdev status

local-check:
	$(PYTHON) -m localdev.checks

tf-init:
	cd terraform/local && terraform init

tf-plan:
	cd terraform/local && terraform plan

tf-apply:
	cd terraform/local && terraform apply -auto-approve

tf-destroy:
	cd terraform/local && terraform destroy -auto-approve
