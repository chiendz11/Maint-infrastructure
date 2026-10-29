terraform {
  required_version = "= 1.15.6"
  backend "s3" {
    key          = "maintai-v13/domain.tfstate"
    use_lockfile = true
    encrypt      = true
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.61.0" }

  }
}
provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = "MaintAI", Environment = "production", ManagedBy = "terraform", Blueprint = "v1.3.1" }
  }
}
