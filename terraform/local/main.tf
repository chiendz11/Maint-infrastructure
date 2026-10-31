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
      .venv/bin/python -m localdev bootstrap-argocd
    EOT
  }
}

resource "null_resource" "provisioning" {
  depends_on = [null_resource.platform_bootstrap]

  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = <<-EOT
      mkdir -p local/.local/data/datasets
      cp ../MaintAI/sensor/data/ai4i2020.csv local/.local/data/datasets/ai4i2020.csv
      .venv/bin/python -m localdev model-identity
      .venv/bin/python -m localdev provision
      .venv/bin/python -m localdev activate-ordering --legacy-writers-drained
    EOT
  }
}

resource "null_resource" "argocd_sync" {
  depends_on = [null_resource.provisioning]

  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = <<-EOT
      export KUBECONFIG="$PWD/local/.local/kubeconfig"
      kubectl --context k3d-maintai-local -n argocd patch application maintai-local-apps \
        --type merge -p '{"operation":{"sync":{"prune":false}}}' || true
    EOT
  }
}
