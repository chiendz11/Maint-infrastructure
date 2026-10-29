variable "aws_region" {
  type = string
  default = "ap-southeast-1"
}
variable "vpc_cidr" {
  type = string
  default = "10.76.0.0/16"
}
variable "kubernetes_version" {
  type = string
  default = "1.33"
}
variable "eks_addon_versions" {
  type = map(string)
  description = "Exact AWS region/Kubernetes-compatible builds, with no most_recent resolution."
  validation {
    condition = alltrue([for key in ["coredns", "kube-proxy", "vpc-cni", "aws-ebs-csi-driver"] : can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+-eksbuild\\.[0-9]+$", var.eks_addon_versions[key]))])
    error_message = "Pin all four add-ons to exact eksbuild versions."
  }
}
variable "node_ami_release_version" {
  type = string
  validation {
    condition = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+-[0-9]{8}$", var.node_ami_release_version))
    error_message = "Pin an AL2023 EKS AMI release compatible with the chosen EKS minor."
  }
}
variable "node_instance_types" {
  type = list(string)
  default = ["m6i.xlarge"]
}
variable "node_desired_size" {
  type = number
  default = 3
}
variable "cluster_public_access_cidrs" {
  type = list(string)
  description = "Reviewed operator and CI runner egress CIDRs. Private endpoint remains enabled."
  validation {
    condition = length(var.cluster_public_access_cidrs) > 0 && !contains(var.cluster_public_access_cidrs, "0.0.0.0/0")
    error_message = "Provide explicit operator/runner CIDRs."
  }
}
variable "operator_role_arns" {
  type = set(string)
}
variable "terraform_apply_role_arn" {
  type = string
}
variable "github_oidc_provider_arn" {
  type = string
}
variable "github_owner" {
  type = string
  default = "chiendz11"
}
variable "app_repository" {
  type = string
  default = "MaintAI"
}
variable "gitops_repository" {
  type = string
  default = "MaintAI-gitops"
}
variable "postgres_engine_version" {
  type = string
  validation {
    condition = can(regex("^17\\.[0-9]+$", var.postgres_engine_version))
    error_message = "Pin an exact region-supported PostgreSQL 17 minor."
  }
}
variable "pgvector_extension_version" {
  type = string
}
variable "db_instance_class" {
  type = string
  default = "db.t4g.medium"
}
variable "db_multi_az" {
  type = bool
  default = false
}
variable "state_bucket" {
  type = string
}
variable "state_kms_key_arn" {
  type = string
}
variable "additional_external_secret_arns" {
  type = set(string)
  default = []
}
