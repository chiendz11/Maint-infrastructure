terraform {
  required_version = "= 1.15.6"
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
