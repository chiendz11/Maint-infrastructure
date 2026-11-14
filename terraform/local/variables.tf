variable "cluster_name" {
  type        = string
  default     = "maintai-local"
  description = "Name of the local k3d Kubernetes cluster"
}

variable "machine_count" {
  type        = number
  default     = 5
  description = "Number of industrial sensor machines to provision"
}

variable "gitops_revision" {
  type        = string
  default     = "main"
  description = "Git revision for Argo CD applications in MaintAI-gitops"
}
