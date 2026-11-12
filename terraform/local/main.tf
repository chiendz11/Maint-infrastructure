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
      .venv/bin/python -m localdev prepare platform
      git -C ../MaintAI-gitops diff --quiet || (git -C ../MaintAI-gitops commit -am "chore: update platform image receipts" && git -C ../MaintAI-gitops push origin "${var.gitops_revision}")
      
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
      
      # 3. Ingress NGINX (Simulating AWS ALB Controller)
      helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
        -n ingress-nginx --create-namespace \
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
