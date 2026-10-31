output "cluster_name" {
  value       = var.cluster_name
  description = "Name of the local k3d Kubernetes cluster"
}

output "kubeconfig" {
  value       = abspath("${path.module}/../../local/.local/kubeconfig")
  description = "Path to the private kubeconfig for the local cluster"
}

output "business_ui_url" {
  value       = "http://127.0.0.1:18080"
  description = "URL to access the Business UI dashboard"
}

output "simulator_ui_url" {
  value       = "http://127.0.0.1:18081"
  description = "URL to access the Sensor Simulator UI"
}

output "keycloak_url" {
  value       = "https://127.0.0.1:18490"
  description = "URL to access Keycloak IdP"
}

output "grafana_url" {
  value       = "http://127.0.0.1:13000"
  description = "URL to access Grafana Observability"
}

output "minio_url" {
  value       = "http://127.0.0.1:19001"
  description = "URL to access MinIO Console"
}

output "argocd_ui_url" {
  value       = "https://127.0.0.1:18443"
  description = "URL to access Argo CD UI"
}
