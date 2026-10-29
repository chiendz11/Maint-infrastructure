terraform {
  required_version = "= 1.15.6"
  backend "s3" {
    key          = "maintai-v13/argocd.tfstate"
    use_lockfile = true
    encrypt      = true
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.61.0" }
    helm = { source = "hashicorp/helm", version = "3.2.0" }
  }
}
provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = "MaintAI", Environment = "production", ManagedBy = "terraform", Blueprint = "v1.3.1" }
  }
}

provider "helm" {
  kubernetes = {
    host = data.terraform_remote_state.platform.outputs.eks_endpoint
    cluster_ca_certificate = base64decode(data.terraform_remote_state.platform.outputs.eks_ca)
    exec = { api_version = "client.authentication.k8s.io/v1beta1", command = "aws", args = ["eks", "get-token", "--cluster-name", data.terraform_remote_state.platform.outputs.eks_name, "--region", var.aws_region] }
  }
}
