PYTHON ?= .venv/bin/python

.PHONY: local-init local-up local-status local-check tf-init tf-plan tf-apply tf-destroy phase2-bootstrap

phase2-bootstrap:
	export KUBECONFIG=$$PWD/local/.local/kubeconfig && \
	kubectl apply -f local/manifests/localstack.yaml && \
	helm upgrade --install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace --set installCRDs=true --wait && \
	kubectl apply -f local/manifests/cluster-secret-store.yaml && \
	$(PYTHON) local/manifests/seed_localstack_secrets.py && \
	helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace --set controller.ingressClassResource.name=alb --set controller.ingressClass=alb --set controller.ingressClassResource.default=true --wait


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
