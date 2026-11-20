# Local Demo Infrastructure for MaintAI (k3d + Argo CD GitOps)

resource "null_resource" "init" {
  triggers = {
    revision = var.gitops_revision
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = <<-EOT
      test -d .venv || python3.12 -m venv .venv
      .venv/bin/python -m pip install -q -r local/requirements.lock
      .venv/bin/python -m localdev init
    EOT
  }
}

resource "null_resource" "k3d_cluster" {
  depends_on = [null_resource.init]

  triggers = {
    cluster_name = var.cluster_name
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = ".venv/bin/python -m localdev up"
  }

  provisioner "local-exec" {
    when        = destroy
    working_dir = "${path.module}/../.."
    command     = "k3d cluster delete maintai-local || true"
  }
}

resource "null_resource" "platform_bootstrap" {
  depends_on = [null_resource.k3d_cluster]

  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = <<-EOT
      .venv/bin/python -m localdev build-platform
      .venv/bin/python -m localdev import-images --component minio --component mc --component dev-tools
      
      export KUBECONFIG="$PWD/local/.local/kubeconfig"
      
      # 1. LocalStack (Mock AWS Secrets Manager & S3)
      kubectl apply -f local/manifests/localstack.yaml
      kubectl rollout status deployment/localstack -n localstack --timeout=120s
      
      # 2. External Secrets Operator (CRDs + Controller)
      helm upgrade --install external-secrets external-secrets/external-secrets \
        -n external-secrets --create-namespace --set installCRDs=true --wait
      kubectl set env deployment/external-secrets -n external-secrets \
        AWS_ENDPOINT_URL=http://localstack.localstack.svc.cluster.local:4566
      kubectl apply -f local/manifests/cluster-secret-store.yaml
      .venv/bin/python local/manifests/seed_localstack_secrets.py
      .venv/bin/python -m localdev.history seed

      # 2b. cert-manager (CRDs + Controller for local Ingress & IdP TLS parity)
      helm upgrade --install cert-manager oci://quay.io/jetstack/charts/cert-manager \
        --version v1.21.3 -n cert-manager --create-namespace \
        --set crds.enabled=true --wait

      # 2c. KEDA (CRDs + Operator + Metrics API Server for Kafka consumer lag scaling)
      KEDA_VERSION=$(.venv/bin/python -c "import json; print(json.load(open('local/versions/platform.lock.json'))['keda']['chart_version'])")
      KEDA_REPO=$(.venv/bin/python -c "import json; print(json.load(open('local/versions/platform.lock.json'))['keda']['chart_repo'])")
      helm repo add kedacore "$KEDA_REPO" --force-update
      helm repo update kedacore
      helm upgrade --install keda kedacore/keda \
        --version "$KEDA_VERSION" -n keda --create-namespace \
        --set crds.install=true --wait
      
      # 3. Ingress NGINX (Simulating AWS ALB Controller)
      helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
        -n ingress-nginx --create-namespace \
        --set controller.service.type=NodePort \
        --set controller.service.nodePorts.http=30080 \
        --set controller.service.nodePorts.https=30443 \
        --set controller.ingressClassResource.name=alb \
        --set controller.ingressClass=alb \
        --set controller.ingressClassResource.default=true \
        --wait
      
      # 4. Bootstrap Argo CD GitOps Engine
      .venv/bin/python -m localdev bootstrap-argocd
    EOT
  }
}

resource "null_resource" "argocd_sync" {
  depends_on = [null_resource.platform_bootstrap]

  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = <<-EOT
      export KUBECONFIG="$PWD/local/.local/kubeconfig"
      kubectl --context k3d-maintai-local -n argocd patch application maintai-local-apps \
        --type merge -p '{"operation":{"sync":{"prune":false}}}' || true
    EOT
  }
}
